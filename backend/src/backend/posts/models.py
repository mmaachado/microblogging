from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    TypeDecorator,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.auth.models import User
from backend.db import Base


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        return None if value is None else value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_created_at_id", "created_at", "id"),
        Index(
            "ix_posts_author_created_at_id", "author_id", "created_at", "id"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(
        String(120), default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    author: Mapped[User] = relationship(lazy="selectin")
    media: Mapped[list["Media"]] = relationship(
        order_by="Media.position",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class Media(Base):
    __tablename__ = "media"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(5))
    path: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(SmallInteger)
