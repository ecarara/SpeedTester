# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""PyInstaller entry point for the Windows scheduled measurement client."""
from collector.collector import main


if __name__ == "__main__":
    raise SystemExit(main())
