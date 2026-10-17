#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$DATA_HOME/applications/speedtester.desktop"
rm -f "$DATA_HOME/icons/hicolor/512x512/apps/speedtester.png"
rm -f "$DATA_HOME/speedtester/SpeedTester.AppImage"
rmdir "$DATA_HOME/icons/hicolor/512x512/apps" "$DATA_HOME/icons/hicolor/512x512" "$DATA_HOME/icons/hicolor" 2>/dev/null || true
rmdir "$DATA_HOME/speedtester" 2>/dev/null || true
echo "[speedtester] AppImage removido; os demais dados foram preservados"
