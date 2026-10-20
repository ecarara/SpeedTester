#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

PURGE_DATA=0
for argument in "$@"; do
  case "$argument" in
    --purge-data) PURGE_DATA=1 ;;
    *) echo "uso: $0 [--purge-data]" >&2; exit 2 ;;
  esac
done

UID_VALUE="$(id -u)"
PLIST="$HOME/Library/LaunchAgents/speedtester-client.service.plist"
API_PLIST="$HOME/Library/LaunchAgents/speedtester-api.service.plist"
if [[ "${SPEEDTESTER_SKIP_LAUNCHCTL:-0}" != "1" ]]; then
  launchctl bootout "gui/$UID_VALUE" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootout "gui/$UID_VALUE" "$API_PLIST" >/dev/null 2>&1 || true
fi
rm -f "$PLIST" "$API_PLIST"

for app_path in "/Applications/SpeedTester.app" "$HOME/Applications/SpeedTester.app"; do
  if [[ -d "$app_path" ]]; then
    rm -rf "$app_path"
    echo "[speedtester] removido: $app_path"
  fi
done

if [[ "$PURGE_DATA" == "1" ]]; then
  rm -rf "$HOME/Library/Application Support/SpeedTester"
  rm -rf "$HOME/Library/Preferences/io.github.ecarara.SpeedTester.plist"
  echo "[speedtester] configuração e dados removidos"
else
  echo "[speedtester] configuração e dados preservados; use --purge-data para removê-los"
fi
echo "[speedtester] desinstalação concluída"
