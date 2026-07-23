FROM ruby:3.4-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    RAILS_ENV=development \
    BUNDLE_PATH=/usr/local/bundle

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libcurl4-openssl-dev \
    libffi-dev \
    libyaml-dev \
    libreadline-dev \
    libssl-dev \
    zlib1g-dev \
    imagemagick \
    libvips-dev \
    postgresql-client \
    redis-tools \
    ca-certificates \
    gnupg \
    wget \
    unzip \
    jq \
    libclang-dev \
    clang \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN gem install bundler:2.6.2 --no-document

WORKDIR /app

RUN mkdir -p /app/tmp /app/log /app/storage \
    && chmod -R 777 /app

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:3000/health || exit 1

CMD ["bash"]
