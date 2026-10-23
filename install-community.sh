#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# Compatibility filename: use the single stable installer and collector.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$project_dir/install-speedtester-client.py" "$@"
