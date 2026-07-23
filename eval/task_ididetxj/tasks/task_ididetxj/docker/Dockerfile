# syntax=docker/dockerfile:1.6
#
# Application image — clean development environment for the agent.
#
# Pre-installed:
#   * Node.js 20 LTS (>=20.12 satisfies the engines requirement
#     ">=20.12 <21 || 22 || 24"; the local image registry didn't allow pulling
#     node:22 at build time, so 20-bookworm-slim was used. node 22 is also
#     acceptable if the registry permits it.)
#   * Yarn 4 (Berry; node-modules linker, not PnP)
#   * TypeScript globally available via npx (per-project copy preferred)
#   * PostgreSQL 16 client (psql / pg_dump / pg_restore) + libpq-dev
#   * Redis CLI 7
#   * libvips (image transcoding for sharp), poppler-utils (PDF text), mupdf-tools
#   * git, build-essential, python3 (for native node modules)
#   * curl, wget, jq, ca-certificates
#
# /app is intentionally EMPTY. The agent populates it per task.md §9.
# Default CMD is `tail -f /dev/null` so the container stays up; the agent
# enters via `docker exec -it <container> bash` to develop.

FROM node:20-bookworm-slim

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    NODE_ENV=development \
    APP_PORT=8031 \
    APP_DOMAIN=localhost:8031 \
    YARN_VERSION=4.5.0

# -----------------------------------------------------------------------------
# System dependencies (Debian Bookworm slim from node:22-bookworm)
# -----------------------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential python3 pkg-config \
        postgresql-client libpq-dev \
        redis-tools \
        git curl wget jq ca-certificates \
        tzdata openssl \
    ; \
    rm -rf /var/lib/apt/lists/*

# Note: image processing (sharp), PDF tools, and other optional native
# libraries can be added by the agent on-demand inside `/app` if the
# implementation needs them — they are NOT required for the core HTTP +
# Sequelize + HocusPocus + Bull stack. Sharp ships prebuilt binaries.

# -----------------------------------------------------------------------------
# Yarn 4 (Berry, node-modules linker not PnP)
# -----------------------------------------------------------------------------
RUN corepack enable && \
    corepack prepare "yarn@${YARN_VERSION}" --activate && \
    yarn --version

# -----------------------------------------------------------------------------
# Workspace — kept empty; the agent will copy / clone the project here
# -----------------------------------------------------------------------------
WORKDIR /app
RUN chown -R node:node /app

# Persistent file-storage location (FILE_STORAGE_LOCAL_ROOT_DIR default)
RUN mkdir -p /var/lib/app/data && \
    chown -R node:node /var/lib/app && \
    chmod 1777 /var/lib/app/data
VOLUME ["/var/lib/app/data"]

# -----------------------------------------------------------------------------
# Healthcheck — by default just verifies the container is alive (the agent
# isn't running anything yet). Once the application is up, the HTTP endpoint
# `/_health` is the canonical probe.
# -----------------------------------------------------------------------------
# Health probe — TWO MODES:
#   * BUILD MODE (package.json absent): The agent is still scaffolding (the
#     workspace mount may contain task.md, kb/, scripts/, etc. but no
#     package.json yet). Always report healthy so external orchestrators do
#     not kill the container while the agent is working.
#   * RUNTIME MODE (package.json present): The agent has finished writing the
#     application; require /_health to return OK so evaluator detects boot
#     failures.
# Note: the old logic treated "non-empty /app without package.json" as
# unhealthy (intended to catch a corrupt state), but this was a false-positive
# during normal scaffolding because the workspace mount carries task.md and
# kb/ inputs from the very start.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD bash -c '\
    if [ -f /app/package.json ]; then \
      curl -fsS "http://localhost:${APP_PORT:-8031}/_health" 2>/dev/null | grep -q "OK"; \
    else \
      exit 0; \
    fi'

EXPOSE 8031

USER node

# Default command: stay alive for `docker exec`
CMD ["bash", "-c", "echo \"app container ready (Node $(node -v), yarn $(yarn -v)). /app is empty - populate per task.md §9.\"; tail -f /dev/null"]
