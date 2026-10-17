#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
VERSION="${APP_VERSION:-0.3.0}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_DIR/dist}"
BUILD_DIR="${FLATPAK_BUILD_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/speedtester-flatpak-builder.XXXXXX")}"
MANIFEST="$SOURCE_DIR/packaging/linux/flatpak/io.github.ecarara.SpeedTester.yml"
APP_ID="io.github.ecarara.SpeedTester"
command -v flatpak-builder >/dev/null || { echo "flatpak-builder é necessário para gerar o Flatpak" >&2; exit 2; }
command -v flatpak >/dev/null || { echo "flatpak é necessário para gerar o Flatpak" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
REPO_DIR="${FLATPAK_REPO_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/speedtester-flatpak-repo.XXXXXX")}"
cleanup() {
  if [[ -z "${FLATPAK_BUILD_DIR:-}" && -d "$BUILD_DIR" ]]; then
    rm -rf "$BUILD_DIR"
  fi
  if [[ -z "${FLATPAK_REPO_DIR:-}" && -d "$REPO_DIR" ]]; then
    rm -rf "$REPO_DIR"
  fi
}
trap cleanup EXIT
flatpak-builder --force-clean --repo="$REPO_DIR" "$BUILD_DIR" "$MANIFEST"
flatpak build-bundle "$REPO_DIR" "$OUTPUT_DIR/${APP_ID}-${VERSION}.flatpak" "$APP_ID" stable
