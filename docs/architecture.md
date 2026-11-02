# Architecture

This is a microblogging network built for people whose data is a
liability if it leaks: journalists, activists, politically exposed
persons, and anyone who does not want to be profiled. The code is open so
that if one instance is taken down, anyone can host another.

## Principles

1. **Minimal data.** An account needs an e-mail and a password. Birthday
   and phone are optional and change nothing.
2. **No logs about people.** The server never records IP addresses,
   browsers or operating systems. Application logs record events
   ("user registered"), never who did them.
3. **No third parties.** No CDN, web fonts, analytics or captcha.
   Everything the browser loads comes from the instance itself, so it
   works over Tor.
4. **Easy to re-host.** One repository, one database URL, no proprietary
   services.

## What is stored

| Data | Why |
| ---- | --- |
| E-mail (plain text) | Login. The sign-up form warns about this: if your identity is at risk, use an anonymous mailbox such as Proton Mail. |
| Password | Only as an Argon2id hash. |
| Session | Only a SHA-256 hash of the session token, with its expiry. |
| Profile (username, name, bio, avatar, optional birthday/phone) | Shown on your profile. Birthday and phone are never public. |
| Posts, media, likes, reposts, bookmarks | The service itself. |

Uploaded images are re-encoded and videos are remuxed, so EXIF, GPS and
other metadata are removed before anything is saved. File names are
random.

Deleting your account deletes all of the above, rows and files, with no
soft delete.

## Cookies

Only essential cookies are used: `session`, `theme` and `lang`.

## Components

```
frontend/  React + TypeScript (Vite, shadcn/ui), served as static files
backend/   FastAPI app: REST at /api/v1, read-only GraphQL at /graphql
           SQLAlchemy + Alembic; SQLite locally, Postgres in production
```

A cache (Valkey) and a message broker (NATS) are declared in
`docker-compose.yml` under the `future` profile. The application does not
use them yet.
