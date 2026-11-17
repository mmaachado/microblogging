from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.users.schemas import PublicProfileOut


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    mime: str
    path: str = Field(exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"/media/{self.path}"


class QuotedPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author: PublicProfileOut
    body: str
    media: list[MediaOut]
    created_at: datetime
    edited_at: datetime | None
    is_quote: bool


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author: PublicProfileOut
    body: str
    media: list[MediaOut]
    created_at: datetime
    edited_at: datetime | None
    like_count: int
    repost_count: int
    quote_count: int
    liked: bool
    reposted: bool
    bookmarked: bool
    quote: QuotedPostOut | None
    quote_unavailable: bool


class PostEditIn(BaseModel):
    body: str


class FeedEntry(BaseModel):
    post: PostOut
    reposted_by: PublicProfileOut | None


class FeedPage(BaseModel):
    items: list[FeedEntry]
    next_cursor: str | None
