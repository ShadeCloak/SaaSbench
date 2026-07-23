FROM node:20-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3 \
    git \
    curl \
    wget \
    vim \
    jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN chown -R node:node /app

EXPOSE 8002

CMD ["tail", "-f", "/dev/null"]
