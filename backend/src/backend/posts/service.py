import asyncio
import base64
import logging
import secrets
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped

from backend.auth.models import User
from backend.config import Settings
from backend.interactions.models import Bookmark, Like, Repost
from backend.media import InvalidMedia
from backend.media.images import open_image, to_post_image
from backend.media.storage import delete_media, save_bytes
from backend.media.video import (
    MIME_TYPES,
    VideoUnavailable,
    probe,
    strip_metadata,
)
from backend.posts.models import Media, Post, utcnow
from backend.posts.schemas import (
    FeedEntry,
    FeedPage,
    PostOut,
    QuotedPostOut,
)
from backend.users.schemas import PublicProfileOut

logger = logging.getLogger(__name__)

MAX_BODY = 120
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MINUTE_SECONDS = 60
DAY_SECONDS = 24 * 3600
CHUNK_BYTES = 1024 * 1024
VIDEO_ATOMS = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}
EBML_MAGIC = b"\x1a\x45\xdf\xa3"


class PostError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass
class Reservation:
    key: str
    at: float
    size: int = 0


class PostQuota:
    def __init__(
        self,
        posts_per_minute: int,
        bytes_per_day: int,
        max_keys: int = 10_000,
    ) -> None:
        self.posts_per_minute = posts_per_minute
        self.bytes_per_day = bytes_per_day
        self.max_keys = max_keys
        self._events: dict[str, list[Reservation]] = {}

    def _recent(self, key: str) -> list[Reservation]:
        cutoff = time.monotonic() - DAY_SECONDS
        recent = [e for e in self._events.get(key, []) if e.at > cutoff]
        if recent:
            self._events[key] = recent
        else:
            self._events.pop(key, None)
        return recent

    def reserve_post(self, key: str) -> Reservation:
        cutoff = time.monotonic() - MINUTE_SECONDS
        recent = [e for e in self._recent(key) if e.at > cutoff]
        if len(recent) >= self.posts_per_minute:
            logger.warning("post throttled")
            raise PostError(429, "too_many_posts")
        if key not in self._events and len(self._events) >= self.max_keys:
            day_cutoff = time.monotonic() - DAY_SECONDS
            for stale in [
                k for k, v in self._events.items() if v[-1].at <= day_cutoff
            ]:
                del self._events[stale]
            if len(self._events) >= self.max_keys:
                del self._events[next(iter(self._events))]
        reservation = Reservation(key, time.monotonic())
        self._events.setdefault(key, []).append(reservation)
        return reservation

    def reserve_bytes(self, reservation: Reservation, size: int) -> None:
        used = sum(e.size for e in self._recent(reservation.key))
        if used + size > self.bytes_per_day:
            logger.warning("upload quota exceeded")
            raise PostError(429, "upload_quota_exceeded")
        reservation.size = size

    def release(self, reservation: Reservation) -> None:
        events = self._events.get(reservation.key, [])
        if reservation in events:
            events.remove(reservation)
        if not events:
            self._events.pop(reservation.key, None)


@dataclass
class Limiters:
    image: asyncio.Semaphore
    video: asyncio.Semaphore


@dataclass
class Processed:
    kind: str
    path: str
    mime: str


def normalize_body(body: str, allow_empty: bool) -> str:
    text = body.replace("\r\n", "\n").strip()
    if len(text) > MAX_BODY:
        raise PostError(422, "post_too_long")
    if not text and not allow_empty:
        raise PostError(422, "post_empty")
    return text


def _looks_like_video(head: bytes) -> bool:
    return head[:4] == EBML_MAGIC or head[4:8] in VIDEO_ATOMS


def _sniff(path: Path) -> bool:
    with path.open("rb") as handle:
        return _looks_like_video(handle.read(8))


async def _spool(file: UploadFile, target: Path) -> None:
    limit = MAX_IMAGE_BYTES
    size = 0
    with target.open("wb") as handle:
        while chunk := await file.read(CHUNK_BYTES):
            if size == 0 and _looks_like_video(chunk):
                limit = MAX_VIDEO_BYTES
            size += len(chunk)
            if size > limit:
                raise PostError(413, "file_too_large")
            await asyncio.to_thread(handle.write, chunk)


@asynccontextmanager
async def spooled(
    files: Sequence[UploadFile], media_dir: str
) -> AsyncIterator[list[Path]]:
    tmp = Path(media_dir) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    try:
        for file in files:
            path = tmp / secrets.token_hex(16)
            paths.append(path)
            await _spool(file, path)
        yield paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def _process_image(data: bytes) -> bytes:
    return to_post_image(open_image(data))


