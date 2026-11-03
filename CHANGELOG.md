# Changelog

All notable changes to this project are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- Posts of up to 120 characters with up to 4 images or 1 video, a global
  reverse-chronological timeline with cursor pagination, post pages,
  editing (marked as edited) and deletion, which also removes the files.
  Images are re-encoded to WebP (at most 2048 px) and videos are copied
  through ffmpeg without metadata or extra streams. Known limitation: an
  animated GIF keeps only its first frame. Video uploads need `ffmpeg`
  and `ffprobe` on the host.
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

- Per-account limits on posting: 10 posts per minute and 500 MiB of
  uploads per day by default (`POSTS_PER_MINUTE`,
  `UPLOAD_BYTES_PER_DAY`). Slots are reserved before the upload starts,
  so parallel requests can't get past them, and nothing is keyed by IP.
- Video handling only accepts MP4/MOV and Matroska/WebM demuxers and
  local files, never reads stdin, and caps the output at 180 s. It also
  strips the metadata units inside H.264, HEVC and AV1 streams (SEI and
  OBU metadata), where cameras can embed device or location data.
- Every request body is capped (`MAX_REQUEST_BYTES`, 64 KiB by default;
  5 MiB for profile photos), and the cap is checked before the body is
  read. Before this, any endpoint, including login, read an unbounded
  body into memory.
