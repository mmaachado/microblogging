import io
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import Settings
from backend.db import Base
from backend.main import create_app
from backend.posts.models import Post

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg is not installed",
)


def jpeg_with_gps(size: tuple[int, int] = (64, 48)) -> bytes:
    image = Image.new("RGB", size, "green")
    exif = Image.Exif()
    exif[0x010F] = "SecretMaker"
    exif.get_ifd(0x8825)[2] = (1.0, 2.0, 3.0)
    exif.get_ifd(0x8825)[1] = "N"
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def image_part(
    data: bytes, name: str = "photo.jpg"
) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data, "application/octet-stream"))


def stored_path(settings: Settings, url: str) -> Path:
    return Path(settings.media_dir) / url.removeprefix("/media/")


def leftovers(settings: Settings) -> list[Path]:
    media = Path(settings.media_dir)
    return [
        item for sub in ("posts", "tmp") for item in (media / sub).iterdir()
    ]


async def test_post_with_images_strips_metadata(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    first = jpeg_with_gps((64, 48))
    second = jpeg_with_gps((32, 24))
    assert 0x8825 in Image.open(io.BytesIO(first)).getexif()
    response = await authed.post(
        "/api/v1/posts",
        data={"body": "with photos"},
        files=[image_part(first, "one.jpg"), image_part(second, "two.jpg")],
    )
    assert response.status_code == 201
    media = response.json()["media"]
    assert [m["kind"] for m in media] == ["image", "image"]
    assert [m["mime"] for m in media] == ["image/webp", "image/webp"]
    sizes = []
    for item in media:
        assert item["url"].startswith("/media/posts/")
        path = stored_path(settings, item["url"])
        with Image.open(path) as image:
            assert image.format == "WEBP"
            assert not image.getexif()
            assert "icc_profile" not in image.info
            sizes.append(image.size)
        assert b"SecretMaker" not in path.read_bytes()
        served = await authed.get(item["url"])
        assert served.status_code == 200
        assert served.headers["x-content-type-options"] == "nosniff"
    assert sizes == [(64, 48), (32, 24)]
    fetched = await authed.get(f"/api/v1/posts/{response.json()['id']}")
    assert fetched.json()["media"] == media
    assert sorted(leftovers(settings)) == sorted(
        stored_path(settings, m["url"]) for m in media
    )


async def test_large_image_is_downscaled(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (3000, 1000), "blue").save(buffer, "PNG")
    response = await authed.post(
        "/api/v1/posts", files=[image_part(buffer.getvalue(), "big.png")]
    )
    assert response.status_code == 201
    path = stored_path(settings, response.json()["media"][0]["url"])
    with Image.open(path) as image:
        assert abs(image.width - 2048) <= 1
        assert abs(image.height - 683) <= 1


async def test_animated_gif_keeps_first_frame(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "blue")]
    buffer = io.BytesIO()
    frames[0].save(
        buffer, "GIF", save_all=True, append_images=frames[1:], duration=50
    )
    response = await authed.post(
        "/api/v1/posts", files=[image_part(buffer.getvalue(), "a.gif")]
    )
    assert response.status_code == 201
    path = stored_path(settings, response.json()["media"][0]["url"])
    with Image.open(path) as image:
        assert image.format == "WEBP"
        assert getattr(image, "n_frames", 1) == 1


