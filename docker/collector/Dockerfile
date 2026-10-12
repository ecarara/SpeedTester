# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM python:3.11.17-slim-trixie@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

ARG TARGETARCH

# The collector includes the fast.com runner, official Ookla CLI and iperf3.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates curl iperf3 iproute2 iputils-ping libidn2-0 tar \
    && if [ "$TARGETARCH" = "amd64" ] || [ -z "$TARGETARCH" ]; then \
       curl -fsSL https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-x86_64.tgz -o /tmp/ookla-speedtest.tgz \
    && echo "5690596c54ff9bed63fa3732f818a05dbc2db19ad36ed68f21ca5f64d5cfeeb7  /tmp/ookla-speedtest.tgz" | sha256sum -c - \
    && tar -xzf /tmp/ookla-speedtest.tgz -C /tmp \
    && install -m 0755 /tmp/speedtest /usr/local/bin/speedtest \
    && rm -rf /tmp/ookla-speedtest.tgz /tmp/speedtest; \
       elif [ "$TARGETARCH" != "arm64" ]; then exit 1; fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y setuptools wheel pip

# Application code (shared, collector, api).
# Stale __pycache__ from the build host (wrong Python version) is cleared first
# so Python 3.11 won't try to load cpython-31x bytecode.
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
COPY app/ /app/
COPY scripts/ /opt/speedtester-scripts/

RUN groupadd --system --gid 10001 speedtester \
    && useradd --system --uid 10001 --gid 10001 --no-create-home speedtester \
    && chown -R speedtester:speedtester /app

# The collector runs speed tests on its configured schedule, forever.
# PYTHONPATH=/app lets `from api.store import ...` resolve under WORKDIR /app.
ENV PYTHONPATH=/app
ENV HOME=/tmp
USER 10001:10001
# Run as a module (`-m collector.collector`) rather than a bare script
# (`python collector/collector.py`). Running a script as `__main__` puts the
# script's own directory (/app/collector) on sys.path[0], which shadows the
# top-level package, so `import collector.speedtest_runner` fails with
# "No module named 'collector.speedtest_runner'; 'collector' is not a package".
# Running it as a module keeps /app on sys.path (as `api`, `shared`, etc. rely
# on), which resolves the collector's internal package imports.
CMD ["python", "-u", "-m", "collector.collector"]