async def _process_upload(
    upload: Path, settings: Settings, limiters: Limiters
) -> Processed:
    size = (await asyncio.to_thread(upload.stat)).st_size
    if size <= MAX_IMAGE_BYTES:
        data = await asyncio.to_thread(upload.read_bytes)
        try:
            async with limiters.image:
                encoded = await asyncio.to_thread(_process_image, data)
        except Exception as error:
            logger.debug("not an image: %s", type(error).__name__)
        else:
            path = await asyncio.to_thread(
                save_bytes, settings.media_dir, "posts", encoded, "webp"
            )
            return Processed("image", path, "image/webp")
    try:
        async with limiters.video:
            ext, codec = await asyncio.to_thread(
                probe, settings.ffprobe_path, upload
            )
            relative = f"posts/{secrets.token_hex(16)}.{ext}"
            await asyncio.to_thread(
                strip_metadata,
                settings.ffmpeg_path,
                upload,
                Path(settings.media_dir) / relative,
                ext,
                codec,
            )
    except VideoUnavailable as error:
        logger.info("media rejected: %s", type(error).__name__)
        raise PostError(503, "video_unavailable") from None
    except InvalidMedia as error:
        logger.info("media rejected: %s", type(error).__name__)
        raise PostError(422, "invalid_media") from None
    return Processed("video", relative, MIME_TYPES[ext])


def _discard(media_dir: str, saved: list[Processed]) -> None:
    for item in saved:
        try:
            delete_media(media_dir, item.path)
        except OSError:
            logger.warning("media cleanup failed")


async def create_post(
    db: AsyncSession,
    author: User,
    body: str,
    uploads: list[Path],
    settings: Settings,
    limiters: Limiters,
    quote_of_id: str | None = None,
) -> Post:
    text = normalize_body(body, bool(uploads) or quote_of_id is not None)
    quoted = None if quote_of_id is None else await get_post(db, quote_of_id)
    quoted_id = None if quoted is None else quoted.id
    if len(uploads) > MAX_IMAGES:
        raise PostError(422, "too_many_files")
    sniffed = [await asyncio.to_thread(_sniff, u) for u in uploads]
    videos = sum(sniffed)
    if videos > 1:
        raise PostError(422, "too_many_files")
    if videos and videos != len(uploads):
        raise PostError(422, "mixed_media")
    saved: list[Processed] = []
    try:
        for upload in uploads:
            item = await _process_upload(upload, settings, limiters)
            saved.append(item)
            videos = sum(1 for s in saved if s.kind == "video")
            if videos and videos != len(saved):
                raise PostError(422, "mixed_media")
            if videos > 1:
                raise PostError(422, "too_many_files")
        post = Post(
            author=author,
            body=text,
            quote_of_id=quoted_id,
            is_quote=quoted is not None,
            media=[
                Media(kind=s.kind, path=s.path, mime=s.mime, position=index)
                for index, s in enumerate(saved)
            ],
        )
        db.add(post)
        await db.commit()
    except BaseException as error:
        try:
            await db.rollback()
        finally:
            await asyncio.to_thread(_discard, settings.media_dir, saved)
        if (
            isinstance(error, IntegrityError)
            and quoted_id is not None
            and not await post_exists(db, quoted_id)
        ):
            raise PostError(404, "post_not_found") from None
        raise
    logger.info("post created")
    return post


async def get_post(db: AsyncSession, post_id: str) -> Post:
    try:
        key = UUID(post_id)
    except ValueError:
        raise PostError(404, "post_not_found") from None
    post = await db.get(Post, key)
    if post is None:
        raise PostError(404, "post_not_found")
    return post


async def post_exists(db: AsyncSession, key: UUID) -> bool:
    found = await db.scalar(select(Post.id).where(Post.id == key))
    return found is not None


async def edit_post(
    db: AsyncSession, user: User, post_id: str, body: str
) -> Post:
    post = await get_post(db, post_id)
    if post.author_id != user.id:
        raise PostError(403, "not_author")
    post.body = normalize_body(body, bool(post.media) or post.is_quote)
    post.edited_at = utcnow()
    await db.commit()
    logger.info("post edited")
    return post


async def delete_post(
    db: AsyncSession, user: User, post_id: str, media_dir: str
) -> None:
    post = await get_post(db, post_id)
    if post.author_id != user.id:
        raise PostError(403, "not_author")
    paths = [m.path for m in post.media]
    await db.delete(post)
    await db.commit()
    for path in paths:
        try:
            await asyncio.to_thread(delete_media, media_dir, path)
        except OSError:
            logger.warning("media cleanup failed")
    logger.info("post deleted")


def encode_cursor(*parts: object) -> str:
    raw = "|".join(
        p.isoformat() if isinstance(p, datetime) else str(p) for p in parts
    )
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_stamp(stamp: str) -> datetime:
    at = datetime.fromisoformat(stamp)
    if at.tzinfo is None:
        raise ValueError("naive cursor")
    return at.astimezone(UTC)


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, key = raw.split("|")
        return _decode_stamp(stamp), UUID(key)
    except (ValueError, OverflowError):
        raise PostError(422, "invalid_cursor") from None


