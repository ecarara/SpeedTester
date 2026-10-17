#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_APP="${1:-/Volumes/SpeedTester/SpeedTester.app}"
USER_APPLICATIONS="$HOME/Applications"

die() { echo "[speedtester] $*" >&2; exit 1; }
[[ -d "$SOURCE_APP/Contents" ]] || die "aplicativo não encontrado: $SOURCE_APP"
[[ -x "$SOURCE_APP/Contents/MacOS/SpeedTesterClient" ]] || die "SpeedTesterClient ausente no bundle"

if [[ -d /Applications && -w /Applications ]]; then
  DEST_APP="/Applications/SpeedTester.app"
else
  mkdir -p "$USER_APPLICATIONS"
  DEST_APP="$USER_APPLICATIONS/SpeedTester.app"
fi

UID_VALUE="$(id -u)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST="$AGENTS_DIR/speedtester-client.service.plist"
LOG_DIR="$HOME/Library/Logs/SpeedTester"
mkdir -p "$AGENTS_DIR"
mkdir -p "$LOG_DIR"
if [[ "${SPEEDTESTER_SKIP_LAUNCHCTL:-0}" != "1" ]]; then
  launchctl bootout "gui/$UID_VALUE" "$PLIST" >/dev/null 2>&1 || true
fi
rm -f "$PLIST"
rm -rf "$DEST_APP"
ditto "$SOURCE_APP" "$DEST_APP"

CLIENT_PATH="$DEST_APP/Contents/MacOS/SpeedTesterClient"
escaped_client_path="$(printf '%s' "$CLIENT_PATH" | sed 's/[&|]/\\&/g')"
escaped_log_dir="$(printf '%s' "$LOG_DIR" | sed 's/[&|]/\\&/g')"
sed -e "s|@CLIENT_PATH@|$escaped_client_path|g" \
  -e "s|@LOG_DIR@|$escaped_log_dir|g" \
  "$SCRIPT_DIR/LaunchAgents/speedtester-client.service.plist.in" > "$PLIST"
chmod 0644 "$PLIST"
if command -v plutil >/dev/null; then
  plutil -lint "$PLIST" >/dev/null
fi
if [[ "${SPEEDTESTER_SKIP_LAUNCHCTL:-0}" != "1" ]]; then
  launchctl bootstrap "gui/$UID_VALUE" "$PLIST"
  launchctl enable "gui/$UID_VALUE/speedtester-client.service" >/dev/null 2>&1 || true
fi

echo "[speedtester] instalado em $DEST_APP"
echo "[speedtester] o LaunchAgent foi habilitado para a sessão do usuário"
