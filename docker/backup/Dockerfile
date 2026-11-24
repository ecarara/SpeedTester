# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM --platform=$BUILDPLATFORM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61 AS age-builder
ARG TARGETOS
ARG TARGETARCH
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN GOOS="$TARGETOS" GOARCH="$TARGETARCH" go install filippo.io/age/cmd/age@v1.3.2 \
    && GOOS="$TARGETOS" GOARCH="$TARGETARCH" go install filippo.io/age/cmd/age-keygen@v1.3.2 \
    && mkdir /out \
    && find /go/bin -type f \( -name age -o -name age-keygen \) -exec cp {} /out/ \;

FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS ssh-builder
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends build-essential libssl-dev zlib1g-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:9ae44872090cf2f06b3cf9ff147e7f16f309671340763ed2f99248398ae29d5b \
    https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-10.6p2.tar.gz /tmp/openssh.tar.gz
RUN tar -xzf /tmp/openssh.tar.gz -C /tmp \
    && cd /tmp/openssh-10.6p2 \
    && ./configure --prefix=/usr/local --without-pam --without-kerberos5 --without-libedit \
    && make -j2 ssh scp

FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d

RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --only-upgrade zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip uninstall -y setuptools wheel pip

COPY --from=age-builder /out/age /out/age-keygen /usr/local/bin/
COPY --from=age-builder /go/pkg/mod/filippo.io/age@v1.3.2/LICENSE /usr/share/doc/age/LICENSE
COPY --from=ssh-builder /tmp/openssh-10.6p2/ssh /tmp/openssh-10.6p2/scp /usr/local/bin/
COPY --from=ssh-builder /tmp/openssh-10.6p2/LICENCE /usr/share/doc/openssh/LICENCE

COPY scripts/backup.sh scripts/restore.py scripts/check_restore.py scripts/export_backup.py /opt/speedtester-scripts/
RUN chmod 0755 /opt/speedtester-scripts/backup.sh

CMD ["sh", "-c", "set -e; while true; do /opt/speedtester-scripts/backup.sh; sleep \"$BACKUP_INTERVAL_SECONDS\"; done"]
