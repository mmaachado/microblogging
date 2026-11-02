from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url, hide_parameters=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession]
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session
