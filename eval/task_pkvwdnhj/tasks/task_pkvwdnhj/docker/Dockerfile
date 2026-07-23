FROM golang:1.24-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    make \
    gcc \
    g++ \
    postgresql-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8010/health || exit 1

CMD ["bash"]
