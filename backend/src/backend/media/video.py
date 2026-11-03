import json
import os
import subprocess
from pathlib import Path

from backend.media import InvalidMedia

MAX_SECONDS = 180
TIMEOUT_SECONDS = 60
VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "av1"}
AUDIO_CODECS = {"aac", "opus", "vorbis", "mp3"}
MIME_TYPES = {"mp4": "video/mp4", "webm": "video/webm"}
DEMUXERS = "mov,matroska"
BITSTREAM_FILTERS = {
    "h264": "filter_units=remove_types=6",
    "hevc": "filter_units=remove_types=39|40",
    "av1": "filter_units=remove_types=5",
}


class InvalidVideo(InvalidMedia):
    pass


class VideoUnavailable(Exception):
    pass


def _run(argv: list[str]) -> bytes:
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            env={"PATH": os.environ["PATH"]},
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise InvalidVideo from None
    except OSError:
        raise VideoUnavailable from None
    if result.returncode != 0:
        raise InvalidVideo
    return result.stdout


def probe(ffprobe: str, source: Path) -> tuple[str, str]:
    output = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-format_whitelist",
            DEMUXERS,
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            f"file:{source}",
        ]
    )
    try:
        info = json.loads(output)
        container = str(info["format"]["format_name"])
        duration = float(info["format"]["duration"])
        streams = info["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        audio = next((s for s in streams if s["codec_type"] == "audio"), None)
        codec = str(video["codec_name"])
        codecs_ok = codec in VIDEO_CODECS and (
            audio is None or audio["codec_name"] in AUDIO_CODECS
        )
    except (ValueError, KeyError, TypeError, StopIteration):
        raise InvalidVideo from None
    if not 0 < duration <= MAX_SECONDS or not codecs_ok:
        raise InvalidVideo
    if "mp4" in container:
        return "mp4", codec
    if "webm" in container:
        return "webm", codec
    raise InvalidVideo


def strip_metadata(
    ffmpeg: str, source: Path, target: Path, ext: str, codec: str
) -> None:
    muxer = ["-movflags", "+faststart", "-f", "mp4"]
    if ext == "webm":
        muxer = ["-f", "webm"]
    if codec in BITSTREAM_FILTERS:
        muxer = ["-bsf:v", BITSTREAM_FILTERS[codec], *muxer]
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(
            [
                ffmpeg,
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-protocol_whitelist",
                "file",
                "-format_whitelist",
                DEMUXERS,
                "-i",
                f"file:{source}",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-t",
                str(MAX_SECONDS),
                "-c",
                "copy",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                *muxer,
                str(target),
            ]
        )
    except BaseException:
        target.unlink(missing_ok=True)
        raise
