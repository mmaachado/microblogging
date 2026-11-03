import asyncio
import hashlib
import logging
import secrets
import string
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User, UserSession
from backend.auth.schemas import RegisterIn

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()
_ALPHABET = string.ascii_lowercase + string.digits
_DUMMY_HASH = _hasher.hash("dummy password for timing")


class NoticeNotAcknowledged(Exception):
    pass


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class TooManyAttempts(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


class LoginThrottle:
    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 900,
        max_keys: int = 10_000,
    ) -> None:
        self.max_keys = max_keys
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window_seconds
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def check(self, key: str) -> None:
        if len(self._recent(key)) >= self.max_failures:
            raise TooManyAttempts

    def record_failure(self, key: str) -> None:
        if key not in self._failures and len(self._failures) >= self.max_keys:
            cutoff = time.monotonic() - self.window_seconds
            for stale in [
                k for k, v in self._failures.items() if v[-1] <= cutoff
            ]:
                del self._failures[stale]
            if len(self._failures) >= self.max_keys:
                del self._failures[next(iter(self._failures))]
        self._recent(key)
        self._failures.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


class RegistrationLimiter:
    def __init__(self, rate_per_minute: int) -> None:
        self.rate_per_minute = rate_per_minute
        self._hits: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._hits and self._hits[0] <= now - 60:
            self._hits.popleft()
        if len(self._hits) >= self.rate_per_minute:
            raise TooManyAttempts
        self._hits.append(now)


login_throttle = LoginThrottle()


def get_login_throttle() -> LoginThrottle:
    return login_throttle


def _new_username() -> str:
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"user_{suffix}"


async def register(
    db: AsyncSession, data: RegisterIn, limiter: asyncio.Semaphore
) -> User:
    if not data.acknowledged_email_notice:
        raise NoticeNotAcknowledged
    email = data.email.lower()
    async with limiter:
        password_hash = await asyncio.to_thread(hash_password, data.password)
    while True:
        taken = await db.execute(select(User.id).where(User.email == email))
        if taken.first() is not None:
            raise EmailTaken
        user = User(
            email=email,
            password_hash=password_hash,
            username=_new_username(),
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue
        break
    await db.refresh(user)
    logger.info("user registered")
    return user


async def authenticate(
    db: AsyncSession,
    email: str,
    password: str,
    throttle: LoginThrottle,
    limiter: asyncio.Semaphore,
) -> User:
    key = email.lower()
    try:
        throttle.check(key)
    except TooManyAttempts:
        logger.warning("login throttled")
        raise
    throttle.record_failure(key)
    result = await db.execute(select(User).where(User.email == key))
    user = result.scalar_one_or_none()
    password_hash = _DUMMY_HASH if user is None else user.password_hash
    async with limiter:
        valid = await asyncio.to_thread(
            verify_password, password_hash, password
        )
    if user is not None and valid:
        throttle.reset(key)
        return user
    logger.info("login failed")
    raise InvalidCredentials


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db: AsyncSession, user: User, ttl_days: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_digest(token),
            expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
        )
    )
    await db.commit()
    return token


async def resolve_session(db: AsyncSession, token: str) -> User | None:
    result = await db.execute(
        select(UserSession).where(UserSession.token_hash == _digest(token))
    )
    session = result.scalar_one_or_none()
    await db.execute(
        delete(UserSession)
        .where(UserSession.expires_at <= datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if session is None:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    return await db.get(User, session.user_id)


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == _digest(token))
    )
    await db.commit()
