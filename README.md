# Shortener + Rate Limiter

![CI](https://github.com/rizkilaks/shorten/actions/workflows/ci.yml/badge.svg)

A persistent URL shortener (SQLite/WAL, per-link hit stats) with a **built-in race-free rate
limiter** (token bucket, Lua-atomic in Redis, fail-open), deployed to a VPS behind Caddy with
automatic HTTPS on a free DuckDNS subdomain.

The core idea in one line: **every rate-limit decision is a single atomic Lua script in Redis — so
it is correct across any number of instances, and a concurrency test proves it.** The shortener is
the product; the limiter is the safety feature.

## Quickstart (local)

```bash
docker compose up --build
```

- UI: http://localhost:8080  (shorten + recent links + spam/429 demo)
- Limiter health: http://localhost:8000/v1/health
- `./scripts/demo.sh` — scripted live demo (burst → 429 → recover → Redis-down degraded → recover)

```bash
curl -X POST http://localhost:8080/shorten -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/1","user_id":"demo"}'
```

## Architecture

```
demo ──HTTP──► limiter ──Lua──► redis        (production)
 │                                          Internet → Caddy :80/:443 (auto-TLS)
 │ SQLite (WAL)                                        │
 └── links.db (volume) + nightly backup      demo :8080 → limiter :8000 → redis :6379 (internal)
```

The limiter is a **service, not a library** — the shortener calls it over HTTP (~1ms), so the
decision is real network traffic and observable. Limit state lives only in Redis; the Lua script is
the only place it changes, so it is race-free by construction. On a Redis error the limiter **fails
open**: `allowed: true` + `X-RateLimit-Mode: degraded` + a warning log — the product keeps working
instead of dying with the decision store. Nothing to sync on recovery: a rate limit is a **temporal
decision, not an accounting ledger**. Links live in SQLite (WAL) and persist across restarts.

## API

`POST /v1/check` — body `{"rule_key": string, "user_id"?: string, "cost"?: int}`.

| rule_key   | burst | sustained | applies to                    |
|------------|-------|-----------|-------------------------------|
| `write_free` | 10  | 20/min    | POST /shorten (user)          |
| `read_free`  | 100 | 300/min   | GET /{code} (user)            |
| `ip_write`   | 30  | 60/min    | POST /shorten (anonymous)     |

Always `X-RateLimit-Limit / Remaining / Reset`; over budget → **429** + `Retry-After` (seconds).

Shortener: `POST /shorten`, `GET /{code}` (301 + hit count), `GET /recent`, `GET /v1/health`.

## Testing

`pytest` runs integration tests against **real Redis**, not a mock. Headline test: 100 parallel
checks at a capacity-5 bucket → **exactly 5 approved** (a client-side read-modify-write regression
would fail it). Token-bucket math is deterministic via an injectable clock; SQLite tests use temp
files. CI: `ruff` → `mypy` → `pytest` (Redis service) → compose build + smoke, on every push.

## Production Deployment

Target: a single VPS (2 vCPU / 2GB / 40GB — ~8-10× headroom). Costs $0 beyond the VPS.

1. **DNS (free):** create a DuckDNS subdomain `s.<me>.duckdns.org` → A record = VPS IP. Verify `nslookup s.<me>.duckdns.org`.
2. **Docker on the VPS:** `sudo apt install -y docker.io docker-compose-v2 sqlite3`.
3. **App:** clone the repo to `/opt/linkshort/app`, `cp .env.example .env`, set `DOMAIN`.
4. **Data dir ownership:** `sudo mkdir -p /opt/linkshort/data /opt/linkshort/backups && sudo chown 1000:1000 /opt/linkshort/data /opt/linkshort/backups` — the container runs as uid 1000 and must own the bind-mounted data dir, or SQLite can't be written.
5. **Firewall:** `sudo ufw allow 80,443/tcp` (also open 80/443 in the provider panel).
6. **Launch:** `docker compose -f compose.yaml -f compose.prod.yaml up -d --build`.
7. **Backups:** `crontab -e` → `@daily /opt/linkshort/app/scripts/backup.sh` (keeps 7 tarballs). Test once: `DATA_DIR=/opt/linkshort/data BACKUP_DIR=/opt/linkshort/backups bash /opt/linkshort/app/scripts/backup.sh`.

Only Caddy is public; `limiter` + `redis` are internal-only; SQLite lives on a mounted volume;
`restart: unless-stopped`. HTTPS comes from Let's Encrypt, renewed automatically by Caddy.

## Decision Log (why this project looks like this)

1. **Python over Go/.NET** — target JDs accept Python; leetcode synergy. .NET depth is the next project's job.
2. **FastAPI over Flask/Django** — async by default, pydantic-typed, first-class async testing.
3. **Token bucket over fixed window / sliding log** — bursts up to capacity, smooth refill, 2 fields per key. Alternatives documented; one algorithm shipped.
4. **Rate-limit state in Redis** — atomic ops (Lua), TTL, multi-instance correctness natively. Postgres has no TTL primitive.
5. **Lua over client-side RMW** — check-then-set races under concurrency; Lua runs atomically. The concurrency test is the proof.
6. **Fail-open over circuit breaker / fail-closed** — a 1/N local bucket collapses at N=1 (full budget, no guarantee), so the honest version is pure fail-open with a visible degraded header.
7. **Limiter as HTTP service over a library** — real decoupling, observable decision; sidecar/library wins only at very high QPS.
8. **SQLite (WAL) for links** — the product must persist; SQLite is zero-ops to ~10M rows (≈1.4GB); Postgres is the documented migration trigger. In-memory was fine for a demo, not for a tool I use.
9. **Hit stats as columns, incremented on redirect** — simple at this scale; the "read that is also a write" is worth knowing; Redis counters + async flush is the scale evolution.
10. **user_id primary, IP fallback** — NAT makes IP-only limits unfair and useless.
11. **429 semantics per IANA** — clients already understand `Retry-After` + `X-RateLimit-*`.
12. **Deployed: VPS + Docker + Caddy + DuckDNS** — it's a tool meant to be used, so it ships. One command, real HTTPS for $0 beyond hardware I own. K8s/Terraform/AWS would be mis-scoped here.
13. **Backups: nightly WAL-consistent SQLite snapshot** — taken via SQLite's online backup (`sqlite3 .backup`), because tarring a live WAL database would silently drop recent writes; keep 7.
14. **Static HTML UI** — a tool page, not an app; recent links load from SQLite; no toolchain.

## Scale

Design envelope: 5k writes/day (peak 60/min), 50k reads/day (peak 600/min), ~1-3k DAU — enough to
make storage/limits choices concrete. These are **design inputs, not a load claim**: one host serves
~1,000-2,000 RPS end-to-end (each check = one Lua round-trip; Redis does 50k+ ops/s), ~100× the
envelope. "The interesting work was making the decision correct, not fast."

What I'd change at scale: sidecar/library limiter per host; shard Redis by user hash; hit counters
in Redis + async flush; Postgres at ~10M rows; Prometheus metrics + throttle-rate alerts; the IANA
`RateLimit` draft headers; auth if I open it up (an `ADMIN_TOKEN` middleware is the seeded door).

## Security notes

- `X-User-Id` is a proxy for an API key (spoofable — real auth is out of scope by design, extensible).
- Short codes are cryptographically random; `/shorten` is itself rate-limited (brute-force defense).
- No credentials in the repo; `.env` (VPS) and `data/` are gitignored.
