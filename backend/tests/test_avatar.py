import io
import logging
import struct
import zlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.media.storage import delete_media
from backend.users import service


def jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (600, 300), "green")
    exif = Image.Exif()
    exif[0x010F] = "SecretMaker"
    exif.get_ifd(0x8825)[2] = (1.0, 2.0, 3.0)
    exif.get_ifd(0x8825)[1] = "N"
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


async def put_avatar(client: httpx.AsyncClient, data: bytes) -> httpx.Response:
    return await client.put(
        "/api/v1/me/avatar",
        files={"file": ("photo.jpg", data, "application/octet-stream")},
    )


async def test_avatar_upload_strips_metadata(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    source = jpeg_with_exif()
    assert 0x8825 in Image.open(io.BytesIO(source)).getexif()
    response = await put_avatar(authed, source)
    assert response.status_code == 200
    url = response.json()["avatar_url"]
    assert url.startswith("/media/avatars/")
    stored = Path(settings.media_dir) / url.removeprefix("/media/")
    assert stored.is_file()
    with Image.open(stored) as image:
        assert image.format == "WEBP"
        assert image.size == (400, 400)
        assert not image.getexif()
        assert "icc_profile" not in image.info
    assert b"SecretMaker" not in stored.read_bytes()


async def test_avatar_respects_exif_orientation(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    image = Image.new("RGB", (200, 100), "red")
    image.paste("blue", (100, 0, 200, 100))
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    image.save(buffer, "PNG", exif=exif)
    response = await put_avatar(authed, buffer.getvalue())
    url = response.json()["avatar_url"]
    stored = Path(settings.media_dir) / url.removeprefix("/media/")
    with Image.open(stored).convert("RGB") as out:
        for x in (100, 300):
            top = out.getpixel((x, 20))
            bottom = out.getpixel((x, 380))
            assert isinstance(top, tuple)
            assert isinstance(bottom, tuple)
            assert top[0] > 200 and top[2] < 60
            assert bottom[2] > 200 and bottom[0] < 60


async def test_avatar_replace_deletes_old_file(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    first = (await put_avatar(authed, jpeg_with_exif())).json()["avatar_url"]
    old = Path(settings.media_dir) / first.removeprefix("/media/")
    assert old.is_file()
    second = (await put_avatar(authed, jpeg_with_exif())).json()["avatar_url"]
    assert second != first
    assert not old.exists()
    assert (
        Path(settings.media_dir) / second.removeprefix("/media/")
    ).is_file()
    me = (await authed.get("/api/v1/auth/me")).json()
    assert me["avatar_url"] == second


async def test_avatar_remove(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    url = (await put_avatar(authed, jpeg_with_exif())).json()["avatar_url"]
    stored = Path(settings.media_dir) / url.removeprefix("/media/")
    response = await authed.delete("/api/v1/me/avatar")
    assert response.status_code == 200
    assert response.json()["avatar_url"] is None
    assert not stored.exists()
    again = await authed.delete("/api/v1/me/avatar")
    assert again.status_code == 200


async def test_avatar_remove_tolerates_missing_file(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    url = (await put_avatar(authed, jpeg_with_exif())).json()["avatar_url"]
    (Path(settings.media_dir) / url.removeprefix("/media/")).unlink()
    response = await authed.delete("/api/v1/me/avatar")
    assert response.status_code == 200
    assert response.json()["avatar_url"] is None


async def test_avatar_requires_auth(client: httpx.AsyncClient) -> None:
    response = await put_avatar(client, jpeg_with_exif())
    assert response.status_code == 401


async def test_avatar_rejects_non_image(authed: httpx.AsyncClient) -> None:
    response = await put_avatar(authed, b"definitely not an image")
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_image"}


async def test_avatar_rejects_oversized(authed: httpx.AsyncClient) -> None:
    response = await put_avatar(authed, b"0" * (5 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json() == {"detail": "file_too_large"}


def png_declaring(width: int, height: int) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body)
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize("size", [(20000, 20000), (7100, 7100)])
async def test_avatar_rejects_decompression_bomb(
    authed: httpx.AsyncClient, size: tuple[int, int]
) -> None:
    response = await put_avatar(authed, png_declaring(*size))
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_image"}


async def test_avatar_rejection_logs_reason_without_identifiers(
    authed: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    await put_avatar(authed, b"not an image")
    messages = [r.getMessage() for r in caplog.records]
    assert "avatar rejected: UnidentifiedImageError" in messages


async def test_oversized_declared_length_rejected_without_auth(
    client: httpx.AsyncClient,
) -> None:
    response = await client.put(
        "/api/v1/me/avatar",
        content=b"x",
        headers={"Content-Length": str(6 * 1024 * 1024)},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "file_too_large"}


async def test_oversized_chunked_body_rejected(
    client: httpx.AsyncClient,
) -> None:
    async def body() -> AsyncIterator[bytes]:
        yield (
            b"--x\r\nContent-Disposition: form-data; "
            b'name="file"; filename="a.jpg"\r\n\r\n'
        )
        for _ in range(8):
            yield b"x" * (1024 * 1024)

    response = await client.put(
        "/api/v1/me/avatar",
        content=body(),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "file_too_large"}


async def test_failed_commit_removes_new_file(
    authed: httpx.AsyncClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    avatars = Path(settings.media_dir) / "avatars"

    async def failing_commit(self: AsyncSession) -> None:
        if avatars.exists() and any(avatars.iterdir()):
            raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        await put_avatar(authed, jpeg_with_exif())
    assert list(avatars.iterdir()) == []


async def test_old_file_cleanup_failure_does_not_fail_request(
    authed: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_avatar(authed, jpeg_with_exif())

    def failing(media_dir: str, relative_path: str) -> None:
        raise OSError("disk")

    monkeypatch.setattr(service, "delete_media", failing)
    replaced = await put_avatar(authed, jpeg_with_exif())
    assert replaced.status_code == 200
    removed = await authed.delete("/api/v1/me/avatar")
    assert removed.status_code == 200
    assert removed.json()["avatar_url"] is None


async def test_media_is_served(authed: httpx.AsyncClient) -> None:
    url = (await put_avatar(authed, jpeg_with_exif())).json()["avatar_url"]
    response = await authed.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'"


async def test_media_has_no_directory_listing(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/media/avatars/")
    assert response.status_code == 404


def test_delete_media_refuses_path_outside_media_dir(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("keep")
    with pytest.raises(ValueError):
        delete_media(str(media), "../secret.txt")
    assert outside.exists()
