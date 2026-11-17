from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.interactions import service as interactions_service
from backend.interactions.models import Bookmark, Like, Repost
from backend.posts import service as posts_service
from backend.posts.models import Post
from tests.test_posts import POST_KEYS, make_post

API = "/api/v1"
MISSING = "00000000-0000-0000-0000-000000000000"
FLAGS = ("liked", "reposted", "bookmarked")


@pytest.fixture
async def other(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"{API}/auth/register",
            json={
                "email": "second@example.com",
                "password": "a long enough password",
                "acknowledged_email_notice": True,
            },
        )
        assert response.status_code == 201
        yield client


@pytest.fixture
async def anonymous(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


async def username(client: httpx.AsyncClient) -> str:
    return str((await client.get(f"{API}/auth/me")).json()["username"])


async def test_like_toggle_is_idempotent(authed: httpx.AsyncClient) -> None:
    post = (await make_post(authed)).json()
    url = f"{API}/posts/{post['id']}/like"
    for _ in range(2):
        response = await authed.put(url)
        assert response.status_code == 200
        assert response.json()["like_count"] == 1
        assert response.json()["liked"] is True
    for _ in range(2):
        response = await authed.delete(url)
        assert response.status_code == 200
        assert response.json()["like_count"] == 0
        assert response.json()["liked"] is False


@pytest.mark.parametrize("action", ["like", "repost", "bookmark"])
async def test_like_requires_auth(
    authed: httpx.AsyncClient, anonymous: httpx.AsyncClient, action: str
) -> None:
    post = (await make_post(authed)).json()
    url = f"{API}/posts/{post['id']}/{action}"
    assert (await anonymous.put(url)).status_code == 401
    assert (await anonymous.delete(url)).status_code == 401
    assert (await anonymous.get(f"{API}/me/bookmarks")).status_code == 401


@pytest.mark.parametrize("action", ["like", "repost", "bookmark"])
@pytest.mark.parametrize("post_id", [MISSING, "not-a-uuid"])
async def test_like_missing_post_404(
    authed: httpx.AsyncClient, action: str, post_id: str
) -> None:
    for send in (authed.put, authed.delete):
        response = await send(f"{API}/posts/{post_id}/{action}")
        assert response.status_code == 404
        assert response.json() == {"detail": "post_not_found"}


async def test_counts_are_public_viewer_state_is_private(
    authed: httpx.AsyncClient,
    other: httpx.AsyncClient,
    anonymous: httpx.AsyncClient,
) -> None:
    post = (await make_post(authed)).json()
    url = f"{API}/posts/{post['id']}"
    for action in ("like", "repost", "bookmark"):
        assert (await authed.put(f"{url}/{action}")).status_code == 200
    seen = await anonymous.get(url)
    assert set(seen.json()) == POST_KEYS
    assert seen.json()["like_count"] == 1
    assert seen.json()["repost_count"] == 1
    assert all(seen.json()[flag] is False for flag in FLAGS)
    theirs = (await other.get(url)).json()
    assert set(theirs) == POST_KEYS
    assert theirs["like_count"] == 1
    assert all(theirs[flag] is False for flag in FLAGS)
    mine = (await authed.get(url)).json()
    assert set(mine) == POST_KEYS
    assert all(mine[flag] is True for flag in FLAGS)
    timeline = (await authed.get(f"{API}/timeline")).json()
    assert all(timeline["items"][0]["post"][f] is True for f in FLAGS)


async def test_bookmarks_are_private(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    post = (await make_post(authed)).json()
    saved = await authed.put(f"{API}/posts/{post['id']}/bookmark")
    assert saved.json()["bookmarked"] is True
    assert set(saved.json()) == POST_KEYS
    assert (await other.get(f"{API}/me/bookmarks")).json() == {
        "items": [],
        "next_cursor": None,
    }
    mine = (await authed.get(f"{API}/me/bookmarks")).json()
    assert [i["post"]["id"] for i in mine["items"]] == [post["id"]]
    assert mine["items"][0]["reposted_by"] is None
    assert mine["items"][0]["post"]["bookmarked"] is True
    removed = await authed.delete(f"{API}/posts/{post['id']}/bookmark")
    assert removed.json()["bookmarked"] is False
    assert (await authed.get(f"{API}/me/bookmarks")).json()["items"] == []


async def test_no_endpoint_lists_likers(app: FastAPI) -> None:
    for path, methods in app.openapi()["paths"].items():
        if "get" in methods:
            assert "likes" not in path
            assert "likers" not in path
            assert "reposters" not in path


async def test_repost_appears_on_reposter_feed_not_timeline(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    post = (await make_post(authed)).json()
    reposted = await other.put(f"{API}/posts/{post['id']}/repost")
    assert reposted.status_code == 200
    assert reposted.json()["repost_count"] == 1
    assert reposted.json()["reposted"] is True
    name = await username(other)
    feed = (await other.get(f"{API}/users/{name}/posts")).json()
    assert len(feed["items"]) == 1
    entry = feed["items"][0]
    assert entry["post"]["id"] == post["id"]
    assert entry["reposted_by"]["username"] == name
    timeline = (await other.get(f"{API}/timeline")).json()
    assert [i["post"]["id"] for i in timeline["items"]] == [post["id"]]
    assert timeline["items"][0]["reposted_by"] is None
    await other.delete(f"{API}/posts/{post['id']}/repost")
    after = (await other.get(f"{API}/users/{name}/posts")).json()
    assert after["items"] == []


async def test_user_feed_merges_posts_and_reposts_by_time(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    theirs = [
        (await make_post(authed, f"a{i}")).json()["id"] for i in range(3)
    ]
    mine1 = (await make_post(other, "b1")).json()["id"]
    await other.put(f"{API}/posts/{theirs[0]}/repost")
    mine2 = (await make_post(other, "b2")).json()["id"]
    await other.put(f"{API}/posts/{theirs[2]}/repost")
    name = await username(other)
    expected = [
        (theirs[2], True),
        (mine2, False),
        (theirs[0], True),
        (mine1, False),
    ]
    feed = (await other.get(f"{API}/users/{name}/posts")).json()
    assert [
        (i["post"]["id"], i["reposted_by"] is not None) for i in feed["items"]
    ] == expected
    seen: list[tuple[str, bool]] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (
            await other.get(f"{API}/users/{name}/posts", params=params)
        ).json()
        seen.extend(
            (i["post"]["id"], i["reposted_by"] is not None)
            for i in page["items"]
        )
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == expected


async def test_self_repost_and_user_feed_invalid_cursor(
    authed: httpx.AsyncClient,
) -> None:
    post = (await make_post(authed)).json()
    assert (
        await authed.put(f"{API}/posts/{post['id']}/repost")
    ).status_code == 200
    name = await username(authed)
    feed = (await authed.get(f"{API}/users/{name}/posts")).json()
    assert len(feed["items"]) == 2
    for url in (f"{API}/users/{name}/posts", f"{API}/me/bookmarks"):
        response = await authed.get(url, params={"cursor": "!!!"})
        assert response.status_code == 422
        assert response.json() == {"detail": "invalid_cursor"}


async def test_quote_post(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    original = (await make_post(authed, "original")).json()
    response = await other.post(
        f"{API}/posts",
        data={"body": "my take", "quote_of_id": original["id"]},
    )
    assert response.status_code == 201
    quote = response.json()
    assert quote["quote"]["author"] == original["author"]
    assert quote["quote"]["body"] == "original"
    assert quote["quote_unavailable"] is False
    assert set(quote["quote"]) == {
        "id",
        "author",
        "body",
        "media",
        "created_at",
        "edited_at",
        "is_quote",
    }
    fetched = (await other.get(f"{API}/posts/{original['id']}")).json()
    assert fetched["quote_count"] == 1
    assert fetched["quote"] is None
    assert fetched["quote_unavailable"] is False
    empty = await other.post(
        f"{API}/posts", data={"body": "", "quote_of_id": original["id"]}
    )
    assert empty.status_code == 201
    assert empty.json()["body"] == ""


async def test_quote_missing_post_404(authed: httpx.AsyncClient) -> None:
    for value in (MISSING, "not-a-uuid"):
        response = await authed.post(
            f"{API}/posts", data={"body": "x", "quote_of_id": value}
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "post_not_found"}


async def test_quote_of_deleted_post_shows_unavailable(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    original = (await make_post(authed)).json()
    quote = (
        await other.post(
            f"{API}/posts",
            data={"body": "", "quote_of_id": original["id"]},
        )
    ).json()
    assert (
        await authed.delete(f"{API}/posts/{original['id']}")
    ).status_code == 204
    fetched = await other.get(f"{API}/posts/{quote['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["quote"] is None
    assert fetched.json()["quote_unavailable"] is True
    timeline = (await other.get(f"{API}/timeline")).json()
    assert timeline["items"][0]["post"]["quote_unavailable"] is True


async def test_quote_embed_is_one_level(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    original = (await make_post(authed, "root")).json()
    middle = (
        await other.post(
            f"{API}/posts",
            data={"body": "middle", "quote_of_id": original["id"]},
        )
    ).json()
    top = (
        await authed.post(
            f"{API}/posts",
            data={"body": "top", "quote_of_id": middle["id"]},
        )
    ).json()
    assert top["quote"]["id"] == middle["id"]
    assert top["quote"]["is_quote"] is True
    assert "quote" not in top["quote"]
    assert "quote_unavailable" not in top["quote"]
    plain = (await authed.get(f"{API}/posts/{original['id']}")).json()
    assert plain["quote_count"] == 1


async def test_deleting_post_removes_interactions(
    authed: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    post = (await make_post(authed)).json()
    for action in ("like", "repost", "bookmark"):
        await authed.put(f"{API}/posts/{post['id']}/{action}")
    async with sessionmaker() as db:
        for model in (Like, Repost, Bookmark):
            count = await db.scalar(select(func.count()).select_from(model))
            assert count == 1
    await authed.delete(f"{API}/posts/{post['id']}")
    async with sessionmaker() as db:
        for model in (Like, Repost, Bookmark):
            count = await db.scalar(select(func.count()).select_from(model))
            assert count == 0


async def test_bookmarks_pagination(authed: httpx.AsyncClient) -> None:
    ids = [(await make_post(authed, f"p{i}")).json()["id"] for i in range(5)]
    for post_id in [ids[2], ids[0], ids[4], ids[1], ids[3]]:
        await authed.put(f"{API}/posts/{post_id}/bookmark")
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (await authed.get(f"{API}/me/bookmarks", params=params)).json()
        seen.extend(i["post"]["id"] for i in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert seen == [ids[3], ids[1], ids[4], ids[0], ids[2]]


async def timeline_statements(
    app: FastAPI, client: httpx.AsyncClient, size: int
) -> int:
    count = 0

    def counter(*_: object) -> None:
        nonlocal count
        count += 1

    sync_engine = app.state.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", counter)
    try:
        response = await client.get(f"{API}/timeline", params={"limit": size})
    finally:
        event.remove(sync_engine, "before_cursor_execute", counter)
    assert len(response.json()["items"]) == size
    return count


async def test_page_queries_are_bounded(
    app: FastAPI,
    authed: httpx.AsyncClient,
    other: httpx.AsyncClient,
) -> None:
    ids = [(await make_post(authed, f"p{i}")).json()["id"] for i in range(10)]
    for post_id in ids:
        await other.put(f"{API}/posts/{post_id}/like")
        await other.put(f"{API}/posts/{post_id}/repost")
        await other.put(f"{API}/posts/{post_id}/bookmark")
    for post_id in ids:
        await other.post(
            f"{API}/posts", data={"body": "q", "quote_of_id": post_id}
        )
    for post_id in ids:
        await authed.put(f"{API}/posts/{post_id}/like")
    small = await timeline_statements(app, authed, 5)
    assert small > 0
    large = await timeline_statements(app, authed, 20)
    assert large <= small


async def test_concurrent_like_is_idempotent(
    authed: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = (await make_post(authed)).json()
    real_get = AsyncSession.get

    async def racing(
        self: AsyncSession,
        entity: type[object],
        ident: tuple[UUID, UUID],
        **kw: Any,
    ) -> object:
        found = await real_get(self, entity, ident, **kw)
        if entity is Like and found is None:
            user_id, post_id = ident
            async with sessionmaker() as other:
                other.add(Like(user_id=user_id, post_id=post_id))
                await other.commit()
        return found

    monkeypatch.setattr(AsyncSession, "get", racing)
    response = await authed.put(f"{API}/posts/{post['id']}/like")
    assert response.status_code == 200
    assert response.json()["like_count"] == 1
    assert response.json()["liked"] is True


async def _vanish_before_load(
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    original = posts_service.posts_by_id

    async def vanishing(db: AsyncSession, ids: list[UUID]) -> dict[UUID, Post]:
        async with sessionmaker() as other:
            await other.execute(delete(Post).where(Post.id.in_(ids)))
            await other.commit()
        return await original(db, ids)

    monkeypatch.setattr(module, "posts_by_id", vanishing)


async def test_user_feed_skips_post_deleted_mid_request(
    authed: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await make_post(authed)
    name = await username(authed)
    await _vanish_before_load(sessionmaker, monkeypatch, posts_service)
    response = await authed.get(f"{API}/users/{name}/posts")
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_bookmarks_skip_post_deleted_mid_request(
    authed: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = (await make_post(authed)).json()
    await authed.put(f"{API}/posts/{post['id']}/bookmark")
    await _vanish_before_load(sessionmaker, monkeypatch, interactions_service)
    response = await authed.get(f"{API}/me/bookmarks")
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_toggle_on_post_deleted_mid_request_404(
    authed: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = (await make_post(authed)).json()
    original = posts_service.get_post

    async def vanishing(db: AsyncSession, post_id: str) -> Post:
        found = await original(db, post_id)
        async with sessionmaker() as other:
            await other.execute(delete(Post).where(Post.id == found.id))
            await other.commit()
        return found

    monkeypatch.setattr(posts_service, "get_post", vanishing)
    response = await authed.put(f"{API}/posts/{post['id']}/like")
    assert response.status_code == 404
    assert response.json() == {"detail": "post_not_found"}


async def test_quote_target_deleted_mid_request_404(
    authed: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = (await make_post(authed)).json()
    original = posts_service.get_post

    async def vanishing(db: AsyncSession, post_id: str) -> Post:
        found = await original(db, post_id)
        async with sessionmaker() as other:
            await other.execute(delete(Post).where(Post.id == found.id))
            await other.commit()
        return found

    monkeypatch.setattr(posts_service, "get_post", vanishing)
    response = await authed.post(
        f"{API}/posts", data={"body": "q", "quote_of_id": post["id"]}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "post_not_found"}
