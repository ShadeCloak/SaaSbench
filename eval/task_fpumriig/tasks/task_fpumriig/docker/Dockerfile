FROM node:24-bookworm

RUN corepack enable && corepack prepare yarn@4.13.0 --activate

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    jq \
    git \
    build-essential \
    python3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g nx@latest

WORKDIR /app

RUN chown -R node:node /app

EXPOSE 8034

CMD ["tail", "-f", "/dev/null"]
