# Shorten

A self-hosted URL shortener with per-link analytics and a built-in, Redis-backed rate limiter.
Shorten a URL, share the code, watch it redirect and count hits — all from one `docker compose up`.

## Features

- Random, unguessable base62 short codes (6 chars, ~57B combinations)
- Persistent storage — links survive restarts and redeploys (SQLite, WAL mode)
- Per-link hit counts and last-used timestamps
- Built-in rate limiting on shorten requests — token bucket, enforced atomically in Redis
- Fail-open: if Redis is unavailable the shortener keeps working, marked degraded, rather than failing
- Single-page web UI: shorten, browse recent links, and a live demo of the rate limiter

## Stack

- **API:** Python 3.12, FastAPI, uvicorn
- **Storage:** Redis (rate-limit state), SQLite via aiosqlite (links)
- **Frontend:** plain HTML/JS, no build step
- **Infra:** Docker Compose, Caddy (automatic HTTPS), GitHub Actions

## Quickstart

```bash
docker compose up --build
```

Open http://localhost:8080 — shorten a link, then hit **Spam** to watch the rate limiter
throttle the request flow (200s → 429s with a Retry-After countdown) and recover as the bucket refills.

```bash
curl -X POST http://localhost:8080/shorten -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","user_id":"me"}'
```

## Architecture

`demo` (shortener, SQLite) and `limiter` (token bucket) are two small HTTP services. Every
`POST /shorten` first asks the limiter for a decision; the limiter's only state is a token bucket in
Redis updated atomically via a Lua script — correct under concurrency by construction.

```
demo ──HTTP──► limiter ──Lua──► redis
```

If Redis is unreachable the limiter fails open: `200` + `X-RateLimit-Mode: degraded`, with a
warning log, so the shortener keeps working rather than failing with the decision store.

## API

- `POST /shorten` — `{url, user_id?}` → `{short_code, short_url, created_at, hits}`, or `429` + `Retry-After`
- `GET /{code}` — 301 redirect, increments the hit count
- `GET /recent` — latest links
- `POST /v1/check` — the limiter decision API, always with `X-RateLimit-*` headers

## Testing

```bash
pytest
```

35 tests against real Redis. The headline test fires 100 concurrent checks at a capacity-5 bucket
and asserts exactly 5 are allowed — a regression to a non-atomic implementation fails it.
GitHub Actions runs lint, typecheck, tests, and a compose smoke test on every push.

## Deployment

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

A production override adds Caddy (automatic HTTPS), keeps the limiter and Redis on an internal
network with only Caddy public, persists SQLite on a volume, and includes a nightly backup
(`scripts/backup.sh`).

## License

MIT
