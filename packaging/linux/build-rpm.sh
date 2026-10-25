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
command -v rpmbuild >/dev/null || { echo "rpmbuild é necessário para gerar o pacote" >&2; exit 2; }
command -v "$PYTHON" >/dev/null || { echo "Python de build não encontrado: defina PYTHON ou SPEEDTESTER_VENV" >&2; exit 2; }
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
TOP="$TMP_DIR/rpmbuild"
mkdir -p "$TOP/BUILD" "$TOP/RPMS" "$TOP/SOURCES" "$TOP/SPECS" "$TOP/SRPMS"
PAYLOAD="$TMP_DIR/payload"
mkdir -p "$PAYLOAD/app"
cp -a "$SOURCE_DIR/app/." "$PAYLOAD/app/"
"$PYTHON" "$SOURCE_DIR/scripts/stamp_version.py" "$PAYLOAD/app" "$VERSION"
if [[ -n "$RUNTIME" ]]; then
  "$PYTHON" "$SOURCE_DIR/scripts/build_linux_runtime.py" --output "$RUNTIME" --version "$VERSION" --verify-only
  cp -a "$RUNTIME" "$PAYLOAD/runtime"
else
  "$PYTHON" "$SOURCE_DIR/scripts/build_linux_runtime.py" --output "$PAYLOAD/runtime" --version "$VERSION"
fi
install -m 0755 "$SOURCE_DIR/packaging/linux/system/speedtester-launcher" "$PAYLOAD/speedtester-launcher"
install -m 0755 "$SOURCE_DIR/packaging/linux/configure-user.sh" "$PAYLOAD/configure-user.sh"
install -m 0644 "$SOURCE_DIR/packaging/linux/speedtester.env.example" "$PAYLOAD/speedtester.env.example"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester.desktop" "$PAYLOAD/speedtester.desktop"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester-api.service" "$PAYLOAD/speedtester-api.service"
install -m 0644 "$SOURCE_DIR/packaging/linux/system/speedtester-client.service" "$PAYLOAD/speedtester-client.service"
install -m 0644 "$SOURCE_DIR/assets/icons/hicolor/512/apps/speedtester.png" "$PAYLOAD/speedtester.png"
install -m 0644 "$SOURCE_DIR/LICENSE" "$PAYLOAD/LICENSE"
PACKAGE_TREE="$TMP_DIR/speedtester-${VERSION}"
mv "$PAYLOAD" "$PACKAGE_TREE"
tar -czf "$TOP/SOURCES/speedtester-${VERSION}.tar.gz" -C "$TMP_DIR" "speedtester-${VERSION}"
cp "$SOURCE_DIR/packaging/linux/rpm/speedtester.spec" "$TOP/SPECS/speedtester.spec"
mkdir -p "$OUTPUT_DIR"
rpmbuild -bb --define "_topdir $TOP" --define "version $VERSION" "$TOP/SPECS/speedtester.spec"
cp "$TOP"/RPMS/*/*.rpm "$OUTPUT_DIR/"
