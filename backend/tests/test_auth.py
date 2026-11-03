import asyncio
import hashlib
import re
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.models import User, UserSession

EMAIL = "Person@Example.com"
PASSWORD = "correct horse battery"


def payload(
    email: str = EMAIL,
    password: str = PASSWORD,
    acknowledged: bool = True,
) -> dict[str, object]:
    return {
        "email": email,
        "password": password,
        "acknowledged_email_notice": acknowledged,
    }


async def register(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/api/v1/auth/register", json=payload())


async def test_register_requires_notice_acknowledgement(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register", json=payload(acknowledged=False)
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "notice_not_acknowledged"}


async def test_register_rejects_short_password(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register", json=payload(password="short")
    )
    assert response.status_code == 422


async def test_register_creates_user_and_logs_in(
    client: httpx.AsyncClient,
) -> None:
    response = await register(client)
    assert response.status_code == 201
    header = response.headers["set-cookie"].lower()
    assert "session=" in header
    assert "httponly" in header
    assert "samesite=strict" in header
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == EMAIL.lower()
    assert re.fullmatch(r"user_[a-z0-9]{8}", body["username"])


async def test_register_duplicate_email_is_case_insensitive(
    client: httpx.AsyncClient,
) -> None:
    await register(client)
    response = await client.post(
        "/api/v1/auth/register", json=payload(email=EMAIL.upper())
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "email_taken"}


async def test_password_is_stored_hashed(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await register(client)
    async with sessionmaker() as db:
        stored = (await db.execute(select(User.password_hash))).scalar_one()
    assert stored.startswith("$argon2id$")
    assert stored != PASSWORD


async def test_session_token_is_stored_hashed(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await register(client)
    token = client.cookies["session"]
    async with sessionmaker() as db:
        hashes = (await db.execute(select(UserSession.token_hash))).scalars()
        stored = list(hashes)
    assert token not in stored
    assert hashlib.sha256(token.encode()).hexdigest() in stored


async def test_login_success_and_me(client: httpx.AsyncClient) -> None:
    await register(client)
    client.cookies.clear()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL.upper(), "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL.lower()
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200


async def test_me_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "not_authenticated"}


async def test_login_wrong_password_and_unknown_email_return_same_error(
    client: httpx.AsyncClient,
) -> None:
    await register(client)
    client.cookies.clear()
    wrong = await client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "wrong password!!"},
    )
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": PASSWORD},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json() == {"detail": "invalid_credentials"}


async def test_login_throttled_after_five_failures(
    client: httpx.AsyncClient,
) -> None:
    await register(client)
    body = {"email": EMAIL, "password": "wrong password!!"}
    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json=body)
        assert response.status_code == 401
    response = await client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 429
    assert response.json() == {"detail": "too_many_attempts"}


async def test_logout_deletes_session(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await register(client)
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401
    async with sessionmaker() as db:
        count = await db.execute(text("select count(*) from sessions"))
        assert count.scalar_one() == 0


async def test_logout_without_session_returns_204(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204


async def test_expired_session_is_rejected(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await register(client)
    async with sessionmaker() as db:
        await db.execute(
            update(UserSession).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        await db.commit()
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401
    async with sessionmaker() as db:
        count = await db.execute(text("select count(*) from sessions"))
        assert count.scalar_one() == 0


async def test_mutation_with_foreign_origin_is_rejected(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json=payload(),
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "origin_not_allowed"}


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


async def test_allowed_origin_can_register(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json=payload(),
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 201


async def test_missing_origin_can_register(
    client: httpx.AsyncClient,
) -> None:
    response = await register(client)
    assert response.status_code == 201


async def test_concurrent_failures_are_throttled(
    client: httpx.AsyncClient,
) -> None:
    await register(client)
    body = {"email": EMAIL, "password": "wrong password!!"}
    responses = await asyncio.gather(
        *(client.post("/api/v1/auth/login", json=body) for _ in range(10))
    )
    codes = [r.status_code for r in responses]
    assert codes.count(429) >= 5


async def test_login_rejects_overlong_password(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "x" * 129},
    )
    assert response.status_code == 422


async def test_logout_cookie_deletion_keeps_attributes(
    client: httpx.AsyncClient,
) -> None:
    await register(client)
    response = await client.post("/api/v1/auth/logout")
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=strict" in header


async def test_expired_sessions_of_other_users_are_purged(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await register(client)
    other = await client.post(
        "/api/v1/auth/register",
        json=payload(email="other@example.com"),
    )
    assert other.status_code == 201
    async with sessionmaker() as db:
        first = (
            await db.execute(
                select(UserSession).order_by(UserSession.created_at).limit(1)
            )
        ).scalar_one()
        first.expires_at = datetime.now(UTC) - timedelta(days=1)
        await db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    async with sessionmaker() as db:
        count = await db.execute(text("select count(*) from sessions"))
        assert count.scalar_one() == 1
