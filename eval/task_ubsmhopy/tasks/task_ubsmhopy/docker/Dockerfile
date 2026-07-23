FROM rust:1.84-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    libpq-dev \
    postgresql-client \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN cargo install diesel_cli --no-default-features --features postgres

WORKDIR /app

ENV ROCKET_ADDRESS=0.0.0.0
ENV ROCKET_PORT=8035
ENV ROCKET_LOG_LEVEL=normal

EXPOSE 8035

CMD ["tail", "-f", "/dev/null"]
