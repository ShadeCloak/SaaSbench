FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_PORT=8029 \
    APP_UPSTREAM_PORT=18029

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        curl \
        gettext-base \
        gcc \
        git \
        libpq-dev \
        netcat-openbsd \
        nginx \
        postgresql-client \
        procps \
        redis-tools \
        tini \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://nodejs.org/dist/v22.16.0/node-v22.16.0-linux-x64.tar.xz \
      -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && pip install --no-cache-dir psycopg2-binary requests websockets openai

WORKDIR /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY nginx.conf /usr/local/share/task-bootstrap/nginx.conf.template
COPY placeholder_server.py /usr/local/share/task-bootstrap/placeholder_server.py

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /app /run/nginx /var/lib/nginx /var/log/nginx

EXPOSE 8029

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=10 \
  CMD curl -fsS "http://127.0.0.1:${APP_PORT:-8029}/healthz" \
  || curl -fsS "http://127.0.0.1:${APP_PORT:-8029}/" \
  || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
