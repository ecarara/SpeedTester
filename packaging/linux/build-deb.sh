#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
VERSION="${APP_VERSION:-0.3.0}"
VENV="${SPEEDTESTER_VENV:-$SOURCE_DIR/.venv}"
PYTHON="${PYTHON:-$VENV/bin/python}"
RUNTIME="${SPEEDTESTER_RUNTIME:-}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_DIR/dist}"
command -v dpkg-deb >/dev/null || { echo "dpkg-deb é necessário para gerar o pacote" >&2; exit 2; }
command -v "$PYTHON" >/dev/null || { echo "Python de build não encontrado: defina PYTHON ou SPEEDTESTER_VENV" >&2; exit 2; }
ARCH="$(dpkg --print-architecture)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
ROOT="$TMP_DIR/root"
mkdir -p "$ROOT/usr/lib/speedtester" "$ROOT/usr/bin" "$ROOT/usr/share/applications" "$ROOT/usr/lib/systemd/user" "$ROOT/usr/share/speedtester"
mkdir -p "$ROOT/usr/share/icons/hicolor/512x512/apps"
cp -a "$SOURCE_DIR/app" "$ROOT/usr/lib/speedtester/app"
"$PYTHON" "$SOURCE_DIR/scripts/stamp_version.py" "$ROOT/usr/lib/speedtester/app" "$VERSION"
if [[ -n "$RUNTIME" ]]; then
  "$PYTHON" "$SOURCE_DIR/scripts/build_linux_runtime.py" --output "$RUNTIME" --version "$VERSION" --verify-only
  cp -a "$RUNTIME" "$ROOT/usr/lib/speedtester/runtime"
else
  "$PYTHON" "$SOURCE_DIR/scripts/build_linux_runtime.py" --output "$ROOT/usr/lib/speedtester/runtime" --version "$VERSION"
fi
GLIBC_VERSION="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["libc"]["version"])' "$ROOT/usr/lib/speedtester/runtime/runtime-components.json")"
install -m 0755 "$SOURCE_DIR/packaging/linux/system/speedtester-launcher" "$ROOT/usr/bin/speedtester-launcher"
install -m 0755 "$SOURCE_DIR/packaging/linux/configure-user.sh" "$ROOT/usr/lib/speedtester/configure-user.sh"
install -m 0644 "$SOURCE_DIR/packaging/linux/speedtester.env.example" "$ROOT/usr/share/speedtester/speedtester.env.example"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester.desktop" "$ROOT/usr/share/applications/speedtester.desktop"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester-api.service" "$ROOT/usr/lib/systemd/user/speedtester-api.service"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester-client.service" "$ROOT/usr/lib/systemd/user/speedtester-client.service"
install -m 0644 "$SOURCE_DIR/assets/icons/hicolor/512/apps/speedtester.png" "$ROOT/usr/share/icons/hicolor/512x512/apps/speedtester.png"
install -m 0644 "$SOURCE_DIR/LICENSE" "$ROOT/usr/lib/speedtester/LICENSE"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@ARCH@/$ARCH/g" -e "s/@GLIBC_VERSION@/$GLIBC_VERSION/g" "$SOURCE_DIR/packaging/linux/debian/control.in" > "$ROOT/DEBIAN.control"
mkdir -p "$ROOT/DEBIAN"
mv "$ROOT/DEBIAN.control" "$ROOT/DEBIAN/control"
install -m 0755 "$SOURCE_DIR/packaging/linux/debian/postinst" "$ROOT/DEBIAN/postinst"
install -m 0755 "$SOURCE_DIR/packaging/linux/debian/prerm" "$ROOT/DEBIAN/prerm"
install -m 0755 "$SOURCE_DIR/packaging/linux/debian/postrm" "$ROOT/DEBIAN/postrm"
mkdir -p "$OUTPUT_DIR"
dpkg-deb --build --root-owner-group "$ROOT" "$OUTPUT_DIR/speedtester_${VERSION}_${ARCH}.deb"
