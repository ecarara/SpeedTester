# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61 AS age-builder
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN go install filippo.io/age/cmd/age@v1.3.2 \
    && go install filippo.io/age/cmd/age-keygen@v1.3.2

FROM python:3.11.17-slim-trixie@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip uninstall -y setuptools wheel pip

COPY --from=age-builder /go/bin/age /go/bin/age-keygen /usr/local/bin/

COPY scripts/backup.sh /opt/speedtester-scripts/backup.sh
RUN chmod 0755 /opt/speedtester-scripts/backup.sh

CMD ["sh", "-c", "set -e; while true; do /opt/speedtester-scripts/backup.sh; sleep \"$BACKUP_INTERVAL_SECONDS\"; done"]
