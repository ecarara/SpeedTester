# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""PyInstaller entry point for the Windows local dashboard API."""
from __future__ import annotations

import os

import uvicorn

from api.server import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("API_PORT", "8000")))
