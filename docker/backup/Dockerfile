# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM python:3.11-slim@sha256:be1575ed968de893bd54f4c56315ff7c4736ce522c1bca08fd521731aafc0d76

RUN apt-get update && apt-get install -y --no-install-recommends age openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/backup.sh /opt/speedtester-scripts/backup.sh
RUN chmod 0755 /opt/speedtester-scripts/backup.sh

CMD ["sh", "-c", "set -e; while true; do /opt/speedtester-scripts/backup.sh; sleep \"$BACKUP_INTERVAL_SECONDS\"; done"]
