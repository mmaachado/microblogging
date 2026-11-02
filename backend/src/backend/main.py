import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.auth.router import router as auth_router
from backend.auth.service import RegistrationLimiter
from backend.config import Settings, get_settings
from backend.db import create_engine
from backend.logging import configure_logging

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
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.add_middleware(
        OriginCheckMiddleware, allowed_origins=settings.allowed_origins
    )
    app.include_router(auth_router)

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
