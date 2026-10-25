# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Cross-platform frozen collector, independent of an installed Python."""
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
    # Frozen console output should reach the service journal immediately.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(line_buffering=True)
    from collector.collector import main as run_collector
    return run_collector()


if __name__ == "__main__":
    raise SystemExit(main())

