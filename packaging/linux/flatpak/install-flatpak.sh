#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

BUNDLE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ "$BUNDLE" == "uninstall" || "$BUNDLE" == "--uninstall" ]]; then
  shift || true
  [[ $# -eq 0 ]] || { echo "uso: $0 [--uninstall] /caminho/io.github.ecarara.SpeedTester-*.flatpak" >&2; exit 2; }
  exec "$SCRIPT_DIR/uninstall-flatpak.sh"
fi
[[ -f "$BUNDLE" ]] || { echo "uso: $0 /caminho/io.github.ecarara.SpeedTester-*.flatpak" >&2; exit 2; }
command -v flatpak >/dev/null || { echo "flatpak não encontrado" >&2; exit 2; }
flatpak --user install --noninteractive "$BUNDLE"
echo "[speedtester] Flatpak instalado; remova com $0 --uninstall"
