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

from backend.auth.deps import current_user, get_app_settings, optional_user
from backend.auth.models import User
from backend.config import Settings
from backend.db import get_db
from backend.posts import service
from backend.posts.schemas import FeedPage, PostEditIn, PostOut
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
Viewer = Annotated[User | None, Depends(optional_user)]
Limiters = Annotated[service.Limiters, Depends(get_limiters)]
Quota = Annotated[service.PostQuota, Depends(get_post_quota)]
Cursor = Annotated[str | None, Query()]
Limit = Annotated[int, Query(ge=1, le=50)]


@router.post("/posts", status_code=201)
async def create_post(
    db: Db,
    user: CurrentUser,
    settings: AppSettings,
    limiters: Limiters,
    quota: Quota,
    body: Annotated[str, Form()] = "",
    quote_of_id: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> PostOut:
    reservation = quota.reserve_post(str(user.id))
    try:
        async with service.spooled(files or [], settings.media_dir) as uploads:
            quota.reserve_bytes(
                reservation, sum(u.stat().st_size for u in uploads)
            )
            post = await service.create_post(
                db, user, body, uploads, settings, limiters, quote_of_id
            )
    except BaseException:
        quota.release(reservation)
        raise
    return (await service.serialize(db, [post], user))[0]


@router.get("/posts/{post_id}")
async def get_post(post_id: str, db: Db, viewer: Viewer) -> PostOut:
    post = await service.get_post(db, post_id)
    return (await service.serialize(db, [post], viewer))[0]


@router.patch("/posts/{post_id}")
async def edit_post(
    post_id: str, data: PostEditIn, db: Db, user: CurrentUser
) -> PostOut:
    post = await service.edit_post(db, user, post_id, data.body)
    return (await service.serialize(db, [post], user))[0]


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str, db: Db, user: CurrentUser, settings: AppSettings
) -> Response:
    await service.delete_post(db, user, post_id, settings.media_dir)
    return Response(status_code=204)


@router.get("/timeline")
async def get_timeline(
    db: Db, viewer: Viewer, cursor: Cursor = None, limit: Limit = 20
) -> FeedPage:
    return await service.timeline(db, viewer, cursor, limit)


@router.get("/users/{username}/posts")
async def get_user_posts(
    username: str,
    db: Db,
    viewer: Viewer,
    cursor: Cursor = None,
    limit: Limit = 20,
) -> FeedPage:
    user = await users_service.get_by_username(db, username)
    if user is None:
        raise HTTPException(404, "user_not_found")
    return await service.user_feed(db, user, viewer, cursor, limit)
