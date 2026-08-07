#!/usr/bin/env bash
# Forced command for the CI/CD deploy key. GitHub Actions connects over SSH and
# the server runs this script — the key cannot open a general shell.
set -euo pipefail

cd /opt/linkshort/app
git pull --ff-only
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
