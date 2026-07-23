FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates gnupg lsb-release curl wget && \
    echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/pgdg.gpg && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libssl-dev \
    libreadline-dev \
    zlib1g-dev \
    libyaml-dev \
    libffi-dev \
    libpq-dev \
    libvips-dev \
    imagemagick \
    libmagickwand-dev \
    libxml2-dev \
    libxslt1-dev \
    redis-tools \
    postgresql-client-16 \
    software-properties-common \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

ENV RUBY_VERSION=3.4.4
RUN git clone https://github.com/rbenv/rbenv.git /root/.rbenv && \
    git clone https://github.com/rbenv/ruby-build.git /root/.rbenv/plugins/ruby-build && \
    /root/.rbenv/plugins/ruby-build/bin/ruby-build $RUBY_VERSION /usr/local && \
    rm -rf /root/.rbenv

RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g pnpm
RUN gem install bundler --no-document

WORKDIR /app

ENV RAILS_ENV=development \
    NODE_ENV=development \
    BUNDLE_PATH=/usr/local/bundle \
    GEM_HOME=/usr/local/bundle \
    PATH="/usr/local/bundle/bin:$PATH" \
    PORT=8018

EXPOSE 8018

COPY workspace/bin/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY workspace/bin/create_eval_users.rb /usr/local/bin/create_eval_users.rb
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

CMD ["/usr/local/bin/docker-entrypoint.sh"]
