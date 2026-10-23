#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

SOURCE_DIR="${SPEEDTESTER_SOURCE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VERSION="${APP_VERSION:-0.3.0}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_DIR/dist}"
command -v git >/dev/null || { echo "git é necessário para gerar o source tarball" >&2; exit 2; }
cd "$SOURCE_DIR"
[[ -d .git ]] || { echo "o source tarball deve ser gerado dentro de um checkout Git" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
git archive --format=tar.gz --prefix="SpeedTester-${VERSION}/" --output="$OUTPUT_DIR/SpeedTester-${VERSION}.tar.gz" HEAD
echo "$OUTPUT_DIR/SpeedTester-${VERSION}.tar.gz"
