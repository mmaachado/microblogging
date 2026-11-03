from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.users.schemas import AvatarMixin


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    acknowledged_email_notice: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class MeOut(AvatarMixin):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    display_name: str
    bio: str
    birthday: date | None
    phone: str | None
    created_at: datetime
