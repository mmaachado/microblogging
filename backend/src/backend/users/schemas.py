import re
from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
)
from pydantic_core import PydanticCustomError

RESERVED_USERNAMES = frozenset(
    {
        "login",
        "register",
        "logout",
        "settings",
        "bookmarks",
        "home",
        "explore",
        "search",
        "notifications",
        "messages",
        "post",
        "posts",
        "api",
        "media",
        "graphql",
        "admin",
        "root",
        "support",
        "help",
        "about",
        "privacy",
        "terms",
    }
)
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,15}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{3,32}$")
MIN_BIRTHDAY = date(1900, 1, 1)


PROFILE_ERROR_CODES = frozenset(
    {
        "username_invalid",
        "username_reserved",
        "birthday_invalid",
        "phone_invalid",
    }
)


def _error(code: str) -> PydanticCustomError:
    return PydanticCustomError(code, code)


def _username(value: str) -> str:
    value = value.lower()
    if not USERNAME_RE.fullmatch(value):
        raise _error("username_invalid")
    if value in RESERVED_USERNAMES:
        raise _error("username_reserved")
    return value


def _birthday(value: date | None) -> date | None:
    if value is not None and not MIN_BIRTHDAY <= value <= date.today():
        raise _error("birthday_invalid")
    return value


def _phone(value: str | None) -> str | None:
    if value is None:
        return None
    if not PHONE_RE.fullmatch(value):
        raise _error("phone_invalid")
    return value


class AvatarMixin(BaseModel):
    avatar_path: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avatar_url(self) -> str | None:
        if self.avatar_path is None:
            return None
        return f"/media/{self.avatar_path}"


class PublicProfileOut(AvatarMixin):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str
    bio: str


class ProfileUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: Annotated[str, AfterValidator(_username)] = ""
    display_name: Annotated[str, Field(max_length=50)] = ""
    bio: Annotated[str, Field(max_length=160)] = ""
    birthday: Annotated[date | None, AfterValidator(_birthday)] = None
    phone: Annotated[str | None, AfterValidator(_phone)] = None
