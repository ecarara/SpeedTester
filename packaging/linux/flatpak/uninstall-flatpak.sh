#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

command -v flatpak >/dev/null || { echo "flatpak não encontrado" >&2; exit 2; }
flatpak --user uninstall --noninteractive io.github.ecarara.SpeedTester
echo "[speedtester] Flatpak removido; dados de outros serviços foram preservados"
