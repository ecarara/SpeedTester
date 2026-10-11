#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# install.sh — deploy the SpeedTester container stack on the target host.
#
# Usage:
#   ./install.sh
#
# Copies the project (if run remotely), builds the containers, brings them up,
# and installs systemd user services so collector + api survive reboots.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/SpeedTester}"
COMPOSE_FILE="$PROJECT_DIR/docker/compose.yaml"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-speedtester}"

# Ensure we run from the project root (where compose.yaml lives under docker/).
cd "$PROJECT_DIR"

echo "[install] project dir: $PROJECT_DIR"

# 1) Docker + Compose must exist.
if ! command -v docker >/dev/null 2>&1; then
  echo "[install] docker not found — installing..."
  # Fedora: use dnf; fall back to get-docker script.
  sudo dnf install -y docker
  sudo systemctl start docker
  sudo systemctl enable docker
fi

docker compose version >/dev/null 2>&1 || {
  echo "[install] docker compose plugin not found. Install Docker Desktop or the compose plugin first." >&2
  exit 1
}

# 2) Copy sudo password prompt (best effort; harmless if no password).
echo "[install] ensuring docker group access for current user..."
sudo usermod -aG docker "${USER:-$(whoami)}" || true
newgrp docker || true

# 3) Build + start.
echo "[install] building containers (this may take a while on first run)..."
docker compose --env-file "$PROJECT_DIR/.env" -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d --build

echo "[install] waiting for services to be healthy..."
for i in $(seq 1 30); do
  if docker compose --env-file "$PROJECT_DIR/.env" -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" ps --status healthy 2>/dev/null | grep -q healthy; then
    echo "[install] services healthy."
    break
  fi
  sleep 2
done

# 4) One systemd user service for the complete Compose stack.
# XDG_CONFIG_HOME is optional according to the XDG convention.
USER_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
USER_SYSTEMD_DIR="$USER_CONFIG_HOME/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

cat > "$USER_SYSTEMD_DIR/speedtester.service" <<EOF
[Unit]
Description=SpeedTester Docker Compose stack
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/docker compose --env-file ${PROJECT_DIR}/.env -f ${COMPOSE_FILE} -p ${COMPOSE_PROJECT} up
ExecStop=/usr/bin/docker compose --env-file ${PROJECT_DIR}/.env -f ${COMPOSE_FILE} -p ${COMPOSE_PROJECT} stop
Restart=always
RestartSec=5
Environment=HOME=${PROJECT_DIR}

[Install]
WantedBy=default.target
EOF

# Disable the two legacy units if a previous installation created them.
systemctl --user disable --now speedtester-collector.service speedtester-api.service 2>/dev/null || true

loginctl enable-linger "${USER:-$(whoami)}" || sudo loginctl enable-linger "${USER:-$(whoami)}" || true

systemctl --user daemon-reload
systemctl --user enable --now speedtester.service

echo
echo "[install] DONE. Open the dashboard at:"
echo "  http://$(hostname -I | awk '{print $1}'):8000"
echo
echo "[install] useful commands:"
echo "  docker compose --env-file $PROJECT_DIR/.env -f $COMPOSE_FILE -p $COMPOSE_PROJECT logs -f"
echo "  systemctl --user status speedtester.service"
