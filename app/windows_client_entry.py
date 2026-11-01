# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""PyInstaller entry point for the Windows scheduled measurement client."""
import sys


if __name__ == "__main__":
    if sys.argv[1:] == ["--runtime-info"]:
        from shared.frozen_runtime import print_runtime_info
        print_runtime_info()
    else:
        from collector.collector import main
        raise SystemExit(main())
