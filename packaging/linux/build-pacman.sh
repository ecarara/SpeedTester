#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
ARCH_DIR="$SOURCE_DIR/packaging/linux/arch"
VERSION="${APP_VERSION:-0.3.0}"
OUTPUT_DIR="${OUTPUT_DIR:-}"
command -v makepkg >/dev/null || { echo "makepkg é necessário para gerar o pacote pacman" >&2; exit 2; }
[[ "$(id -u)" -ne 0 ]] || { echo "makepkg não deve ser executado como root" >&2; exit 2; }
command -v curl >/dev/null || { echo "curl é necessário para fixar o checksum do source" >&2; exit 2; }
command -v sha256sum >/dev/null || { echo "sha256sum é necessário para fixar o checksum do source" >&2; exit 2; }
TMP_SOURCE="$(mktemp)"
trap 'rm -f "$TMP_SOURCE"' EXIT
SOURCE_URL="https://github.com/ecarara/SpeedTester/archive/refs/tags/v${VERSION}.tar.gz"
curl --fail --location --silent --show-error "$SOURCE_URL" --output "$TMP_SOURCE"
export APP_VERSION="$VERSION"
export SOURCE_SHA256="$(sha256sum "$TMP_SOURCE" | awk '{print $1}')"
cd "$ARCH_DIR"
makepkg --clean --force "$@"
if [[ -n "$OUTPUT_DIR" ]]; then
  mkdir -p "$OUTPUT_DIR"
  shopt -s nullglob
  packages=("$ARCH_DIR"/speedtester-*.pkg.tar.*)
  ((${#packages[@]} > 0)) || { echo "pacman package was not generated" >&2; exit 1; }
  mv "${packages[@]}" "$OUTPUT_DIR/"
fi
