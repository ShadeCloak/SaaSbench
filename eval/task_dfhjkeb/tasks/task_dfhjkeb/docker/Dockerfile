FROM node:20-bookworm

RUN corepack enable && corepack prepare yarn@4.4.1 --activate

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    build-essential \
    python3 \
    gnupg \
    lsb-release \
    jq \
    && echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g turbo@^2 tsup vite typescript tsx

WORKDIR /app

RUN chown -R node:node /app

ENV NODE_ENV=development
ENV PORT=8003

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8003/health 2>/dev/null || curl -f http://localhost:8003/ 2>/dev/null || exit 1

CMD ["sh", "-c", "cd /app && corepack enable && yarn install --no-immutable 2>/dev/null; npx tsx packages/server/src/index.ts"]
