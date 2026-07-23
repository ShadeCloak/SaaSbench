# Stage 3 — Docker container providing a "clean development environment"
# Pre-installed: Node 20 + Yarn 4.12 (corepack) + Git + system tools + DB/Redis clients
# Not pre-installed: project code / node_modules / prisma client (the agent builds inside /app)

FROM node:20-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    NODE_ENV=development \
    NEXT_TELEMETRY_DISABLED=1 \
    APP_TELEMETRY_DISABLED=1 \
    PORT=3000

# ---------- system dependencies ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    libcairo2-dev \
    libgif-dev \
    libjpeg-dev \
    libpango1.0-dev \
    librsvg2-dev \
    libpixman-1-dev \
    libpq-dev \
    libssl-dev \
    netcat-openbsd \
    openssl \
    pkg-config \
    postgresql-client-15 \
    procps \
    python3 \
    redis-tools \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# ---------- Yarn 4.12+ via Corepack ----------
RUN corepack enable \
    && corepack prepare yarn@4.12.0 --activate \
    && yarn --version

# ---------- Workspace directory (where the agent writes code) ----------
WORKDIR /app

RUN mkdir -p /app && chmod -R 777 /app

# expose the webapp port
# task.md §8.1 mandates: host port 8016 -> container port 3000 (mapped in docker-compose.yml)
# EXPOSE 3000 in the Dockerfile is because the app listens on 3000 inside the container; external access goes through docker-compose's ports mapping
EXPOSE 3000

# health check: after the app starts, hit the root page or the health endpoint
# - prefer /api/healthz (the agent should implement it, ideally returning {status:"ok"})
# - fall back to / returning 2xx/3xx (landing page)
# the startup period is long (the first yarn install + prisma generate + build is slow), so start-period is set to 600s
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=10 \
    CMD curl -fsS http://localhost:3000/api/healthz \
        || curl -fsSI http://localhost:3000/ \
        || exit 1

# defaults to bash; the agent runs commands via docker exec to build the app
# after deployment this can be changed to CMD ["yarn","start"]
CMD ["bash"]
