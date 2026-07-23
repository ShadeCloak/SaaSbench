FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg2 ca-certificates lsb-release software-properties-common \
    git vim unzip zip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Java 17 (OpenJDK)
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk && \
    rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Maven 3.9.x
ARG MAVEN_VERSION=3.9.6
RUN curl -fsSL https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz \
    | tar xz -C /opt && \
    ln -s /opt/apache-maven-${MAVEN_VERSION} /opt/maven
ENV MAVEN_HOME=/opt/maven
ENV PATH="${MAVEN_HOME}/bin:${PATH}"

# Node.js 20.x
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Yarn 3.5.1 (via corepack)
RUN corepack enable && corepack prepare yarn@3.5.1 --activate

# MongoDB 7.0 server + shell
RUN curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
    gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg && \
    echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
    > /etc/apt/sources.list.d/mongodb-org-7.0.list && \
    apt-get update && apt-get install -y mongodb-org && \
    rm -rf /var/lib/apt/lists/*

# Redis 7.x
RUN apt-get update && apt-get install -y --no-install-recommends redis-server && \
    rm -rf /var/lib/apt/lists/*

# Data directories
RUN mkdir -p /data/db /data/redis /var/log/mongodb /var/log/redis && \
    chown -R mongodb:mongodb /data/db /var/log/mongodb && \
    chown -R redis:redis /data/redis /var/log/redis

# Working directory
RUN mkdir -p /app && chmod 777 /app
WORKDIR /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY init-db.js /docker-entrypoint-initdb.d/init-db.js

EXPOSE 8007 27017 6379

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD mongosh --quiet --eval "db.adminCommand('ping')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
