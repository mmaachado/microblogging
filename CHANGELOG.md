# Changelog

All notable changes to this project are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

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
