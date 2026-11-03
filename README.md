# microblogging

Open source, privacy-first microblogging network. No IP, browser or OS
logs, only essential cookies, and nothing loaded from third parties, so
it runs over Tor. See [docs/architecture.md](docs/architecture.md).

## Running locally

Backend (Python 3.13, [uv](https://docs.astral.sh/uv/)): see
[backend/README.md](backend/README.md).

Frontend (Node):

```sh
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to the backend
```
