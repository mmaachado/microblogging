import io
import logging
import secrets
from pathlib import Path

from PIL import Image, ImageOps

MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

logger = logging.getLogger(__name__)

FORMATS = ["JPEG", "PNG", "WEBP", "GIF"]
SIZE = 400


class InvalidImage(Exception):
    pass


def process_avatar(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data), formats=FORMATS) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("too many pixels")
            source.draft("RGB", (800, 800))
            source.seek(0)
            image = ImageOps.exif_transpose(source).convert("RGB")
        width, height = image.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        image = image.crop((left, top, left + side, top + side))
        image = image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        image.info.clear()
        out = io.BytesIO()
        image.save(out, "WEBP", quality=85, exif=b"", icc_profile=None)
    except Exception as error:
        logger.info("avatar rejected: %s", type(error).__name__)
        raise InvalidImage from None
    return out.getvalue()


def save_avatar(media_dir: str, data: bytes) -> str:
    relative = f"avatars/{secrets.token_hex(16)}.webp"
    target = Path(media_dir) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative


def delete_media(media_dir: str, relative_path: str) -> None:
    base = Path(media_dir).resolve()
    target = (base / relative_path).resolve()
    if not target.is_relative_to(base):
        raise ValueError("path outside media dir")
    target.unlink(missing_ok=True)
