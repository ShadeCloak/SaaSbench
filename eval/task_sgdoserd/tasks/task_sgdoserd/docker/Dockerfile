################################################################################
# task_sgdoserd — Self-hosted team collaboration platform build environment
#
# Provides a clean Linux environment with Go 1.25.8, Node 24, npm 11, PostgreSQL
# client tools, and the build essentials needed to compile both the Go server
# and the React + TypeScript webapp. Crucially, /app is empty — the agent must
# populate it (clone or scaffold the project) and run the build pipeline.
################################################################################

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV LANG=C.UTF-8

# -----------------------------------------------------------------------------
# 1) System packages
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        git \
        gnupg \
        lsb-release \
        build-essential \
        pkg-config \
        unzip \
        zip \
        bzip2 \
        xz-utils \
        jq \
        make \
        gcc \
        g++ \
        libssl-dev \
        zlib1g-dev \
        libpcre3-dev \
        libffi-dev \
        python3 \
        python3-pip \
        netcat-openbsd \
        iputils-ping \
        procps \
        less \
        vim \
        sqlite3 \
        tini \
        # For document/text/image processing the platform needs at runtime:
        libsodium-dev \
        libheif-dev \
        webp \
        libwebp-dev \
        libxml2-dev \
        libonig-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 2) PostgreSQL client (matches server major version 14)
# -----------------------------------------------------------------------------
RUN install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
        https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-14 \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 3) Go 1.25.8
#     The platform's go.mod declares `go 1.25.8`. Earlier toolchains will fail
#     because some new stdlib features (e.g., go/types iter helpers) are used.
# -----------------------------------------------------------------------------
ENV GO_VERSION=1.25.8
RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "amd64" ]; then GOARCH=amd64; \
       elif [ "$ARCH" = "arm64" ]; then GOARCH=arm64; \
       else echo "Unsupported arch: $ARCH" && exit 1; fi \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${GOARCH}.tar.gz" -o /tmp/go.tar.gz \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz \
    && /usr/local/go/bin/go version
ENV PATH="/usr/local/go/bin:${PATH}"
ENV GOPATH="/go"
ENV PATH="${GOPATH}/bin:${PATH}"
RUN mkdir -p /go/src /go/bin /go/pkg && chmod -R 777 /go

# -----------------------------------------------------------------------------
# 4) Node.js 24.11 + npm 11 (the webapp pins this in .nvmrc)
# -----------------------------------------------------------------------------
ENV NODE_VERSION=24.11.0
RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "amd64" ]; then NODE_ARCH=x64; \
       elif [ "$ARCH" = "arm64" ]; then NODE_ARCH=arm64; \
       else echo "Unsupported arch: $ARCH" && exit 1; fi \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
        -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && node --version \
    && npm install -g npm@11 \
    && npm --version

# -----------------------------------------------------------------------------
# 5) Build-time helpers used by the platform's Makefile
#     These are HARD-required: mockgen powers `make mocks`, gotestsum powers
#     `make test`. If installation fails the image build must abort so that
#     the harness sees a deterministic failure instead of a silently broken
#     test target downstream.
# -----------------------------------------------------------------------------
RUN go install github.com/golang/mock/mockgen@v1.6.0 \
 && go install gotest.tools/gotestsum@latest \
 && mockgen --version \
 && gotestsum --version

# -----------------------------------------------------------------------------
# 6) Workspace
# -----------------------------------------------------------------------------
WORKDIR /app
RUN chmod 0777 /app

ENV APP_PORT=8028
ENV APP_DATA_DIR=/app/data
ENV APP_LOCALSOCKETPATH=/var/tmp/app_local.socket

EXPOSE 8028
EXPOSE 8067

# -----------------------------------------------------------------------------
# 7) Healthcheck — agent's compiled server must respond on /api/v4/system/ping
# -----------------------------------------------------------------------------
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS http://localhost:${APP_PORT}/api/v4/system/ping >/dev/null 2>&1 \
        || curl -fsS http://localhost:${APP_PORT}/ >/dev/null 2>&1 \
        || exit 1

# Default command: keep the container alive so the test harness can `docker exec`
# into it to run build steps. The agent's ENTRYPOINT will be invoked by the
# harness via `docker compose exec app <cmd>` once code is in /app.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "-c", "echo 'task_sgdoserd build container ready. Workspace=/app (empty). DB=db:5432 (mapped to host :5450). App port=8028.' && tail -f /dev/null"]
