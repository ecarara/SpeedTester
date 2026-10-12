# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM python:3.11.17-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends age openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip uninstall -y setuptools wheel pip

COPY scripts/backup.sh /opt/speedtester-scripts/backup.sh
RUN chmod 0755 /opt/speedtester-scripts/backup.sh

CMD ["sh", "-c", "set -e; while true; do /opt/speedtester-scripts/backup.sh; sleep \"$BACKUP_INTERVAL_SECONDS\"; done"]
