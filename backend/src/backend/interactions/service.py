import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.interactions.models import Bookmark, Like, Repost
from backend.posts.models import Post
from backend.posts.schemas import FeedPage
from backend.posts.service import (
    PostError,
    decode_cursor,
    encode_cursor,
    feed_page,
    post_exists,
    posts_by_id,
)

logger = logging.getLogger(__name__)


async def _set(
    db: AsyncSession,
    model: type[Like | Repost | Bookmark],
    user: User,
    post: Post,
    on: bool,
) -> bool:
    post_id = post.id
    existing = await db.get(model, (user.id, post_id))
    if on == (existing is not None):
        return False
    if existing is not None:
        await db.delete(existing)
    else:
        db.add(model(user_id=user.id, post_id=post_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if not await post_exists(db, post_id):
            raise PostError(404, "post_not_found") from None
        await db.refresh(user)
        await db.refresh(post)
        return False
    return True


def _toggle(
    model: type[Like | Repost | Bookmark], added: str, removed: str
) -> Callable[[AsyncSession, User, Post, bool], Awaitable[None]]:
    async def toggle(
        db: AsyncSession, user: User, post: Post, on: bool
    ) -> None:
        if await _set(db, model, user, post, on):
            logger.debug(added if on else removed)

    return toggle


set_like = _toggle(Like, "post liked", "post unliked")
set_repost = _toggle(Repost, "post reposted", "repost undone")
set_bookmark = _toggle(Bookmark, "post bookmarked", "bookmark removed")


async def bookmarks_page(
    db: AsyncSession, user: User, cursor: str | None, limit: int
) -> FeedPage:
    query = (
        select(Bookmark.created_at, Bookmark.post_id)
        .where(Bookmark.user_id == user.id)
        .order_by(Bookmark.created_at.desc(), Bookmark.post_id.desc())
    )
    if cursor is not None:
        at, key = decode_cursor(cursor)
        query = query.where(
            or_(
                Bookmark.created_at < at,
                and_(Bookmark.created_at == at, Bookmark.post_id < key),
            )
        )
    rows = (await db.execute(query.limit(limit + 1))).all()
    page = rows[:limit]
    loaded = await posts_by_id(db, [row.post_id for row in page])
    next_cursor = encode_cursor(*page[-1]) if len(rows) > limit else None
    return await feed_page(
        db,
        [(loaded[row.post_id], None) for row in page if row.post_id in loaded],
        next_cursor,
        user,
    )
