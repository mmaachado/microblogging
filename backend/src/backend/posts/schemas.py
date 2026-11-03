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


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author: PublicProfileOut
    body: str
    media: list[MediaOut]
    created_at: datetime
    edited_at: datetime | None


class PostEditIn(BaseModel):
    body: str


class PostPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None