async def test_more_than_four_images_rejected(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    response = await authed.post(
        "/api/v1/posts",
        files=[image_part(jpeg_with_gps()) for _ in range(5)],
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "too_many_files"}
    assert leftovers(settings) == []


async def test_non_media_file_rejected(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    response = await authed.post(
        "/api/v1/posts",
        data={"body": "text"},
        files=[image_part(b"definitely not media", "x.jpg")],
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_media"}
    assert leftovers(settings) == []


async def test_oversized_image_rejected(
    authed: httpx.AsyncClient, settings: Settings
) -> None:
    response = await authed.post(
        "/api/v1/posts",
        files=[image_part(b"0" * (5 * 1024 * 1024 + 1))],
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "file_too_large"}
    assert leftovers(settings) == []


async def test_failed_upload_leaves_no_files(
    authed: httpx.AsyncClient,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    response = await authed.post(
        "/api/v1/posts",
        files=[image_part(jpeg_with_gps()), image_part(b"garbage")],
    )
    assert response.status_code == 422
    assert leftovers(settings) == []
    async with sessionmaker() as db:
        assert (await db.scalars(select(Post))).all() == []


async def test_failed_commit_removes_saved_files(
    authed: httpx.AsyncClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    posts = Path(settings.media_dir) / "posts"

    async def failing_commit(self: AsyncSession) -> None:
        if any(posts.iterdir()):
            raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        await authed.post("/api/v1/posts", files=[image_part(jpeg_with_gps())])
    assert leftovers(settings) == []


def make_video(
    path: Path,
    *,
    seconds: int = 1,
    size: str = "160x120",
    rate: int = 10,
    tags: bool = True,
    codecs: tuple[str, ...] = ("-c:v", "libx264", "-c:a", "aac"),
    audio: bool = True,
) -> bytes:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}:rate={rate}",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", "sine"]
    command += ["-t", str(seconds), *codecs]
    if tags and path.suffix == ".mp4":
        command += ["-movflags", "use_metadata_tags"]
    if not audio:
        command += ["-an"]
    if tags:
        command += [
            "-metadata",
            "title=SecretTitle",
            "-metadata",
            "location=+23.5505-046.6333/",
            "-metadata:s:v:0",
            "handler_name=SecretHandler",
        ]
    command.append(str(path))
    subprocess.run(command, check=True, capture_output=True)
    return path.read_bytes()


def video_part(
    data: bytes, name: str = "clip.mp4"
) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data, "video/mp4"))


def ffprobe_json(path: Path) -> dict[str, object]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    parsed: dict[str, object] = json.loads(out.stdout)
    return parsed


@pytest.fixture
def mp4_bytes(tmp_path: Path) -> bytes:
    return make_video(tmp_path / "source.mp4")


@needs_ffmpeg
async def test_post_with_video_strips_metadata(
    authed: httpx.AsyncClient, settings: Settings, mp4_bytes: bytes
) -> None:
    assert b"SecretTitle" in mp4_bytes
    assert b"+23.5505" in mp4_bytes
    assert b"SecretHandler" in mp4_bytes
    assert b"x264 - core" in mp4_bytes
    response = await authed.post(
        "/api/v1/posts",
        data={"body": "clip"},
        files=[video_part(mp4_bytes)],
    )
    assert response.status_code == 201
    media = response.json()["media"]
    assert len(media) == 1
    assert media[0]["kind"] == "video"
    assert media[0]["mime"] == "video/mp4"
    assert media[0]["url"].endswith(".mp4")
    path = stored_path(settings, media[0]["url"])
    raw = path.read_bytes()
    for secret in (
        b"SecretTitle",
        b"+23.5505",
        b"SecretHandler",
        b"x264 - core",
    ):
        assert secret not in raw
    probed = ffprobe_json(path)
    tags: list[dict[str, str]] = []
    fmt = probed["format"]
    assert isinstance(fmt, dict)
    tags.append(fmt.get("tags", {}))
    streams = probed["streams"]
    assert isinstance(streams, list)
    for stream in streams:
        tags.append(stream.get("tags", {}))
    for group in tags:
        for key, value in group.items():
            assert "Secret" not in value and "+23.5505" not in value
            if key.lower() == "encoder":
                assert "Lavf" not in value
    assert [s["codec_type"] for s in streams] == ["video", "audio"]
    assert leftovers(settings) == [path]


@needs_ffmpeg
async def test_webm_video_accepted(
    authed: httpx.AsyncClient, settings: Settings, tmp_path: Path
) -> None:
    data = make_video(
        tmp_path / "source.webm",
        codecs=("-c:v", "libvpx", "-c:a", "libopus"),
    )
    response = await authed.post(
        "/api/v1/posts", files=[video_part(data, "clip.webm")]
    )
    assert response.status_code == 201
    media = response.json()["media"][0]
    assert media["mime"] == "video/webm"
    assert media["url"].endswith(".webm")
    assert stored_path(settings, media["url"]).is_file()


@needs_ffmpeg
async def test_two_videos_rejected(
    authed: httpx.AsyncClient, settings: Settings, mp4_bytes: bytes
) -> None:
    response = await authed.post(
        "/api/v1/posts",
        files=[video_part(mp4_bytes), video_part(mp4_bytes)],
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "too_many_files"}
    assert leftovers(settings) == []


@needs_ffmpeg
async def test_image_and_video_mixed_rejected(
    authed: httpx.AsyncClient, settings: Settings, mp4_bytes: bytes
) -> None:
    for files in (
        [image_part(jpeg_with_gps()), video_part(mp4_bytes)],
        [video_part(mp4_bytes), image_part(jpeg_with_gps())],
    ):
        response = await authed.post("/api/v1/posts", files=files)
        assert response.status_code == 422
        assert response.json() == {"detail": "mixed_media"}
        assert leftovers(settings) == []


@needs_ffmpeg
async def test_video_too_long_rejected(
    authed: httpx.AsyncClient, settings: Settings, tmp_path: Path
) -> None:
    data = make_video(
        tmp_path / "long.mp4",
        seconds=181,
        size="64x64",
        rate=1,
        audio=False,
        tags=False,
    )
    response = await authed.post("/api/v1/posts", files=[video_part(data)])
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_media"}
    assert leftovers(settings) == []


@needs_ffmpeg
async def test_audio_only_file_rejected(
    authed: httpx.AsyncClient, tmp_path: Path
) -> None:
    path = tmp_path / "sound.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine",
            "-t",
            "1",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    response = await authed.post(
        "/api/v1/posts", files=[video_part(path.read_bytes())]
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_media"}


@needs_ffmpeg
async def test_concat_playlist_rejected(
    authed: httpx.AsyncClient,
    settings: Settings,
    tmp_path: Path,
    mp4_bytes: bytes,
) -> None:
    target = tmp_path / "source.mp4"
    target.write_bytes(mp4_bytes)
    playlist = f"ffconcat version 1.0\nfile '{target}'\n".encode()
    response = await authed.post(
        "/api/v1/posts", files=[video_part(playlist, "list.mp4")]
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_media"}
    assert leftovers(settings) == []


@needs_ffmpeg
async def test_ffmpeg_missing_returns_503(
    settings: Settings, mp4_bytes: bytes
) -> None:
    broken = settings.model_copy(update={"ffprobe_path": "/nonexistent"})
    other_app = create_app(broken)
    try:
        async with other_app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        transport = httpx.ASGITransport(app=other_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            registered = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "person@example.com",
                    "password": "a long enough password",
                    "acknowledged_email_notice": True,
                },
            )
            assert registered.status_code == 201
            response = await client.post(
                "/api/v1/posts", files=[video_part(mp4_bytes)]
            )
            assert response.status_code == 503
            assert response.json() == {"detail": "video_unavailable"}
            image = await client.post(
                "/api/v1/posts", files=[image_part(jpeg_with_gps())]
            )
            assert image.status_code == 201
    finally:
        await other_app.state.engine.dispose()
    assert not any((Path(settings.media_dir) / "tmp").iterdir())


def test_startup_sweeps_stale_tmp_files(settings: Settings) -> None:
    tmp = Path(settings.media_dir) / "tmp"
    tmp.mkdir(parents=True)
    old = tmp / "old"
    fresh = tmp / "fresh"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    stale = time.time() - 2 * 3600
    os.utime(old, (stale, stale))
    create_app(settings)
    assert not old.exists()
    assert fresh.exists()
