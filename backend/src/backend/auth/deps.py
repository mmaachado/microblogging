import asyncio
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.auth.service import RegistrationLimiter, resolve_session
from backend.config import Settings
from backend.db import get_db


def get_hash_limiter(request: Request) -> asyncio.Semaphore:
    limiter: asyncio.Semaphore = request.app.state.hash_limiter
    return limiter


def get_registration_limiter(request: Request) -> RegistrationLimiter:
    limiter: RegistrationLimiter = request.app.state.registration_limiter
    return limiter


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    session: Annotated[str | None, Cookie()] = None,
) -> User:
    user = await resolve_session(db, session) if session else None
    if user is None:
        raise HTTPException(401, "not_authenticated")
    return user
