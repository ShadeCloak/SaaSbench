FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# System dependencies
RUN apt-get update && apt-get install -y \
    locales \
    curl \
    wget \
    gnupg2 \
    lsb-release \
    software-properties-common \
    build-essential \
    git \
    libssl-dev \
    libreadline-dev \
    zlib1g-dev \
    libyaml-dev \
    libffi-dev \
    libgdbm-dev \
    libncurses5-dev \
    libpq-dev \
    imagemagick \
    libmagickwand-dev \
    libvips-dev \
    libxml2-dev \
    libxslt1-dev \
    libjemalloc-dev \
    libcurl4-openssl-dev \
    pkg-config \
    autoconf \
    bison \
    rustc \
    cargo \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# PostgreSQL client (for psql, createdb, pg_isready)
RUN sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
    && apt-get update \
    && apt-get install -y postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# Redis CLI
RUN apt-get update && apt-get install -y redis-tools && rm -rf /var/lib/apt/lists/*

# Ruby 3.4 via ruby-install + chruby
ENV RUBY_VERSION=3.4.2
RUN wget -O ruby-install.tar.gz https://github.com/postmodern/ruby-install/releases/download/v0.9.4/ruby-install-0.9.4.tar.gz \
    && tar -xzf ruby-install.tar.gz \
    && cd ruby-install-0.9.4 && make install && cd .. \
    && rm -rf ruby-install-0.9.4 ruby-install.tar.gz \
    && ruby-install --system ruby ${RUBY_VERSION} -- --with-jemalloc \
    && gem update --system \
    && gem install bundler

# Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# pnpm 10.28
RUN npm install -g pnpm@10.28.0

# Verify installations
RUN ruby -v && gem -v && bundler -v && node -v && pnpm -v

# Working directory (empty — agent writes code here)
WORKDIR /app

# Expose application port
EXPOSE 8020

# Default command: keep container alive for interactive development
CMD ["bash", "-c", "tail -f /dev/null"]
