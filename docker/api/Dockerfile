# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

# Agg uses the bundled wheel libraries; no OpenGL or X11 runtime is needed.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y setuptools wheel pip

# Application code + the static dashboard HTML.
COPY app/ /app/
COPY scripts/restore.py /opt/speedtester-scripts/restore.py

RUN groupadd --system --gid 10001 speedtester \
    && useradd --system --uid 10001 --gid 10001 --no-create-home speedtester \
    && mkdir -p /tmp/matplotlib \
    && chown -R speedtester:speedtester /app /tmp/matplotlib

ENV HOME=/tmp
ENV MPLCONFIGDIR=/tmp/matplotlib
USER 10001:10001

CMD ["python", "-u", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
