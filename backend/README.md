# backend

FastAPI backend for the privacy-first microblogging network.

## Development

Video uploads need `ffmpeg` and `ffprobe` on the `PATH` (or set
`FFMPEG_PATH` / `FFPROBE_PATH`). Without them, images still work and
video uploads return `503 video_unavailable`.

```sh
cp .env.example .env          # COOKIE_SECURE=false for plain-HTTP dev
uv sync
uv run alembic upgrade head
uv run task serve             # http://127.0.0.1:8000, no access log
uv run task test              # lint, types, tests
```
