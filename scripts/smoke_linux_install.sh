#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# Smoke-test the Linux per-user installer in an isolated HOME.
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
SCRIPT_DIR="$SOURCE_DIR/packaging/linux"
command -v python3 >/dev/null || { echo "python3 não encontrado" >&2; exit 2; }
command -v iperf3 >/dev/null || { echo "iperf3 não encontrado" >&2; exit 2; }
[[ -d "$SOURCE_DIR/app" ]] || { echo "fonte inválida: $SOURCE_DIR" >&2; exit 2; }

SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/speedtester-linux-smoke.XXXXXX")"
trap 'rm -rf "$SMOKE_ROOT"' EXIT
export HOME="$SMOKE_ROOT/home"
export XDG_DATA_HOME="$SMOKE_ROOT/data"
export XDG_CONFIG_HOME="$SMOKE_ROOT/config"
export SPEEDTESTER_SOURCE_DIR="$SOURCE_DIR"
export SPEEDTESTER_INSTALL_ROOT="$XDG_DATA_HOME/speedtester"
mkdir -p "$HOME"

"$SCRIPT_DIR/install-user.sh"
test -x "$SPEEDTESTER_INSTALL_ROOT/venv/bin/python"
test -f "$XDG_DATA_HOME/applications/speedtester.desktop"
test -f "$XDG_CONFIG_HOME/systemd/user/speedtester-api.service"
test -f "$XDG_CONFIG_HOME/systemd/user/speedtester-client.service"

printf '\n# smoke-test sentinel\n' >> "$XDG_CONFIG_HOME/speedtester/speedtester.env"
"$SCRIPT_DIR/install-user.sh"
grep -F '# smoke-test sentinel' "$XDG_CONFIG_HOME/speedtester/speedtester.env" >/dev/null

SPEEDTESTER_PURGE_DATA=1 "$SCRIPT_DIR/uninstall-user.sh"
test ! -e "$SPEEDTESTER_INSTALL_ROOT"
test ! -e "$XDG_DATA_HOME/applications/speedtester.desktop"
test ! -e "$XDG_CONFIG_HOME/speedtester"
echo "linux-install-smoke-ok"
