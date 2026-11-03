# Hosting an instance as a Tor onion service

The application loads nothing from third-party hosts, so it works in Tor
Browser, including at the "Safer" security level.

## 1. Serve frontend and API from one origin

Build the frontend (`npm run build` in `frontend/`) and serve
`frontend/dist` together with the backend behind one local address, for
example `127.0.0.1:8080`. Run the backend with access logs disabled:

```sh
uv run uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 \
  --no-access-log --no-server-header --no-proxy-headers
```

If you put a reverse proxy in front of it, turn off its access log too
(`access_log off;` in nginx).

## 2. Configure Tor

Add to `torrc`:

```
HiddenServiceDir /var/lib/tor/microblogging/
HiddenServicePort 80 127.0.0.1:8080
```

Restart Tor. The `.onion` address is in
`/var/lib/tor/microblogging/hostname`. Back up that directory: the keys
in it are the address.

## 3. Instance settings

- `ALLOWED_ORIGINS` must include `http://<address>.onion`.
- `COOKIE_SECURE` defaults to `true`. Set it to `false` only when the
  instance is served over plain HTTP on an onion address. Tor already
  encrypts the connection end to end.
