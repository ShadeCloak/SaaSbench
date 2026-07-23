FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y \
    curl wget gnupg2 ca-certificates lsb-release software-properties-common \
    git unzip zip build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm@9 \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN curl -fsSL https://archive.apache.org/dist/maven/maven-3/3.9.8/binaries/apache-maven-3.9.8-bin.tar.gz | tar xz -C /opt \
    && ln -s /opt/apache-maven-3.9.8 /opt/maven

ENV MAVEN_HOME=/opt/maven
ENV PATH="${MAVEN_HOME}/bin:${PATH}"

WORKDIR /app

ENV APP_DB=postgres
ENV APP_DB_URL=jdbc:postgresql://db:5432/app_cvyocaao
ENV APP_DB_USERNAME=appcvyocaao
ENV APP_DB_PASSWORD=app123cvyocaao
ENV APP_HTTP_PORT=8027
ENV APP_HOSTNAME_STRICT=false
ENV APP_HTTP_ENABLED=true
ENV APP_CACHE=local

EXPOSE 8027

CMD ["tail", "-f", "/dev/null"]
