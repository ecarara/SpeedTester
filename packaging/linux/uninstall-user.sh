#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_ROOT="${SPEEDTESTER_INSTALL_ROOT:-$DATA_HOME/speedtester}"

if command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user disable --now speedtester-client.service speedtester-api.service >/dev/null 2>&1 || true
  systemctl --user daemon-reload
fi

rm -f "$CONFIG_HOME/systemd/user/speedtester-api.service" "$CONFIG_HOME/systemd/user/speedtester-client.service"
rm -f "$DATA_HOME/applications/speedtester.desktop"
rm -f "$DATA_HOME/speedtester/bin/speedtester-launcher"
for size in 16 32 48 64 128 256 512; do
  rm -f "$DATA_HOME/icons/hicolor/$size/apps/speedtester.png"
done
rm -rf "$INSTALL_ROOT"

if [[ "${SPEEDTESTER_PURGE_DATA:-0}" == "1" ]]; then
  rm -rf "$CONFIG_HOME/speedtester" "$DATA_HOME/speedtester/data"
  echo "[speedtester] configuração e dados removidos"
else
  echo "[speedtester] configuração e dados preservados; use SPEEDTESTER_PURGE_DATA=1 para removê-los"
fi
echo "[speedtester] desinstalação concluída"
