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
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.config import Settings
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


def normalize_body(body: str, has_media: bool) -> str:
    text = body.replace("\r\n", "\n").strip()
    if len(text) > MAX_BODY:
        raise PostError(422, "post_too_long")
    if not text and not has_media:
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
) -> Post:
    text = normalize_body(body, bool(uploads))
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
            media=[
                Media(kind=s.kind, path=s.path, mime=s.mime, position=index)
                for index, s in enumerate(saved)
            ],
        )
        db.add(post)
        await db.commit()
    except BaseException:
        try:
            await db.rollback()
        finally:
            await asyncio.to_thread(_discard, settings.media_dir, saved)
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


async def edit_post(
    db: AsyncSession, user: User, post_id: str, body: str
) -> Post:
    post = await get_post(db, post_id)
    if post.author_id != user.id:
        raise PostError(403, "not_author")
    post.body = normalize_body(body, bool(post.media))
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


def encode_cursor(post: Post) -> str:
    raw = f"{post.created_at.isoformat()}|{post.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, key = raw.split("|")
        created_at = datetime.fromisoformat(stamp)
        if created_at.tzinfo is None:
            raise ValueError("naive cursor")
        return created_at.astimezone(UTC), UUID(key)
    except (ValueError, OverflowError):
        raise PostError(422, "invalid_cursor") from None


async def _page(
    db: AsyncSession,
    cursor: str | None,
    limit: int,
    author: User | None = None,
) -> tuple[list[Post], str | None]:
    query = select(Post).order_by(Post.created_at.desc(), Post.id.desc())
    if author is not None:
        query = query.where(Post.author_id == author.id)
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
    next_cursor = encode_cursor(items[-1]) if len(rows) > limit else None
    return items, next_cursor


async def timeline(
    db: AsyncSession, cursor: str | None, limit: int
) -> tuple[list[Post], str | None]:
    return await _page(db, cursor, limit)


async def user_posts(
    db: AsyncSession, user: User, cursor: str | None, limit: int
) -> tuple[list[Post], str | None]:
    return await _page(db, cursor, limit, user)
