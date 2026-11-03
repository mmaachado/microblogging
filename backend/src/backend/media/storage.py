import secrets
from pathlib import Path


def save_bytes(media_dir: str, subdir: str, data: bytes, ext: str) -> str:
    relative = f"{subdir}/{secrets.token_hex(16)}.{ext}"
    target = Path(media_dir) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative


def delete_media(media_dir: str, relative: str) -> None:
    base = Path(media_dir).resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValueError("path outside media dir")
    target.unlink(missing_ok=True)