def _decode_feed_cursor(cursor: str) -> tuple[datetime, str, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, kind, key = raw.split("|")
        if kind not in ("p", "r"):
            raise ValueError("kind")
        return _decode_stamp(stamp), kind, UUID(key)
    except (ValueError, OverflowError):
        raise PostError(422, "invalid_cursor") from None


async def posts_by_id(
    db: AsyncSession, ids: Sequence[UUID]
) -> dict[UUID, Post]:
    if not ids:
        return {}
    rows = await db.scalars(select(Post).where(Post.id.in_(ids)))
    return {p.id: p for p in rows}


async def _counts(
    db: AsyncSession,
    column: Mapped[UUID] | Mapped[UUID | None],
    ids: set[UUID],
) -> dict[UUID, int]:
    rows = await db.execute(
        select(column, func.count()).where(column.in_(ids)).group_by(column)
    )
    return {k: c for k, c in rows.all() if k is not None}


async def _viewer_ids(
    db: AsyncSession,
    model: type[Like | Repost | Bookmark],
    viewer: User,
    ids: set[UUID],
) -> set[UUID]:
    rows = await db.scalars(
        select(model.post_id).where(
            model.user_id == viewer.id, model.post_id.in_(ids)
        )
    )
    return set(rows)


async def serialize(
    db: AsyncSession, posts: Sequence[Post], viewer: User | None
) -> list[PostOut]:
    if not posts:
        return []
    ids = {p.id for p in posts}
    quoted = await posts_by_id(
        db, [p.quote_of_id for p in posts if p.quote_of_id is not None]
    )
    likes = await _counts(db, Like.post_id, ids)
    reposts = await _counts(db, Repost.post_id, ids)
    quotes = await _counts(db, Post.quote_of_id, ids)
    liked = reposted = bookmarked = set[UUID]()
    if viewer is not None:
        liked = await _viewer_ids(db, Like, viewer, ids)
        reposted = await _viewer_ids(db, Repost, viewer, ids)
        bookmarked = await _viewer_ids(db, Bookmark, viewer, ids)
    out: list[PostOut] = []
    for p in posts:
        embed = quoted.get(p.quote_of_id) if p.quote_of_id else None
        out.append(
            PostOut.model_validate(
                {
                    "id": p.id,
                    "author": p.author,
                    "body": p.body,
                    "media": p.media,
                    "created_at": p.created_at,
                    "edited_at": p.edited_at,
                    "like_count": likes.get(p.id, 0),
                    "repost_count": reposts.get(p.id, 0),
                    "quote_count": quotes.get(p.id, 0),
                    "liked": p.id in liked,
                    "reposted": p.id in reposted,
                    "bookmarked": p.id in bookmarked,
                    "quote": (
                        None
                        if embed is None
                        else QuotedPostOut.model_validate(embed)
                    ),
                    "quote_unavailable": p.is_quote and embed is None,
                }
            )
        )
    return out


async def feed_page(
    db: AsyncSession,
    entries: Sequence[tuple[Post, User | None]],
    next_cursor: str | None,
    viewer: User | None,
) -> FeedPage:
    outs = await serialize(db, [post for post, _ in entries], viewer)
    return FeedPage(
        items=[
            FeedEntry(
                post=out,
                reposted_by=(
                    None if by is None else PublicProfileOut.model_validate(by)
                ),
            )
            for out, (_, by) in zip(outs, entries, strict=True)
        ],
        next_cursor=next_cursor,
    )


async def timeline(
    db: AsyncSession, viewer: User | None, cursor: str | None, limit: int
) -> FeedPage:
    query = select(Post).order_by(Post.created_at.desc(), Post.id.desc())
    if cursor is not None:
        created_at, key = decode_cursor(cursor)
        query = query.where(
            or_(
                Post.created_at < created_at,
                and_(Post.created_at == created_at, Post.id < key),
            )
        )
    rows = list((await db.scalars(query.limit(limit + 1))).all())
    items = rows[:limit]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id)
        if len(rows) > limit
        else None
    )
    return await feed_page(db, [(p, None) for p in items], next_cursor, viewer)


async def user_feed(
    db: AsyncSession,
    user: User,
    viewer: User | None,
    cursor: str | None,
    limit: int,
) -> FeedPage:
    own = select(
        Post.created_at.label("at"),
        literal("p").label("kind"),
        Post.id.label("post_id"),
    ).where(Post.author_id == user.id)
    reposted = select(Repost.created_at, literal("r"), Repost.post_id).where(
        Repost.user_id == user.id
    )
    merged = union_all(own, reposted).subquery()
    query = select(merged.c.at, merged.c.kind, merged.c.post_id).order_by(
        merged.c.at.desc(), merged.c.kind.desc(), merged.c.post_id.desc()
    )
    if cursor is not None:
        at, kind, key = _decode_feed_cursor(cursor)
        query = query.where(
            or_(
                merged.c.at < at,
                and_(
                    merged.c.at == at,
                    or_(
                        merged.c.kind < kind,
                        and_(merged.c.kind == kind, merged.c.post_id < key),
                    ),
                ),
            )
        )
    rows = (await db.execute(query.limit(limit + 1))).all()
    page = rows[:limit]
    loaded = await posts_by_id(db, [row.post_id for row in page])
    next_cursor = encode_cursor(*page[-1]) if len(rows) > limit else None
    return await feed_page(
        db,
        [
            (loaded[row.post_id], user if row.kind == "r" else None)
            for row in page
            if row.post_id in loaded
        ],
        next_cursor,
        viewer,
    )
