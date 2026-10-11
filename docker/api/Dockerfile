# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

FROM python:3.11-slim@sha256:be1575ed968de893bd54f4c56315ff7c4736ce522c1bca08fd521731aafc0d76

# matplotlib (Agg backend) needs a couple of system libs to render the chart.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code + the static dashboard HTML.
COPY app/ /app/

RUN groupadd --system --gid 10001 speedtester \
    && useradd --system --uid 10001 --gid 10001 --no-create-home speedtester \
    && mkdir -p /tmp/matplotlib \
    && chown -R speedtester:speedtester /app /tmp/matplotlib

ENV HOME=/tmp
ENV MPLCONFIGDIR=/tmp/matplotlib
USER 10001:10001

CMD ["python", "-u", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
