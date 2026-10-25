# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS iperf-builder
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends build-essential libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:1c0d0fb02c52626111d6e132db80edfbf27bbaff8bd9245df2a371dcb0b35a92 \
    https://github.com/esnet/iperf/releases/download/3.22/iperf-3.22.tar.gz /tmp/iperf.tar.gz
RUN tar -xzf /tmp/iperf.tar.gz -C /tmp \
    && cd /tmp/iperf-3.22 \
    && ./configure --disable-shared --enable-static --without-sctp --with-openssl=/usr \
    && make -j2

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58

ARG TARGETARCH
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

# The collector includes the fast.com runner, official Ookla CLI and iperf3.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates iproute2 iputils-ping libidn2-0 tar \
    && if [ "$TARGETARCH" = "amd64" ] || [ -z "$TARGETARCH" ]; then \
       python -c "import urllib.request; urllib.request.urlretrieve('https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-x86_64.tgz','/tmp/ookla-speedtest.tgz')" \
    && echo "5690596c54ff9bed63fa3732f818a05dbc2db19ad36ed68f21ca5f64d5cfeeb7  /tmp/ookla-speedtest.tgz" | sha256sum -c - \
    && tar -xzf /tmp/ookla-speedtest.tgz -C /tmp \
    && install -m 0755 /tmp/speedtest /usr/local/bin/speedtest \
    && rm -rf /tmp/ookla-speedtest.tgz /tmp/speedtest; \
       elif [ "$TARGETARCH" != "arm64" ]; then exit 1; fi \
    && rm -rf /var/lib/apt/lists/*

COPY --from=iperf-builder /tmp/iperf-3.22/src/iperf3 /usr/local/bin/iperf3
COPY --from=iperf-builder /tmp/iperf-3.22/LICENSE /usr/share/doc/iperf3/LICENSE

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && python -m pip uninstall -y setuptools wheel pip

# Application code (shared, collector, api).
# Stale __pycache__ from the build host (wrong Python version) is cleared first
# so Python 3.14 won't try to load bytecode from another interpreter.
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
