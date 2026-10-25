# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Cross-platform frozen local API; diagnostics must not open the database."""
import argparse

from shared.frozen_runtime import prepare_system_children, print_runtime_info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-info", action="store_true")
    args = parser.parse_args(argv)
    if args.runtime_info:
        print_runtime_info()
        return 0
    prepare_system_children()
    # load_settings reads the user configuration before selecting the API port.
    import uvicorn
    from api.server import app, settings
    uvicorn.run(app, host="127.0.0.1", port=settings.api_port, workers=1,
                loop="asyncio", http="h11")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

