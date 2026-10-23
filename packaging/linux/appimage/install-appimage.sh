#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

APPIMAGE_PATH="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ "$APPIMAGE_PATH" == "uninstall" || "$APPIMAGE_PATH" == "--uninstall" ]]; then
  shift || true
  [[ $# -eq 0 ]] || { echo "uso: $0 [--uninstall] /caminho/SpeedTester.AppImage" >&2; exit 2; }
  exec "$SCRIPT_DIR/uninstall-appimage.sh"
fi
[[ -f "$APPIMAGE_PATH" ]] || { echo "uso: $0 /caminho/SpeedTester.AppImage" >&2; exit 2; }
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/speedtester"
APP_PATH="$APP_DIR/SpeedTester.AppImage"
APPLICATION_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/512x512/apps"
mkdir -p "$APP_DIR" "$APPLICATION_DIR" "$ICON_DIR"
install -m 0755 "$APPIMAGE_PATH" "$APP_PATH"

EXTRACT_DIR="$(mktemp -d)"
trap 'rm -rf "$EXTRACT_DIR"' EXIT
if (cd "$EXTRACT_DIR" && "$APP_PATH" --appimage-extract usr/share/icons/hicolor/512x512/apps/speedtester.png >/dev/null 2>&1); then
  install -m 0644 "$EXTRACT_DIR/squashfs-root/usr/share/icons/hicolor/512x512/apps/speedtester.png" "$ICON_DIR/speedtester.png"
fi
cat > "$APPLICATION_DIR/speedtester.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SpeedTester
Comment=Abre o dashboard do SpeedTester
Exec="$APP_PATH" open
Icon=$ICON_DIR/speedtester.png
Terminal=false
Categories=Network;Utility;
EOF
chmod 0644 "$APPLICATION_DIR/speedtester.desktop"
echo "[speedtester] AppImage instalado em $APP_PATH"
echo "[speedtester] remova com $0 --uninstall"
