import base64
import io
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from backend.config import Settings

POST_KEYS = {"id", "author", "body", "media", "created_at", "edited_at"}
AUTHOR_KEYS = {"username", "display_name", "bio", "avatar_url"}


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, "PNG")
    return buffer.getvalue()


async def make_post(
    client: httpx.AsyncClient, body: str = "hello", **extra: object
) -> httpx.Response:
    return await client.post("/api/v1/posts", data={"body": body}, **extra)  # type: ignore[arg-type]


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


@pytest.fixture
async def anonymous(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


async def test_create_text_post(authed: httpx.AsyncClient) -> None:
    response = await make_post(authed, "  first post  ")
    assert response.status_code == 201
    data = response.json()
    assert set(data) == POST_KEYS
    assert set(data["author"]) == AUTHOR_KEYS
    assert data["body"] == "first post"
    assert data["media"] == []
    assert data["edited_at"] is None
    assert data["created_at"].endswith(("Z", "+00:00"))


async def test_create_requires_auth(client: httpx.AsyncClient) -> None:
    response = await make_post(client)
    assert response.status_code == 401


async def test_body_limit_counts_code_points(
    authed: httpx.AsyncClient,
) -> None:
    assert (await make_post(authed, "\U0001f600" * 120)).status_code == 201
    response = await make_post(authed, "\U0001f600" * 121)
    assert response.status_code == 422
    assert response.json() == {"detail": "post_too_long"}


async def test_body_is_trimmed(authed: httpx.AsyncClient) -> None:
    response = await make_post(authed, " " * 5 + "a" * 120 + "\n ")
    assert response.status_code == 201
    assert response.json()["body"] == "a" * 120


async def test_crlf_line_breaks_are_normalized(
    authed: httpx.AsyncClient,
) -> None:
    body = "x" * 59 + "\r\n" + "y" * 60
    response = await make_post(authed, body)
    assert response.status_code == 201
    assert response.json()["body"] == "x" * 59 + "\n" + "y" * 60
    created = response.json()
    edited = await authed.patch(
        f"/api/v1/posts/{created['id']}", json={"body": body + "\r\nz"}
    )
    assert edited.status_code == 422
    ok = await authed.patch(
        f"/api/v1/posts/{created['id']}", json={"body": body}
    )
    assert ok.json()["body"] == "x" * 59 + "\n" + "y" * 60


async def test_empty_body_without_media_rejected(
    authed: httpx.AsyncClient,
) -> None:
    for body in ("", "   \n "):
        response = await make_post(authed, body)
        assert response.status_code == 422
        assert response.json() == {"detail": "post_empty"}
    response = await authed.post("/api/v1/posts")
    assert response.json() == {"detail": "post_empty"}


async def test_body_is_returned_verbatim(authed: httpx.AsyncClient) -> None:
    text = "<script>alert(1)</script> & <b>x</b>\nsecond line"
    created = (await make_post(authed, text)).json()
    assert created["body"] == text
    fetched = await authed.get(f"/api/v1/posts/{created['id']}")
    assert fetched.json()["body"] == text


async def test_get_post_public(
    authed: httpx.AsyncClient, anonymous: httpx.AsyncClient
) -> None:
    created = (await make_post(authed)).json()
    response = await anonymous.get(f"/api/v1/posts/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize(
    "post_id", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]
)
async def test_get_unknown_or_malformed_id_404(
    client: httpx.AsyncClient, post_id: str
) -> None:
    response = await client.get(f"/api/v1/posts/{post_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "post_not_found"}


async def test_edit_own_post_sets_edited_at(
    authed: httpx.AsyncClient,
) -> None:
    created = (await make_post(authed, "before")).json()
    response = await authed.patch(
        f"/api/v1/posts/{created['id']}", json={"body": " after "}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["body"] == "after"
    assert data["edited_at"] is not None
    assert data["edited_at"].endswith(("Z", "+00:00"))
    assert data["created_at"] == created["created_at"]
    fetched = (await authed.get(f"/api/v1/posts/{created['id']}")).json()
    assert fetched == data


async def test_edit_others_post_403(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    created = (await make_post(authed, "mine")).json()
    response = await other.patch(
        f"/api/v1/posts/{created['id']}", json={"body": "taken"}
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "not_author"}
    unknown = await other.patch(
        "/api/v1/posts/00000000-0000-0000-0000-000000000000",
        json={"body": "x"},
    )
    assert unknown.status_code == 404
    fetched = (await authed.get(f"/api/v1/posts/{created['id']}")).json()
    assert fetched["body"] == "mine"


async def test_edit_requires_auth(
    authed: httpx.AsyncClient, anonymous: httpx.AsyncClient
) -> None:
    created = (await make_post(authed)).json()
    response = await anonymous.patch(
        f"/api/v1/posts/{created['id']}", json={"body": "x"}
    )
    assert response.status_code == 401
    response = await anonymous.delete(f"/api/v1/posts/{created['id']}")
    assert response.status_code == 401


async def test_edit_validates_body(authed: httpx.AsyncClient) -> None:
    created = (await make_post(authed)).json()
    url = f"/api/v1/posts/{created['id']}"
    long = await authed.patch(url, json={"body": "x" * 121})
    assert long.status_code == 422
    assert long.json() == {"detail": "post_too_long"}
    empty = await authed.patch(url, json={"body": "  "})
    assert empty.status_code == 422
    assert empty.json() == {"detail": "post_empty"}


async def test_delete_own_post_removes_files(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    created = (
        await authed.post(
            "/api/v1/posts",
            data={"body": ""},
            files=[("files", ("a.png", png(), "image/png"))],
        )
    ).json()
    stored = Path(settings.media_dir) / created["media"][0][
        "url"
    ].removeprefix("/media/")
    assert stored.is_file()
    response = await authed.delete(f"/api/v1/posts/{created['id']}")
    assert response.status_code == 204
    assert not stored.exists()
    again = await authed.get(f"/api/v1/posts/{created['id']}")
    assert again.status_code == 404


async def test_delete_tolerates_cleanup_failure(
    authed: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    created = (
        await authed.post(
            "/api/v1/posts",
            files=[("files", ("a.png", png(), "image/png"))],
        )
    ).json()

    def failing(media_dir: str, relative_path: str) -> None:
        raise OSError("disk")

    from backend.posts import service

    monkeypatch.setattr(service, "delete_media", failing)
    response = await authed.delete(f"/api/v1/posts/{created['id']}")
    assert response.status_code == 204
    messages = [r.getMessage() for r in caplog.records]
    assert "media cleanup failed" in messages


async def test_delete_others_post_403(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    created = (await make_post(authed)).json()
    response = await other.delete(f"/api/v1/posts/{created['id']}")
    assert response.status_code == 403
    assert response.json() == {"detail": "not_author"}
    assert (
        await authed.get(f"/api/v1/posts/{created['id']}")
    ).status_code == 200
    missing = await other.delete(
        "/api/v1/posts/00000000-0000-0000-0000-000000000000"
    )
    assert missing.status_code == 404


async def test_timeline_order_and_pagination(
    authed: httpx.AsyncClient,
) -> None:
    ids = [
        (await make_post(authed, f"post {i}")).json()["id"] for i in range(5)
    ]
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = await authed.get("/api/v1/timeline", params=params)
        assert response.status_code == 200
        page = response.json()
        assert set(page) == {"items", "next_cursor"}
        seen.extend(item["id"] for item in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert seen == list(reversed(ids))


async def test_timeline_limit_bounds(client: httpx.AsyncClient) -> None:
    assert (
        await client.get("/api/v1/timeline", params={"limit": 0})
    ).status_code == 422
    assert (
        await client.get("/api/v1/timeline", params={"limit": 51})
    ).status_code == 422
    assert (await client.get("/api/v1/timeline")).json() == {
        "items": [],
        "next_cursor": None,
    }


async def test_timeline_cursor_overflow_422(
    client: httpx.AsyncClient,
) -> None:
    raw = "0001-01-01T00:00:00+05:00|00000000-0000-0000-0000-000000000000"
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    response = await client.get("/api/v1/timeline", params={"cursor": cursor})
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_cursor"}


@pytest.mark.parametrize(
    "cursor", ["!!!", "bm90LWEtY3Vyc29y", "MjAyNHx4", "", "x" * 400]
)
async def test_timeline_invalid_cursor_422(
    client: httpx.AsyncClient, cursor: str
) -> None:
    response = await client.get("/api/v1/timeline", params={"cursor": cursor})
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_cursor"}


async def test_user_posts_only_that_user(
    authed: httpx.AsyncClient, other: httpx.AsyncClient
) -> None:
    mine = (await make_post(authed, "mine")).json()
    await make_post(other, "theirs")
    username = mine["author"]["username"]
    response = await authed.get(f"/api/v1/users/{username}/posts")
    assert response.status_code == 200
    page = response.json()
    assert [item["id"] for item in page["items"]] == [mine["id"]]
    assert page["next_cursor"] is None


async def test_user_posts_unknown_user_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/users/nobody_here/posts")
    assert response.status_code == 404
    assert response.json() == {"detail": "user_not_found"}


async def test_timeline_is_public(
    authed: httpx.AsyncClient, anonymous: httpx.AsyncClient
) -> None:
    created = (await make_post(authed)).json()
    response = await anonymous.get("/api/v1/timeline")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [created["id"]]
