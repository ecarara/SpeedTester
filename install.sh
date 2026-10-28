#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# Deploy the Compose stack after a read-only preflight. Docker restart policies
# keep the services running after host restarts when the Docker daemon starts.
set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-speedtester}"
cd "$PROJECT_DIR"
python3 scripts/doctor.py --env-file .env
compose=(docker compose --env-file "$PROJECT_DIR/.env" -f "$PROJECT_DIR/docker/compose.yaml" -p "$COMPOSE_PROJECT")
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" run --rm --no-deps collector python /opt/speedtester-scripts/doctor.py --container
"${compose[@]}" up -d --wait --wait-timeout 180
if [[ "${SPEEDTESTER_STAGING_HTTPS_CHECK:-false}" == "true" ]]; then
  python3 scripts/staging_https.py verify --root "$PROJECT_DIR"
fi
echo '[install] services started; use docker compose logs and /health to monitor collection'
