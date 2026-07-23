# Stage 3 — Docker container: a clean development environment for the agent.
#
# Pre-installed:
#   - Python 3.12 + Poetry 1.7+ (backend)
#   - Node 20 + npm (frontend build)
#   - libpq-dev / libssl-dev / build-essential (Python C extensions)
#   - postgresql-client-15 (psql for evaluator DB checks)
#   - git / curl / jq / netcat (general tooling)
#
# NOT pre-installed:
#   - The application code itself (mounted via /app from host workspace/)
#   - Python virtualenv / node_modules (the agent runs `poetry install` and `npm ci` after writing code)
#
# task.md §8.5 alignment.

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.7.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    NODE_ENV=development \
    DJANGO_SETTINGS_MODULE=app.settings.local \
    PORT=8000

# ---------- System dependencies ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    libffi-dev \
    libldap2-dev \
    libpq-dev \
    libsasl2-dev \
    libssl-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    netcat-openbsd \
    openssl \
    pkg-config \
    postgresql-client-15 \
    procps \
    redis-tools \
    unzip \
    wget \
    xmlsec1 \
    && rm -rf /var/lib/apt/lists/*

# ---------- Node.js 20 (for frontend bundling) ----------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    node --version && \
    npm --version

# ---------- Poetry (installed via pip from PyPI; pinned version, no remote install script) ----------
# Avoid `curl https://install.python-poetry.org | python3` — that script is fetched at build time and
# can fail or change behaviour in offline / restricted networks. Pinning via pip gives reproducible builds.
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}" && \
    poetry --version

# ---------- Workspace directory (where the agent writes code) ----------
WORKDIR /app

RUN mkdir -p /app && chmod -R 777 /app

# Expose webapp port
# task.md §8.2 mandate: host port 8023 → container port 8000 (mapped via docker-compose).
# EXPOSE 8000 because the application listens on container port 8000; external access goes through
# docker-compose's `ports` mapping.
EXPOSE 8000

# Healthcheck: hits /health/ once the application is running.
# Long start period (10 min) because first-time `poetry install` + `npm ci` + `manage.py migrate`
# can take several minutes on a slow connection.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=10 \
    CMD curl -fsS http://localhost:8000/health/ \
        || curl -fsSI http://localhost:8000/ \
        || exit 1

# Default to bash; the agent will use `docker exec` to install dependencies and run the server.
# Production deployments may switch to:
#   CMD ["gunicorn", "app.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
CMD ["bash"]
