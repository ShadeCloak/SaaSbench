# syntax=docker/dockerfile:1.6
#
# LMS application image — clean development environment for the agent.
#
# Pre-installed:
#   * Ruby 3.3 (Rails 8 stack)
#   * Bundler 2.6.x (matches Gemfile.lock BUNDLED WITH expectation)
#   * Node.js 20.x (LTS) + Yarn 1.x (Classic) — Rspack delivered as a npm
#     prebuilt binary (@rspack/core / @rspack/cli), so no Rust toolchain is
#     required at build time.
#   * PostgreSQL 16 client (psql/pg_dump/pg_restore) + libpq-dev
#   * Redis CLI
#   * Image processing: ImageMagick + libvips
#   * PDF parsing: poppler-utils (pdftotext)
#   * SAML / LDAP runtime: xmlsec1, ldap-utils
#
# /app is intentionally EMPTY. The agent populates it per task.md §9.
# Default CMD is `bash` for interactive setup; Stage 7 smoke test uses
# `docker compose run --rm web bin/rails server -b 0.0.0.0 -p 8017` to start
# Puma directly. The HEALTHCHECK below is a PROCESS-LIVENESS probe (the bash
# shell + descendants) — once the agent runs Puma, replace it with an HTTP
# probe by setting `HEALTHCHECK_HTTP_MODE=1` in the environment (see entrypoint
# guidance in docker-compose.yml).

FROM ruby:3.3-slim-bookworm

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    RAILS_ENV=development \
    BUNDLE_PATH=/usr/local/bundle \
    BUNDLE_BIN=/usr/local/bundle/bin \
    GEM_HOME=/usr/local/bundle \
    NODE_ENV=development \
    PATH=/usr/local/bundle/bin:/usr/local/bin:/usr/bin:/bin \
    APP_DOMAIN=localhost:8017 \
    APP_PORT=8017

# -----------------------------------------------------------------------------
# System dependencies
# -----------------------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        # build toolchain (for native gem extensions)
        build-essential autoconf automake libtool pkg-config \
        # version control + transport
        git ca-certificates curl wget gnupg lsb-release \
        # PostgreSQL client + dev headers (pg gem)
        libpq-dev \
        # Redis client
        redis-tools \
        # XML / XSLT (nokogiri, saml2)
        libxml2-dev libxslt1-dev libxmlsec1-dev xmlsec1 \
        # SSL / crypto
        libssl-dev libffi-dev libreadline-dev libyaml-dev libgmp-dev zlib1g-dev \
        # ICU (charlock_holmes)
        libicu-dev \
        # Image processing
        imagemagick libmagickwand-dev libvips-dev \
        # PDF parsing
        poppler-utils \
        # LDAP (net-ldap + LDAP SSO)
        libldap-common ldap-utils \
        # Locale
        locales \
        # Debug / scripting helpers
        jq netcat-openbsd unzip vim-tiny less \
    ; \
    rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# PostgreSQL 16 client (LOCKED to v16; task.md §8.1 says "16 or above" but we
# fix the client to match the db service; the db service is also pinned to 16
# in docker-compose.yml. To upgrade later, change BOTH together.)
# -----------------------------------------------------------------------------
RUN set -eux; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-16; \
    rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Node.js 20.x (LTS) + Yarn 1.x (Classic ONLY; corepack NOT enabled to avoid
# yarn 2/3/4 Berry resolving over Classic; Rspack via npm precompiled binary)
# -----------------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    # Install Yarn 1.x Classic via npm. Do NOT enable corepack to keep
    # `yarn` resolving to 1.x.
    npm install -g yarn@1.22.22; \
    rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Bundler 2.6.x (matches BUNDLED WITH that Rails 8 typically generates;
# task.md §8.2 / §9.A documents this version explicitly)
# -----------------------------------------------------------------------------
RUN gem install bundler:2.6.2 rake --no-document

# -----------------------------------------------------------------------------
# Workspace
# -----------------------------------------------------------------------------
WORKDIR /app

# Pre-create writable directories Rails 8 expects on boot
RUN set -eux; \
    mkdir -p /app/tmp/cache /app/tmp/pids /app/tmp/sockets \
             /app/log /app/storage /app/public/dist; \
    chmod -R 0777 /app/tmp /app/log /app/storage /app/public

# Locale (UTF-8)
RUN set -eux; \
    sed -i '/en_US.UTF-8/s/^# //' /etc/locale.gen; \
    locale-gen en_US.UTF-8

# -----------------------------------------------------------------------------
# Health check — PROCESS-LIVENESS probe by default.
# Once the agent boots Puma (via `docker compose run web bin/rails server`),
# the HTTP healthcheck in docker-compose.yml takes over via the `web` service
# definition (which overrides this Dockerfile-level HEALTHCHECK).
# -----------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pgrep -f bash >/dev/null || exit 1

EXPOSE 8017

# Default CMD: drop into bash for the agent to run setup. The agent typically:
#   bundle install
#   bin/rails db:create db:migrate db:initial_setup
#   yarn install && yarn build
#   bin/rails server -b 0.0.0.0 -p 8017
# Once the server is running, override the HEALTHCHECK by exec-ing into the
# container and using `curl -f http://localhost:8017/health_check` from outside.
# (Endpoint name aligns with KB-0381 / task.md §5.1.6.)
CMD ["bash"]
