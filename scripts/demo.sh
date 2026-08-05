#!/usr/bin/env bash
# Live demo: burst -> 429 -> recover, then degraded mode while Redis is stopped.
# Usage: ./scripts/demo.sh [base_url]   (default http://localhost:8080)
set -euo pipefail

# Always restore Redis, even if the demo dies mid-script.
trap 'docker compose start redis' EXIT

BASE="${1:-http://localhost:8080}"

echo "== 1. shorten one URL (expect 200) =="
curl -s -X POST "$BASE/shorten" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/1","user_id":"demo"}'
echo

echo "== 2. spam 15 writes (expect first ~10 -> 200, then 429) =="
for i in $(seq 1 15); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/shorten" \
    -H 'Content-Type: application/json' -d "{\"url\":\"https://example.com/$i\",\"user_id\":\"demo\"}")
  echo "req $i -> $code"
done

echo "== 3. degraded mode: stop Redis, shorten again (expect 200 + X-RateLimit-Mode: degraded) =="
docker compose stop redis
curl -s -i -X POST "$BASE/shorten" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/degraded","user_id":"demo"}' | grep -i "x-ratelimit-mode: degraded"
docker compose start redis

echo "== 4. after Redis restart, bucket refills (expect 200) =="
sleep 4
curl -s -o /dev/null -w "after restart -> %{http_code}\n" -X POST "$BASE/shorten" \
  -H 'Content-Type: application/json' -d '{"url":"https://example.com/recovered","user_id":"demo"}'
