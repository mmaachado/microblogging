import io

from PIL import Image, ImageOps

from backend.media import InvalidMedia

MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

FORMATS = ["JPEG", "PNG", "WEBP", "GIF"]
DRAFT_SIZE = (2048, 2048)
AVATAR_DRAFT_SIZE = (800, 800)
AVATAR_SIZE = 400
POST_MAX_SIDE = 2048


class InvalidImage(InvalidMedia):
    pass


def open_image(
    data: bytes, draft: tuple[int, int] = DRAFT_SIZE
) -> Image.Image:
    with Image.open(io.BytesIO(data), formats=FORMATS) as source:
        if source.width * source.height > MAX_PIXELS:
            raise ValueError("too many pixels")
        source.draft("RGB", draft)
        source.seek(0)
        return ImageOps.exif_transpose(source).convert("RGB")


def _encode(image: Image.Image) -> bytes:
    image.info.clear()
    out = io.BytesIO()
    image.save(out, "WEBP", quality=85, exif=b"", icc_profile=None)
    return out.getvalue()


def to_avatar(image: Image.Image) -> bytes:
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    square = image.crop((left, top, left + side, top + side))
    return _encode(
        square.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    )


def to_post_image(image: Image.Image) -> bytes:
    image.thumbnail((POST_MAX_SIDE, POST_MAX_SIDE), Image.Resampling.LANCZOS)
    return _encode(image)
