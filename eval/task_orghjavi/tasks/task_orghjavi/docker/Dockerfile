# Dockerfile — WebAnalytics Platform development environment
#
# Design: this image provides the **toolchain only** (Elixir, Erlang, Node,
# system libs, db clients). The /app workspace is empty — the implementing
# agent populates it with mix.exs, lib/, priv/, etc.
#
# This image is NOT a release container; it is a long-running dev container
# inside which an agent runs `mix deps.get`, `mix ecto.setup`, `mix phx.server`,
# `iex -S mix`, etc.

FROM hexpm/elixir:1.18.4-erlang-27.3.4-alpine-3.21.3

# Switch Alpine mirror to USTC for faster `apk` downloads in CN networks.
# Falls back to dl-cdn if USTC is unavailable.
RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.ustc.edu.cn|g' /etc/apk/repositories || true

# System dependencies for build + runtime.
#
# Kept minimal on purpose: bcrypt_elixir is the only mix dep that needs a real
# C toolchain, hence build-base + libstdc++. brotli/zstd are required by
# Phoenix asset compression. postgresql-client lets the agent psql into the db
# container directly. tzdata provides the IANA database used by stats queries.
RUN apk update && apk add --no-cache \
        build-base \
        libstdc++ libgcc \
        openssl ncurses \
        brotli zstd \
        git curl wget ca-certificates \
        postgresql-client \
        bash tzdata inotify-tools jq \
    && rm -rf /var/cache/apk/*

# Node.js for assets/ + tracker/ npm projects
RUN apk add --no-cache nodejs npm \
    && npm config set update-notifier false \
    && npm config set fund false

# Hex / Rebar3
RUN mix local.hex --force && mix local.rebar --force

WORKDIR /app
RUN chmod -R 777 /app

# Application data dir (mounted as volume)
RUN mkdir -p /var/lib/app && chmod -R 777 /var/lib/app
ENV DEFAULT_DATA_DIR=/var/lib/app

ENV LANG=C.UTF-8
# MIX_ENV=dev so that mix compiles BOTH lib/ (CE) AND extra/lib/ (EE) per
# the upstream's mix.exs `:elixirc_paths` env conditional. ce_dev would skip
# extra/lib/ and break compilation of any EE-only feature
# (see task.md §1.3 + .env comments).
ENV MIX_ENV=dev
ENV LISTEN_IP=0.0.0.0
ENV HTTP_PORT=8000
ENV TERM=xterm-256color

# Note: HEALTHCHECK is intentionally NOT set in the Dockerfile because the
# default CMD (tail -f /dev/null) keeps the container alive without an HTTP
# server. The HEALTHCHECK is set in docker-compose.yml instead, where it can
# be a smart probe that succeeds in BOTH the idle-toolchain state AND the
# fully-running mix-phx-server state.

EXPOSE 8000

# Default command — keep container alive so the agent can `docker exec` and
# run mix tasks against the mounted /app workspace. Once /app contains the
# implementation, the agent (or the smoke-test harness) replaces this with
# `mix phx.server`.
CMD ["tail", "-f", "/dev/null"]
