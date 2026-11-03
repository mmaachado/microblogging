import asyncio
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import current_user, get_app_settings
from backend.auth.models import User
from backend.auth.schemas import MeOut
from backend.config import Settings
from backend.db import get_db
from backend.media.images import InvalidImage
from backend.users import service
from backend.users.schemas import ProfileUpdateIn, PublicProfileOut

MAX_AVATAR_BYTES = 5 * 1024 * 1024


def get_image_limiter(request: Request) -> asyncio.Semaphore:
    limiter: asyncio.Semaphore = request.app.state.image_limiter
    return limiter


router = APIRouter(prefix="/api/v1", tags=["users"])

Db = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
ImageLimiter = Annotated[asyncio.Semaphore, Depends(get_image_limiter)]
CurrentUser = Annotated[User, Depends(current_user)]


@router.get("/users/{username}")
async def get_profile(username: str, db: Db) -> PublicProfileOut:
    user = await service.get_by_username(db, username)
    if user is None:
        raise HTTPException(404, "user_not_found")
    return PublicProfileOut.model_validate(user)


@router.patch("/me")
async def update_me(data: ProfileUpdateIn, db: Db, user: CurrentUser) -> MeOut:
    try:
        updated = await service.update_profile(db, user, data)
    except service.UsernameTaken:
        raise HTTPException(409, "username_taken") from None
    return MeOut.model_validate(updated)


@router.put("/me/avatar")
async def upload_avatar(
    file: Annotated[UploadFile, File()],
    db: Db,
    user: CurrentUser,
    settings: AppSettings,
    limiter: ImageLimiter,
) -> MeOut:
    data = await file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "file_too_large")
    try:
        updated = await service.set_avatar(
            db, user, settings.media_dir, data, limiter
        )
    except InvalidImage:
        raise HTTPException(422, "invalid_image") from None
    return MeOut.model_validate(updated)


@router.delete("/me/avatar")
async def delete_avatar(
    db: Db, user: CurrentUser, settings: AppSettings
) -> MeOut:
    updated = await service.remove_avatar(db, user, settings.media_dir)
    return MeOut.model_validate(updated)
