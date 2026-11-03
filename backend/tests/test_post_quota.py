import asyncio
import io
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from backend.config import Settings
from backend.posts import service
from backend.posts.service import PostError, PostQuota


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"posts_per_minute": 2, "upload_bytes_per_day": 5000}
    )


@pytest.fixture
async def other(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "second@example.com",
                "password": "a long enough password",
                "acknowledged_email_notice": True,
            },
        )
        assert response.status_code == 201
        yield client


async def post(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/api/v1/posts", data={"body": "hi"})


async def test_third_post_in_a_minute_is_throttled(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    assert (await post(authed)).status_code == 201
    assert (await post(authed)).status_code == 201
    response = await post(authed)
    assert response.status_code == 429
    assert response.json() == {"detail": "too_many_posts"}
    assert (await post(other)).status_code == 201


async def test_window_frees_after_a_minute(
    authed: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(
        service, "time", SimpleNamespace(monotonic=lambda: now[0])
    )
    await post(authed)
    await post(authed)
    assert (await post(authed)).status_code == 429
    now[0] += 61
    assert (await post(authed)).status_code == 201


async def test_upload_budget_is_enforced(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    response = await authed.post(
        "/api/v1/posts",
        files=[("files", ("a.bin", b"0" * 6000, "image/png"))],
    )
    assert response.status_code == 429
    assert response.json() == {"detail": "upload_quota_exceeded"}
    media = Path(settings.media_dir)
    assert list((media / "tmp").iterdir()) == []
    assert list((media / "posts").iterdir()) == []


def test_oldest_key_is_evicted_when_full() -> None:
    quota = PostQuota(posts_per_minute=1, bytes_per_day=100, max_keys=2)
    handles = {key: quota.reserve_post(key) for key in ("a", "b", "c")}
    quota.reserve_post("a")
    with pytest.raises(PostError):
        quota.reserve_post("c")
    quota.reserve_bytes(handles["c"], 95)
    with pytest.raises(PostError):
        quota.reserve_bytes(handles["c"], 10)


def tiny_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, "PNG")
    return buffer.getvalue()


async def test_concurrent_posts_respect_the_window(
    authed: httpx.AsyncClient, app: FastAPI
) -> None:
    app.state.post_quota = PostQuota(3, 10**9)
    data = tiny_png()
    responses = await asyncio.gather(
        *(
            authed.post(
                "/api/v1/posts",
                files=[("files", ("a.png", data, "image/png"))],
            )
            for _ in range(10)
        )
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [201] * 3 + [429] * 7
    assert {r.json()["detail"] for r in responses if r.status_code == 429} == {
        "too_many_posts"
    }


async def test_concurrent_uploads_respect_the_byte_budget(
    authed: httpx.AsyncClient, app: FastAPI
) -> None:
    data = tiny_png()
    app.state.post_quota = PostQuota(100, len(data) + len(data) // 2)
    responses = await asyncio.gather(
        *(
            authed.post(
                "/api/v1/posts",
                files=[("files", ("a.png", data, "image/png"))],
            )
            for _ in range(3)
        )
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 429, 429]


async def test_failed_create_releases_its_reservation(
    authed: httpx.AsyncClient, app: FastAPI
) -> None:
    app.state.post_quota = PostQuota(1, 10**9)
    bad = await authed.post(
        "/api/v1/posts", files=[("files", ("a.png", b"garbage", "image/png"))]
    )
    assert bad.status_code == 422
    assert (await post(authed)).status_code == 201
    assert (await post(authed)).status_code == 429
