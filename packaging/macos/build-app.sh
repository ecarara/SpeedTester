#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="${APP_VERSION:-0.3.0}"
BUILD_VERSION="${APP_BUILD_VERSION:-${VERSION//./}}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/dist/macos}"
ARCHITECTURE="${MACOS_ARCH:-$(uname -m)}"

die() { echo "[speedtester] $*" >&2; exit 1; }
command -v "$PYTHON" >/dev/null || die "Python não encontrado: $PYTHON"
command -v hdiutil >/dev/null || die "hdiutil não encontrado; execute este builder no macOS"
"$PYTHON" -m PyInstaller --version >/dev/null 2>&1 || die "PyInstaller não encontrado; instale-o no ambiente do build"

mkdir -p "$OUTPUT_DIR"
pushd "$REPO_ROOT" >/dev/null
STAGE=""
cleanup() {
  if [[ -n "$STAGE" && -d "$STAGE" ]]; then
    rm -rf "$STAGE"
  fi
  popd >/dev/null
}
trap cleanup EXIT

"$PYTHON" -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name SpeedTesterLauncher app/desktop_launcher.py
"$PYTHON" -m PyInstaller --noconfirm --clean --onefile --console \
  --name SpeedTesterClient --paths app app/macos_client_entry.py
"$PYTHON" -m PyInstaller --noconfirm --clean --onefile --console \
  --name SpeedTesterAPI --paths app app/macos_api_entry.py

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/speedtester-macos.XXXXXX")"
APP="$STAGE/SpeedTester.app"
CONTENTS="$APP/Contents"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"
cp dist/SpeedTesterLauncher "$CONTENTS/MacOS/SpeedTesterLauncher"
cp dist/SpeedTesterClient "$CONTENTS/MacOS/SpeedTesterClient"
cp dist/SpeedTesterAPI "$CONTENTS/MacOS/SpeedTesterAPI"
cp assets/packaging/macos/SpeedTester.icns "$CONTENTS/Resources/SpeedTester.icns"
chmod 0755 "$CONTENTS/MacOS/SpeedTesterLauncher" "$CONTENTS/MacOS/SpeedTesterClient" "$CONTENTS/MacOS/SpeedTesterAPI"

sed -e "s|@VERSION@|$VERSION|g" -e "s|@BUILD_VERSION@|$BUILD_VERSION|g" \
  "$SCRIPT_DIR/Info.plist.in" > "$CONTENTS/Info.plist"

if command -v plutil >/dev/null; then
  plutil -lint "$CONTENTS/Info.plist" >/dev/null
fi

APP_ARCHIVE="$OUTPUT_DIR/SpeedTester-$VERSION-macos-$ARCHITECTURE.app.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$APP_ARCHIVE"

DMG_STAGE="$STAGE/dmg"
mkdir -p "$DMG_STAGE"
ditto "$APP" "$DMG_STAGE/SpeedTester.app"
ln -s /Applications "$DMG_STAGE/Applications"
mkdir -p "$DMG_STAGE/LaunchAgents"
cp "$SCRIPT_DIR/install-dmg.sh" "$DMG_STAGE/Install SpeedTester.command"
cp "$SCRIPT_DIR/uninstall-app.sh" "$DMG_STAGE/Uninstall SpeedTester.command"
cp "$SCRIPT_DIR/LaunchAgents/speedtester-client.service.plist.in" \
  "$DMG_STAGE/LaunchAgents/speedtester-client.service.plist.in"
cp "$SCRIPT_DIR/LaunchAgents/speedtester-api.service.plist.in" \
  "$DMG_STAGE/LaunchAgents/speedtester-api.service.plist.in"
cp "$REPO_ROOT/packaging/linux/configure-user.sh" "$DMG_STAGE/configure-user.sh"
cp "$REPO_ROOT/packaging/linux/speedtester.env.example" "$DMG_STAGE/speedtester.env.example"
chmod 0755 "$DMG_STAGE/Install SpeedTester.command" "$DMG_STAGE/Uninstall SpeedTester.command"
DMG="$OUTPUT_DIR/SpeedTester-$VERSION-macos-$ARCHITECTURE.dmg"
hdiutil create -volname SpeedTester -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG" >/dev/null

echo "$DMG"
