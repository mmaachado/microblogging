# Changelog

All notable changes to this project are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- Profiles at `/<username>`. People can edit their display name,
  `@username` (some names are reserved) and bio, and set a private
  birthday and phone. Public profiles show only username, name, bio and
  photo.
- Profile photos are re-encoded to 400×400 WebP, which drops EXIF, GPS,
  ICC and XMP metadata. Oversized and decompression-bomb images are
  rejected, and `/media` responses send `nosniff` and a restrictive CSP.
- Backend foundation (FastAPI, SQLAlchemy, Alembic): sign-up with e-mail
  and password, login, logout and `/api/v1/auth/me`. Sessions are opaque
  cookies stored only as hashes. Logs carry events, never IPs,
  user-agents, e-mails or tokens.
- Login throttling per e-mail, an instance-wide sign-up rate limit, and a
  cap on concurrent password hashing, none of which use IP addresses.
- Frontend foundation (React, shadcn/ui): sign-up with the e-mail notice,
  login, the app shell, light/dark/system theme and pt-BR/en, all kept in
  essential cookies.
- `docker-compose.yml` declaring Valkey and NATS for future use.
- Architecture overview (`docs/architecture.md`) and Tor hosting guide
  (`docs/tor.md`).
- Pull request template.

### Security

- Every request body is capped (`MAX_REQUEST_BYTES`, 64 KiB by default;
  5 MiB for profile photos), and the cap is checked before the body is
  read. Before this, any endpoint, including login, read an unbounded
  body into memory.
