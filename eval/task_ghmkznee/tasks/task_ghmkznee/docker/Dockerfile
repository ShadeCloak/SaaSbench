FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    pkg-config \
    ca-certificates \
    gnupg \
    lsb-release \
    unzip \
    jq \
    postgresql-client \
    libpq-dev \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY go1.25.8.linux-amd64.tar.gz /tmp/go.tar.gz
RUN tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz

ENV PATH="/usr/local/go/bin:/root/go/bin:${PATH}"
ENV GOPATH="/root/go"

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable && corepack prepare yarn@4.6.0 --activate

RUN npm install -g nx@latest webpack@5 webpack-cli@5 sass

WORKDIR /app

RUN go version && node --version && yarn --version && psql --version

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8025

HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=5 \
    CMD curl -f http://localhost:8025/api/health || exit 1

CMD ["/usr/local/bin/start.sh"]
