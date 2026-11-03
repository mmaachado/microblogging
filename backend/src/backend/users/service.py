import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.media.storage import delete_media, save_bytes
from backend.users.avatar import process_avatar
from backend.users.schemas import ProfileUpdateIn

logger = logging.getLogger(__name__)


class UsernameTaken(Exception):
    pass


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(
        select(User).where(User.username == username.lower())
    )
    return result.scalar_one_or_none()


async def update_profile(
    db: AsyncSession, user: User, data: ProfileUpdateIn
) -> User:
    changes = data.model_dump(include=data.model_fields_set)
    new_name = changes.get("username")
    if new_name is not None and new_name != user.username:
        taken = await db.execute(
            select(User.id).where(
                User.username == new_name, User.id != user.id
            )
        )
        if taken.first() is not None:
            raise UsernameTaken
    for field, value in changes.items():
        setattr(user, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise UsernameTaken from None
    logger.info("profile updated")
    return user


async def _discard(media_dir: str, relative_path: str | None) -> None:
    if not relative_path:
        return
    try:
        await asyncio.to_thread(delete_media, media_dir, relative_path)
    except OSError:
        logger.warning("old avatar cleanup failed")


async def set_avatar(
    db: AsyncSession,
    user: User,
    media_dir: str,
    data: bytes,
    limiter: asyncio.Semaphore,
) -> User:
    async with limiter:
        processed = await asyncio.to_thread(process_avatar, data)
    old = user.avatar_path
    new = await asyncio.to_thread(
        save_bytes, media_dir, "avatars", processed, "webp"
    )
    user.avatar_path = new
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await _discard(media_dir, new)
        raise
    await _discard(media_dir, old)
    logger.info("avatar updated")
    return user


async def remove_avatar(db: AsyncSession, user: User, media_dir: str) -> User:
    old = user.avatar_path
    user.avatar_path = None
    await db.commit()
    if old:
        await _discard(media_dir, old)
        logger.info("avatar removed")
    return user
