import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import service
from backend.auth.deps import (
    current_user,
    get_app_settings,
    get_hash_limiter,
    get_registration_limiter,
)
from backend.auth.models import User
from backend.auth.schemas import LoginIn, MeOut, RegisterIn
from backend.config import Settings
from backend.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

Db = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
Limiter = Annotated[asyncio.Semaphore, Depends(get_hash_limiter)]
RegLimiter = Annotated[
    service.RegistrationLimiter, Depends(get_registration_limiter)
]
Throttle = Annotated[
    service.LoginThrottle, Depends(service.get_login_throttle)
]


def _me(user: User) -> MeOut:
    return MeOut.model_validate(user)


async def _start_session(
    db: AsyncSession, user: User, response: Response, settings: Settings
) -> None:
    token = await service.create_session(db, user, settings.session_ttl_days)
    response.set_cookie(
        "session",
        token,
        max_age=settings.session_ttl_days * 86400,
        path="/",
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.post("/register", status_code=201)
async def register(
    data: RegisterIn,
    response: Response,
    db: Db,
    settings: AppSettings,
    limiter: Limiter,
    reg_limiter: RegLimiter,
) -> MeOut:
    try:
        reg_limiter.acquire()
    except service.TooManyAttempts:
        logger.warning("registration throttled")
        raise HTTPException(429, "too_many_attempts") from None
    try:
        user = await service.register(db, data, limiter)
    except service.NoticeNotAcknowledged:
        raise HTTPException(422, "notice_not_acknowledged") from None
    except service.EmailTaken:
        raise HTTPException(409, "email_taken") from None
    await _start_session(db, user, response, settings)
    return _me(user)


@router.post("/login")
async def login(
    data: LoginIn,
    response: Response,
    db: Db,
    settings: AppSettings,
    throttle: Throttle,
    limiter: Limiter,
) -> MeOut:
    try:
        user = await service.authenticate(
            db, data.email, data.password, throttle, limiter
        )
    except service.TooManyAttempts:
        raise HTTPException(429, "too_many_attempts") from None
    except service.InvalidCredentials:
        raise HTTPException(401, "invalid_credentials") from None
    await _start_session(db, user, response, settings)
    logger.info("user logged in")
    return _me(user)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: Db,
    settings: AppSettings,
    session: Annotated[str | None, Cookie()] = None,
) -> None:
    if session:
        await service.revoke_session(db, session)
        logger.info("user logged out")
    response.delete_cookie(
        "session",
        path="/",
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.get("/me")
async def me(user: Annotated[User, Depends(current_user)]) -> MeOut:
    return _me(user)
