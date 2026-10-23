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
[[ -x "$SOURCE_APP/Contents/MacOS/SpeedTesterAPI" ]] || die "SpeedTesterAPI ausente no bundle"

if [[ -d /Applications && -w /Applications ]]; then
  DEST_APP="/Applications/SpeedTester.app"
else
  mkdir -p "$USER_APPLICATIONS"
  DEST_APP="$USER_APPLICATIONS/SpeedTester.app"
fi

UID_VALUE="$(id -u)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST="$AGENTS_DIR/speedtester-client.service.plist"
API_PLIST="$AGENTS_DIR/speedtester-api.service.plist"
LOG_DIR="$HOME/Library/Logs/SpeedTester"
mkdir -p "$AGENTS_DIR"
mkdir -p "$LOG_DIR"
CONFIG_DIR="$HOME/Library/Application Support/SpeedTester"
CONFIG_TEMPLATE="$SCRIPT_DIR/speedtester.env.example"
CONFIG_HELPER="$SCRIPT_DIR/configure-user.sh"
if [[ ! -f "$CONFIG_TEMPLATE" ]]; then
  CONFIG_TEMPLATE="$SCRIPT_DIR/../linux/speedtester.env.example"
fi
if [[ ! -x "$CONFIG_HELPER" ]]; then
  CONFIG_HELPER="$SCRIPT_DIR/../linux/configure-user.sh"
fi
if [[ -x "$CONFIG_HELPER" && -f "$CONFIG_TEMPLATE" ]]; then
  SPEEDTESTER_CONFIG_DIR="$CONFIG_DIR" \
    SPEEDTESTER_CONFIRM_EXISTING=1 \
    SPEEDTESTER_ENV_TEMPLATE="$CONFIG_TEMPLATE" \
    "$CONFIG_HELPER"
fi
if [[ "${SPEEDTESTER_SKIP_LAUNCHCTL:-0}" != "1" ]]; then
  launchctl bootout "gui/$UID_VALUE" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootout "gui/$UID_VALUE" "$API_PLIST" >/dev/null 2>&1 || true
fi
rm -f "$PLIST" "$API_PLIST"
rm -rf "$DEST_APP"
ditto "$SOURCE_APP" "$DEST_APP"

CLIENT_PATH="$DEST_APP/Contents/MacOS/SpeedTesterClient"
API_PATH="$DEST_APP/Contents/MacOS/SpeedTesterAPI"
escaped_client_path="$(printf '%s' "$CLIENT_PATH" | sed 's/[&|]/\\&/g')"
escaped_api_path="$(printf '%s' "$API_PATH" | sed 's/[&|]/\\&/g')"
escaped_log_dir="$(printf '%s' "$LOG_DIR" | sed 's/[&|]/\\&/g')"
sed -e "s|@CLIENT_PATH@|$escaped_client_path|g" \
  -e "s|@LOG_DIR@|$escaped_log_dir|g" \
  "$SCRIPT_DIR/LaunchAgents/speedtester-client.service.plist.in" > "$PLIST"
sed -e "s|@API_PATH@|$escaped_api_path|g" \
  -e "s|@LOG_DIR@|$escaped_log_dir|g" \
  "$SCRIPT_DIR/LaunchAgents/speedtester-api.service.plist.in" > "$API_PLIST"
chmod 0644 "$PLIST"
chmod 0644 "$API_PLIST"
if command -v plutil >/dev/null; then
  plutil -lint "$PLIST" >/dev/null
  plutil -lint "$API_PLIST" >/dev/null
fi
if [[ "${SPEEDTESTER_SKIP_LAUNCHCTL:-0}" != "1" ]]; then
  launchctl bootstrap "gui/$UID_VALUE" "$PLIST"
  launchctl bootstrap "gui/$UID_VALUE" "$API_PLIST"
  launchctl enable "gui/$UID_VALUE/speedtester-client.service" >/dev/null 2>&1 || true
  launchctl enable "gui/$UID_VALUE/speedtester-api.service" >/dev/null 2>&1 || true
fi

echo "[speedtester] instalado em $DEST_APP"
echo "[speedtester] o LaunchAgent foi habilitado para a sessão do usuário"
