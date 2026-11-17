from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.posts.models import UTCDateTime, utcnow


class _Interaction:
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Like(_Interaction, Base):
    __tablename__ = "likes"


class Repost(_Interaction, Base):
    __tablename__ = "reposts"
    __table_args__ = (
        Index("ix_reposts_user_id_created_at", "user_id", "created_at"),
    )


class Bookmark(_Interaction, Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        Index("ix_bookmarks_user_id_created_at", "user_id", "created_at"),
    )
