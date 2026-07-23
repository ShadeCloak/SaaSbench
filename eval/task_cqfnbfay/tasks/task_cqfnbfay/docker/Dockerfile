# task_cqfnbfay baseline image source.
#
# This Dockerfile is intentionally retained as a build-recipe placeholder
# but is NOT exercised by the public docker-compose workflow:
#   - docker-compose.yml has the `build:` stanza commented out (v3 hardening)
#   - Public consumers pull the pre-built image from the container registry:
#       shadetocloak/task_cqfnbfay-app:baseline
#   - Rebuilding this image is a SaaSBench-maintainer-only operation;
#     the BASELINE_FROM default below points at the maintainer's
#     sanitized intermediate image. Override via build-arg if you need
#     to target a different upstream (see internal maintainer docs).
ARG BASELINE_FROM=shadetocloak/task_cqfnbfay-app:baseline-fromsource
FROM ${BASELINE_FROM}

ENV RAILS_ENV=production \
    BUNDLE_WITHOUT="development:test" \
    LANG=C.UTF-8

RUN apk add --no-cache \
    bash \
    postgresql-client \
    build-base \
    libpq-dev \
    yaml-dev \
    libffi-dev \
    openssl-dev \
    git \
    nodejs \
    npm \
    redis

RUN npm install -g yarn

RUN ruby -v && bundler -v && node -v && yarn -v && git --version

WORKDIR /app

EXPOSE 8021

CMD ["bash", "-c", "tail -f /dev/null"]
