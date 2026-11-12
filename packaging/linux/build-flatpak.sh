#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
VERSION="${APP_VERSION:-0.3.0}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_DIR/dist}"
BUILD_DIR="${FLATPAK_BUILD_DIR:-$SOURCE_DIR/.flatpak-builder}"
MANIFEST="$SOURCE_DIR/packaging/linux/flatpak/io.github.ecarara.SpeedTester.yml"
APP_ID="io.github.ecarara.SpeedTester"
command -v flatpak-builder >/dev/null || { echo "flatpak-builder é necessário para gerar o Flatpak" >&2; exit 2; }
command -v flatpak >/dev/null || { echo "flatpak é necessário para gerar o Flatpak" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
REPO_DIR="$OUTPUT_DIR/flatpak-repo"
STATE_DIR="${FLATPAK_STATE_DIR:-${TMPDIR:-/tmp}/speedtester-flatpak-state}"
case "$BUILD_DIR" in ""|"/") echo "diretório de build inválido: $BUILD_DIR" >&2; exit 2;; esac
# Clean explicitly: newer flatpak-builder refuses --force-clean when its app
# dir looks like a parent of the working or state directory.
rm -rf "$BUILD_DIR"
mkdir -p "$STATE_DIR"
# GitHub-hosted runners do not provide a reliable FUSE mount for rofiles-fuse.
# Disabling that optimization keeps the build portable and avoids indefinite
# hangs after the module commands complete.
flatpak-builder --disable-rofiles-fuse --default-branch=stable --state-dir="$STATE_DIR" --repo="$REPO_DIR" "$BUILD_DIR" "$MANIFEST"
flatpak build-bundle "$REPO_DIR" "$OUTPUT_DIR/${APP_ID}-${VERSION}.flatpak" "$APP_ID" stable
