FROM python:3.10-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    libpq-dev \
    libsasl2-dev \
    libldap2-dev \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    wget \
    git \
    vim \
    jq \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

RUN chown -R 1000:1000 /app

EXPOSE 8013

CMD ["tail", "-f", "/dev/null"]
