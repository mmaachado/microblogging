# backend

FastAPI backend for the privacy-first microblogging network.

## Development

```sh
cp .env.example .env          # COOKIE_SECURE=false for plain-HTTP dev
uv sync
uv run alembic upgrade head
uv run task serve             # http://127.0.0.1:8000, no access log
uv run task test              # lint, types, tests
```
