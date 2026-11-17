from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import current_user
from backend.auth.models import User
from backend.db import get_db
from backend.interactions import service
from backend.posts import service as posts_service
from backend.posts.models import Post
from backend.posts.schemas import FeedPage, PostOut

router = APIRouter(prefix="/api/v1", tags=["interactions"])

Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
Setter = Callable[[AsyncSession, User, Post, bool], Awaitable[None]]


async def _apply(
    setter: Setter, db: AsyncSession, user: User, post_id: str, on: bool
) -> PostOut:
    post = await posts_service.get_post(db, post_id)
    await setter(db, user, post, on)
    return (await posts_service.serialize(db, [post], user))[0]


@router.put("/posts/{post_id}/like")
async def like(post_id: str, db: Db, user: CurrentUser) -> PostOut:
    return await _apply(service.set_like, db, user, post_id, True)


@router.delete("/posts/{post_id}/like")
async def unlike(post_id: str, db: Db, user: CurrentUser) -> PostOut:
    return await _apply(service.set_like, db, user, post_id, False)


@router.put("/posts/{post_id}/repost")
async def repost(post_id: str, db: Db, user: CurrentUser) -> PostOut:
    return await _apply(service.set_repost, db, user, post_id, True)


@router.delete("/posts/{post_id}/repost")
async def unrepost(post_id: str, db: Db, user: CurrentUser) -> PostOut:
    return await _apply(service.set_repost, db, user, post_id, False)


@router.put("/posts/{post_id}/bookmark")
async def bookmark(post_id: str, db: Db, user: CurrentUser) -> PostOut:
    return await _apply(service.set_bookmark, db, user, post_id, True)


@router.delete("/posts/{post_id}/bookmark")
async def unbookmark(post_id: str, db: Db, user: CurrentUser) -> PostOut:
    return await _apply(service.set_bookmark, db, user, post_id, False)


@router.get("/me/bookmarks")
async def bookmarks(
    db: Db,
    user: CurrentUser,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FeedPage:
    return await service.bookmarks_page(db, user, cursor, limit)
