from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import current_user, get_app_settings
from backend.auth.models import User
from backend.config import Settings
from backend.db import get_db
from backend.posts import service
from backend.posts.models import Post
from backend.posts.schemas import PostEditIn, PostOut, PostPage
from backend.users import service as users_service

router = APIRouter(prefix="/api/v1", tags=["posts"])


def get_limiters(request: Request) -> service.Limiters:
    state = request.app.state
    return service.Limiters(
        image=state.image_limiter, video=state.video_limiter
    )


def get_post_quota(request: Request) -> service.PostQuota:
    quota: service.PostQuota = request.app.state.post_quota
    return quota


Db = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
CurrentUser = Annotated[User, Depends(current_user)]
Limiters = Annotated[service.Limiters, Depends(get_limiters)]
Quota = Annotated[service.PostQuota, Depends(get_post_quota)]
Cursor = Annotated[str | None, Query()]
Limit = Annotated[int, Query(ge=1, le=50)]


def _page(items: list[Post], next_cursor: str | None) -> PostPage:
    return PostPage(
        items=[PostOut.model_validate(p) for p in items],
        next_cursor=next_cursor,
    )


@router.post("/posts", status_code=201)
async def create_post(
    db: Db,
    user: CurrentUser,
    settings: AppSettings,
    limiters: Limiters,
    quota: Quota,
    body: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> PostOut:
    reservation = quota.reserve_post(str(user.id))
    try:
        async with service.spooled(files or [], settings.media_dir) as uploads:
            quota.reserve_bytes(
                reservation, sum(u.stat().st_size for u in uploads)
            )
            post = await service.create_post(
                db, user, body, uploads, settings, limiters
            )
    except BaseException:
        quota.release(reservation)
        raise
    return PostOut.model_validate(post)


@router.get("/posts/{post_id}")
async def get_post(post_id: str, db: Db) -> PostOut:
    return PostOut.model_validate(await service.get_post(db, post_id))


@router.patch("/posts/{post_id}")
async def edit_post(
    post_id: str, data: PostEditIn, db: Db, user: CurrentUser
) -> PostOut:
    post = await service.edit_post(db, user, post_id, data.body)
    return PostOut.model_validate(post)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str, db: Db, user: CurrentUser, settings: AppSettings
) -> Response:
    await service.delete_post(db, user, post_id, settings.media_dir)
    return Response(status_code=204)


@router.get("/timeline")
async def get_timeline(
    db: Db, cursor: Cursor = None, limit: Limit = 20
) -> PostPage:
    return _page(*await service.timeline(db, cursor, limit))


@router.get("/users/{username}/posts")
async def get_user_posts(
    username: str, db: Db, cursor: Cursor = None, limit: Limit = 20
) -> PostPage:
    user = await users_service.get_by_username(db, username)
    if user is None:
        raise HTTPException(404, "user_not_found")
    return _page(*await service.user_posts(db, user, cursor, limit))
