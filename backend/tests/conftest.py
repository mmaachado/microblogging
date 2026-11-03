from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth import models as auth_models  # noqa: F401
from backend.auth.service import LoginThrottle, get_login_throttle
from backend.config import Settings
from backend.db import Base
from backend.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}",
        log_file=str(tmp_path / "logs" / "backend.log"),
        media_dir=str(tmp_path / "media"),
        cookie_secure=False,
        registration_rate_per_minute=1000,
        _env_file=None,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    throttle = LoginThrottle()
    app.dependency_overrides[get_login_throttle] = lambda: throttle
    yield app
    await app.state.engine.dispose()


@pytest.fixture
def sessionmaker(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    sm: async_sessionmaker[AsyncSession] = app.state.sessionmaker
    return sm


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def authed(client: httpx.AsyncClient) -> httpx.AsyncClient:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "person@example.com",
            "password": "a long enough password",
            "acknowledged_email_notice": True,
        },
    )
    assert response.status_code == 201
    return client
