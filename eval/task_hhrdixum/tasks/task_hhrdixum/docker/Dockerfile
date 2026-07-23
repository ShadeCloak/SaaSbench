# syntax=docker/dockerfile:1.6
#
# task_hhrdixum (Inventory Management & Light-MRP) — application image
#
# Provides a clean development environment for the agent: Python 3.12, Node.js 20,
# all native libraries required by WeasyPrint, Pillow, LDAP, SAML, OpenTelemetry,
# and the django-money + Pint stack. The /app directory is intentionally empty —
# the agent is expected to populate it.
#
# Build:    docker compose build
# Run:      docker compose up -d
# Shell in: docker compose exec app bash
#
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    POETRY_VIRTUALENVS_CREATE=false \
    NODE_ENV=development \
    NODE_OPTIONS=--max-old-space-size=4096

# ---- 1. Base system & tooling ------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        # Core build tooling
        build-essential \
        ca-certificates \
        curl \
        git \
        gnupg \
        wget \
        unzip \
        jq \
        make \
        pkg-config \
        # PostgreSQL client (for pg_isready, psql, libpq for psycopg)
        libpq-dev \
        postgresql-client \
        # Redis client (debug: redis-cli)
        redis-tools \
        # Pillow native deps
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
        libtiff-dev \
        libopenjp2-7-dev \
        # WeasyPrint native deps
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu \
        fonts-liberation \
        # LDAP optional auth
        libldap2-dev \
        libsasl2-dev \
        # SAML SSO via xmlsec
        xmlsec1 \
        libxmlsec1-dev \
        libxml2-dev \
        libxslt1-dev \
        # MySQL client headers (django supports MySQL too)
        default-libmysqlclient-dev \
        # MIME / icons for fielduploads
        libmagic1 \
        # Image / barcode rendering helpers
        librsvg2-bin \
        # Misc
        gettext \
        locales \
        tzdata \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. Node.js 20 + yarn (frontend) -----------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && corepack prepare yarn@stable --activate \
    && corepack prepare pnpm@latest --activate \
    && node -v && yarn -v && pnpm -v

# ---- 3. Python tooling -------------------------------------------------------
# Pre-install only the *toolchain* level packages that every Django project
# in this stack needs (gunicorn, uvicorn, watchdog).  Application packages
# (Django, DRF, etc.) are NOT installed here — the agent must declare them in
# the workspace's requirements file.
RUN pip install --upgrade pip setuptools wheel \
    && pip install \
        gunicorn==23.0.0 \
        uvicorn==0.32.0 \
        watchdog==5.0.3 \
        # Useful diagnostics inside the container
        ipython==8.28.0 \
        httpie==3.2.4

# ---- 4. Workspace layout -----------------------------------------------------
WORKDIR /app

# Persistent runtime directories — agents may use these freely
RUN mkdir -p \
        /app/data \
        /app/static \
        /app/media \
        /app/logs \
        /app/plugins \
        /app/run \
    && chmod -R 777 /app

# Add a tiny entrypoint helper (no-op by default — agent overrides via compose `command`)
COPY --chmod=0755 <<'EOF' /usr/local/bin/app-entrypoint
#!/usr/bin/env bash
set -euo pipefail
echo "[app-entrypoint] task_hhrdixum environment ready."
echo "  Python:  $(python -V 2>&1)"
echo "  Pip:     $(pip -V 2>&1)"
echo "  Node:    $(node -v)"
echo "  Yarn:    $(yarn -v)"
echo "  Pnpm:    $(pnpm -v)"
echo "  PG cli:  $(pg_isready --version 2>&1)"
echo "  Redis:   $(redis-cli --version)"
echo "  Workdir: $(pwd)  (mounted from host ./workspace)"
exec "$@"
EOF

EXPOSE 8000

# NOTE: the runtime healthcheck is defined in docker-compose.yml.  An image-
# level HEALTHCHECK is intentionally omitted to avoid the two probes drifting
# (port, retry policy, etc.).  When running the image bare with `docker run`
# (no compose), pass `--health-cmd ...` explicitly.

ENTRYPOINT ["/usr/local/bin/app-entrypoint"]
CMD ["bash"]
