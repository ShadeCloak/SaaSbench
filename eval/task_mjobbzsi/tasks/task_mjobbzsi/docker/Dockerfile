FROM node:20-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    build-essential \
    python3 \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g webpack webpack-cli webpack-dev-server

RUN rm -f /etc/nginx/sites-enabled/default

COPY nginx.conf /etc/nginx/sites-enabled/conference.conf

RUN mkdir -p /app && chown -R node:node /app

WORKDIR /app

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
