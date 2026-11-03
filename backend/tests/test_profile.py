from collections.abc import AsyncIterator
from datetime import date, timedelta

import httpx
import pytest

PUBLIC_KEYS = {"username", "display_name", "bio", "avatar_url"}


async def register(client: httpx.AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "a long enough password",
            "acknowledged_email_notice": True,
        },
    )
    assert response.status_code == 201


async def test_public_profile_hides_private_fields(
    authed: httpx.AsyncClient,
) -> None:
    me = (await authed.get("/api/v1/auth/me")).json()
    updated = await authed.patch(
        "/api/v1/me",
        json={"birthday": "1990-01-02", "phone": "+55 11 99999-0000"},
    )
    assert updated.status_code == 200
    anonymous = httpx.AsyncClient(
        transport=authed._transport, base_url="http://testserver"
    )
    async with anonymous:
        response = await anonymous.get(f"/api/v1/users/{me['username']}")
    assert response.status_code == 200
    assert set(response.json()) == PUBLIC_KEYS


async def test_public_profile_lookup_is_case_insensitive(
    authed: httpx.AsyncClient,
) -> None:
    me = (await authed.get("/api/v1/auth/me")).json()
    response = await authed.get(f"/api/v1/users/{me['username'].upper()}")
    assert response.status_code == 200
    assert response.json()["username"] == me["username"]


async def test_public_profile_unknown_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/users/nobody_here")
    assert response.status_code == 404
    assert response.json() == {"detail": "user_not_found"}


async def test_update_profile_fields(authed: httpx.AsyncClient) -> None:
    response = await authed.patch(
        "/api/v1/me",
        json={
            "display_name": "  Ada  ",
            "bio": "Hello there",
            "birthday": "1990-01-02",
            "phone": " +55 (11) 99999-0000 ",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Ada"
    assert body["bio"] == "Hello there"
    assert body["birthday"] == "1990-01-02"
    assert body["phone"] == "+55 (11) 99999-0000"
    cleared = await authed.patch(
        "/api/v1/me", json={"birthday": None, "phone": None}
    )
    assert cleared.json()["birthday"] is None
    assert cleared.json()["phone"] is None
    me = (await authed.get("/api/v1/auth/me")).json()
    assert me["birthday"] is None
    assert me["phone"] is None


async def test_update_profile_partial_keeps_other_fields(
    authed: httpx.AsyncClient,
) -> None:
    await authed.patch(
        "/api/v1/me", json={"display_name": "Ada", "bio": "First"}
    )
    response = await authed.patch("/api/v1/me", json={"bio": "Second"})
    assert response.json()["display_name"] == "Ada"
    assert response.json()["bio"] == "Second"


async def test_update_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.patch("/api/v1/me", json={"bio": "x"})
    assert response.status_code == 401


@pytest.mark.parametrize("name", ["ab", "a" * 16, "bad-name", "bad name"])
async def test_username_change_lowercases_and_validates(
    authed: httpx.AsyncClient, name: str
) -> None:
    response = await authed.patch("/api/v1/me", json={"username": name})
    assert response.status_code == 422
    assert response.json() == {"detail": "username_invalid"}


async def test_username_change_lowercases(authed: httpx.AsyncClient) -> None:
    response = await authed.patch("/api/v1/me", json={"username": "  Ada_1 "})
    assert response.status_code == 200
    assert response.json()["username"] == "ada_1"


async def test_username_reserved(authed: httpx.AsyncClient) -> None:
    response = await authed.patch("/api/v1/me", json={"username": "Settings"})
    assert response.status_code == 422
    assert response.json() == {"detail": "username_reserved"}


async def test_username_taken(client: httpx.AsyncClient) -> None:
    await register(client, "first@example.com")
    await client.patch("/api/v1/me", json={"username": "taken_name"})
    await client.post("/api/v1/auth/logout")
    await register(client, "second@example.com")
    response = await client.patch(
        "/api/v1/me", json={"username": "TAKEN_name"}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "username_taken"}


async def test_username_unchanged_is_ok(authed: httpx.AsyncClient) -> None:
    me = (await authed.get("/api/v1/auth/me")).json()
    response = await authed.patch(
        "/api/v1/me", json={"username": me["username"]}
    )
    assert response.status_code == 200
    assert response.json()["username"] == me["username"]


async def test_birthday_in_future_rejected(
    authed: httpx.AsyncClient,
) -> None:
    future = (date.today() + timedelta(days=2)).isoformat()
    response = await authed.patch("/api/v1/me", json={"birthday": future})
    assert response.status_code == 422
    assert response.json() == {"detail": "birthday_invalid"}
    old = await authed.patch("/api/v1/me", json={"birthday": "1899-12-31"})
    assert old.status_code == 422
    assert old.json() == {"detail": "birthday_invalid"}


async def test_phone_invalid_rejected(authed: httpx.AsyncClient) -> None:
    response = await authed.patch("/api/v1/me", json={"phone": "call me"})
    assert response.status_code == 422
    assert response.json() == {"detail": "phone_invalid"}


async def test_other_validation_errors_keep_default_shape(
    authed: httpx.AsyncClient,
) -> None:
    response = await authed.patch("/api/v1/me", json={"bio": "x" * 161})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_login_declared_oversized_body_rejected(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        content=b"{}",
        headers={"Content-Length": str(1024 * 1024)},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "request_too_large"}


async def test_login_chunked_oversized_body_rejected(
    client: httpx.AsyncClient,
) -> None:
    async def body() -> AsyncIterator[bytes]:
        for _ in range(16):
            yield b" " * 65536

    response = await client.post(
        "/api/v1/auth/login",
        content=body(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "request_too_large"}


async def test_get_with_oversized_body_rejected(
    client: httpx.AsyncClient,
) -> None:
    response = await client.request(
        "GET", "/api/v1/health", content=b"x" * (70 * 1024)
    )
    assert response.status_code == 413


async def test_normal_login_still_works(authed: httpx.AsyncClient) -> None:
    response = await authed.post(
        "/api/v1/auth/login",
        json={
            "email": "person@example.com",
            "password": "a long enough password",
        },
    )
    assert response.status_code == 200
