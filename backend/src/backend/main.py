import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.auth.router import router as auth_router
from backend.auth.service import RegistrationLimiter
from backend.config import Settings, get_settings
from backend.db import create_engine
from backend.logging import configure_logging
from backend.posts.router import router as posts_router
from backend.posts.service import MAX_VIDEO_BYTES, PostError, PostQuota
from backend.users.router import MAX_AVATAR_BYTES
from backend.users.router import router as users_router
from backend.users.schemas import PROFILE_ERROR_CODES

AVATAR_PATH = "/api/v1/me/avatar"
AVATAR_BODY_LIMIT = MAX_AVATAR_BYTES + 64 * 1024
POSTS_PATH = "/api/v1/posts"
POSTS_BODY_LIMIT = MAX_VIDEO_BYTES + 256 * 1024

STALE_TMP_SECONDS = 3600

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self.allowed_origins = allowed_origins

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method in MUTATING
            and origin is not None
            and origin not in self.allowed_origins
        ):
            return JSONResponse(
                {"detail": "origin_not_allowed"}, status_code=403
            )
        return await call_next(request)


class MediaHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/media"):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Content-Security-Policy"] = "default-src 'none'"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        default_limit: int,
        route_limits: dict[tuple[str, str], int],
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.route_limits = route_limits

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route = (scope["method"], scope["path"])
        limit = self.route_limits.get(route, self.default_limit)
        detail = (
            "file_too_large"
            if route in self.route_limits
            else "request_too_large"
        )
        rejection = JSONResponse({"detail": detail}, status_code=413)
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await rejection(scope, receive, send)
            return
        received = 0
        exceeded = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not exceeded:
                await send(message)

        await self.app(scope, counting_receive, guarded_send)
        if exceeded:
            await rejection(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.registration_limiter = RegistrationLimiter(
        settings.registration_rate_per_minute
    )
    app.state.hash_limiter = asyncio.Semaphore(
        settings.password_hash_concurrency
    )
    app.state.image_limiter = asyncio.Semaphore(
        settings.image_processing_concurrency
    )
    app.state.video_limiter = asyncio.Semaphore(
        settings.video_processing_concurrency
    )
    app.state.post_quota = PostQuota(
        settings.posts_per_minute, settings.upload_bytes_per_day
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.add_middleware(
        OriginCheckMiddleware, allowed_origins=settings.allowed_origins
    )
    app.add_middleware(MediaHeadersMiddleware)
    app.add_middleware(
        BodyLimitMiddleware,
        default_limit=settings.max_request_bytes,
        route_limits={
            ("PUT", AVATAR_PATH): AVATAR_BODY_LIMIT,
            ("POST", POSTS_PATH): POSTS_BODY_LIMIT,
        },
    )
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(posts_router)

    @app.exception_handler(PostError)
    async def post_error(_: Request, exc: PostError) -> Response:
        return JSONResponse({"detail": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        for error in exc.errors():
            if error["type"] in PROFILE_ERROR_CODES:
                return JSONResponse({"detail": error["type"]}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    for subdir in ("tmp", "posts"):
        (Path(settings.media_dir) / subdir).mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - STALE_TMP_SECONDS
    for leftover in (Path(settings.media_dir) / "tmp").iterdir():
        if leftover.is_file() and leftover.stat().st_mtime < cutoff:
            leftover.unlink(missing_ok=True)
    app.mount(
        "/media", StaticFiles(directory=settings.media_dir), name="media"
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
