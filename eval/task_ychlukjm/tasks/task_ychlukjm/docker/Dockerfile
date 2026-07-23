FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg2 software-properties-common ca-certificates \
    git unzip zip jq vim nano less \
    build-essential libffi-dev libssl-dev zlib1g-dev \
    python3 python3-pip python3-venv python3-dev \
    default-mysql-client netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /usr/share/keyrings/adoptium-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/adoptium-archive-keyring.gpg] https://packages.adoptium.net/artifactory/deb $(lsb_release -cs) main" > /etc/apt/sources.list.d/adoptium.list \
    && apt-get update && apt-get install -y --no-install-recommends temurin-17-jdk \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/temurin-17-jdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

RUN wget -qO /tmp/gradle.zip "https://services.gradle.org/distributions/gradle-8.4-bin.zip" \
    && unzip -q /tmp/gradle.zip -d /opt \
    && ln -s /opt/gradle-8.4/bin/gradle /usr/local/bin/gradle \
    && rm /tmp/gradle.zip \
    || echo "Gradle download skipped (will be installed by wrapper if needed)"

ENV GRADLE_HOME=/opt/gradle-8.4
ENV PATH="${GRADLE_HOME}/bin:${PATH}"

WORKDIR /app

RUN mkdir -p /app && chmod 777 /app

EXPOSE 8019

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${APPLICATION_PORT:-8019}/health || exit 1

CMD ["bash"]
