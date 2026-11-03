import asyncio
import logging
import time

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth import service
from backend.auth.models import User
from backend.config import Settings
from backend.db import Base
from backend.logging import configure_logging


def test_throttle_sweeps_stale_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    throttle = service.LoginThrottle(max_keys=1)
    throttle.record_failure("old@example.com")
    now[0] += 901
    throttle.record_failure("new@example.com")
    assert list(throttle._failures) == ["new@example.com"]


async def test_verify_password_handles_invalid_hash() -> None:
    assert service.verify_password("not a hash", "whatever") is False


async def test_sql_parameters_are_hidden_in_errors(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    secret = "secret-probe@example.com"
    async with sessionmaker() as db:
        with pytest.raises(StatementError) as info:
            await db.execute(select(User).where(User.id == secret))
    assert secret not in str(info.value)


def test_throttle_evicts_oldest_key_when_full() -> None:
    throttle = service.LoginThrottle(max_keys=3)
    for name in ("a", "b", "c", "d"):
        throttle.record_failure(name)
    assert list(throttle._failures) == ["b", "c", "d"]


def test_cookie_secure_defaults_to_true() -> None:
    assert Settings(_env_file=None).cookie_secure is True


def test_only_backend_loggers_use_configured_level(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    logging.getLogger("thirdparty").info("third party noise")
    logging.getLogger("backend.x").info("own event")
    err = capsys.readouterr().err
    assert "own event" in err
    assert "third party noise" not in err


async def test_password_hashing_concurrency_is_bounded(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    running = 0
    peak = 0

    def slow_verify(password_hash: str, password: str) -> bool:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        time.sleep(0.05)
        running -= 1
        return False

    monkeypatch.setattr(service, "verify_password", slow_verify)
    responses = await asyncio.gather(
        *(
            client.post(
                "/api/v1/auth/login",
                json={
                    "email": f"user{i}@example.com",
                    "password": "wrong password!!",
                },
            )
            for i in range(10)
        )
    )
    assert all(r.status_code == 401 for r in responses)
    assert 1 < peak <= 4


def test_registration_limiter_slides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    limiter = service.RegistrationLimiter(2)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(service.TooManyAttempts):
        limiter.acquire()
    now[0] += 61
    limiter.acquire()


async def test_registration_is_rate_limited(
    settings: Settings,
) -> None:
    from backend.main import create_app

    limited = settings.model_copy(update={"registration_rate_per_minute": 2})
    app = create_app(limited)
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        codes = []
        for i in range(3):
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"person{i}@example.com",
                    "password": "correct horse battery",
                    "acknowledged_email_notice": True,
                },
            )
            codes.append(response.status_code)
        assert codes == [201, 201, 429]
        assert response.json() == {"detail": "too_many_attempts"}
    await app.state.engine.dispose()
