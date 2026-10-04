FROM python:3.13-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/python -m pip install -r /tmp/requirements.txt

FROM python:3.13-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QUOTA_STATE_FILE=/data/quota.sqlite3

RUN groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --no-create-home --shell /usr/sbin/nologin bot \
    && mkdir /data \
    && chown bot:bot /data

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY main.py overseerr.py shared.py views.py ./
COPY overseerrapi/ ./overseerrapi/
COPY quota/ ./quota/

VOLUME ["/data"]

USER bot

CMD ["python", "main.py"]
