#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
VERSION="${APP_VERSION:-0.3.0}"
VENV="${SPEEDTESTER_VENV:-$SOURCE_DIR/.venv}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_DIR/dist}"
command -v appimagetool >/dev/null || { echo "appimagetool é necessário para gerar o AppImage" >&2; exit 2; }
[[ -x "$VENV/bin/python" ]] || { echo "venv não encontrado: defina SPEEDTESTER_VENV" >&2; exit 2; }
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
APPDIR="$TMP_DIR/SpeedTester.AppDir"
mkdir -p "$APPDIR/usr/lib/speedtester" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$SOURCE_DIR/app" "$APPDIR/usr/lib/speedtester/app"
cp -a "$VENV" "$APPDIR/usr/lib/speedtester/venv"
install -m 0755 "$SOURCE_DIR/packaging/linux/appimage/AppRun" "$APPDIR/AppRun"
sed 's|^Exec=.*|Exec=SpeedTester open|' "$SOURCE_DIR/packaging/linux/system/speedtester.desktop" > "$APPDIR/speedtester.desktop"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester.desktop" "$APPDIR/usr/share/applications/speedtester.desktop"
install -m 0644 "$SOURCE_DIR/assets/icons/hicolor/512/apps/speedtester.png" "$APPDIR/speedtester.png"
install -m 0644 "$SOURCE_DIR/assets/icons/hicolor/512/apps/speedtester.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/speedtester.png"
mkdir -p "$OUTPUT_DIR"
appimagetool "$APPDIR" "$OUTPUT_DIR/SpeedTester-${VERSION}-x86_64.AppImage"
