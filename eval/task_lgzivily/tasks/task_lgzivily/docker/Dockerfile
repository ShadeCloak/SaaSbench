# syntax=docker/dockerfile:1.7
#
# Application image for task_lgzivily — Clinical Practice Management Suite.
#
# Provides a clean working environment:
#   - PHP 8.2 + Apache 2.4 with mod_rewrite + mod_headers
#   - All 32 PHP extensions required by §2.2 of task.md
#   - Composer 2.x
#   - Node.js 24.x + npm + gulp-cli (for the frontend build pipeline)
#   - wkhtmltopdf (consumed via knplabs/knp-snappy)
#   - git
#
# IMPORTANT: this image deliberately ships with NO application code.
# The agent's workspace is mounted into /var/www/html at run time.
FROM php:8.2-apache-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PHP_INI_DIR=/usr/local/etc/php \
    COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_NO_INTERACTION=1 \
    COMPOSER_HOME=/root/.composer \
    APP_PORT=80

# ---------------------------------------------------------------------------
# 1. System packages + headers needed to compile PHP extensions
# ---------------------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash ca-certificates curl wget git unzip xz-utils gnupg \
        tini netcat-openbsd procps sudo lsof \
        wkhtmltopdf \
        # MariaDB / MySQL client (used by smoke tests + docker exec)
        default-mysql-client \
        # libs to build PHP extensions
        libldap2-dev libxml2-dev libxslt1-dev libzip-dev libonig-dev \
        libpng-dev libjpeg-dev libwebp-dev libfreetype6-dev libgd-dev \
        libicu-dev libsodium-dev libssl-dev libcurl4-openssl-dev \
        libxslt-dev libxmlrpc-epi-dev libtidy-dev libmagickwand-dev \
        libsqlite3-dev libreadline-dev \
        # for ext-imagick (still PECL on PHP 8.2)
        imagemagick ghostscript; \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2. PHP extensions (the 33 ext-* required in §2.2 of task.md)
# ---------------------------------------------------------------------------
# Some are bundled by docker-php-source (ctype/dom/filter/json/libxml/mbstring/openssl/
# pdo/phar/session/simplexml/sodium/tokenizer/xml/xmlreader/xmlwriter — built-in by default).
# Compile what's left.

RUN set -eux; \
    docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp; \
    docker-php-ext-configure ldap; \
    docker-php-ext-install -j"$(nproc)" \
        bcmath calendar curl exif fileinfo gd iconv intl ldap mysqli \
        opcache pdo_mysql soap sockets xsl zip; \
    # PECL extensions
    pecl install imagick; \
    docker-php-ext-enable imagick

# ---------------------------------------------------------------------------
# 3. Apache modules and base config
# ---------------------------------------------------------------------------
RUN set -eux; \
    a2enmod rewrite headers expires deflate ssl; \
    # we will replace 000-default.conf with our own (mounted from docker-entrypoint)
    rm -f /etc/apache2/sites-enabled/000-default.conf

COPY 000-default.conf /etc/apache2/sites-available/000-default.conf
RUN ln -sf /etc/apache2/sites-available/000-default.conf /etc/apache2/sites-enabled/000-default.conf

# Drop a sane php.ini for production-ish defaults; raise upload limits because
# clinical documents (CCDA, PDF, DICOM previews) routinely exceed 8 MB.
RUN { \
        echo "memory_limit = 512M"; \
        echo "max_execution_time = 120"; \
        echo "post_max_size = 128M"; \
        echo "upload_max_filesize = 128M"; \
        echo "max_input_vars = 5000"; \
        echo "date.timezone = UTC"; \
        echo "expose_php = Off"; \
        echo "session.cookie_httponly = 1"; \
        echo "session.cookie_secure = 0"; \
        echo "session.cookie_samesite = Lax"; \
    } > /usr/local/etc/php/conf.d/zz-app.ini

# ---------------------------------------------------------------------------
# 4. Composer 2.x (vendor by application code; image only ships the binary)
# ---------------------------------------------------------------------------
COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer

# ---------------------------------------------------------------------------
# 5. Node.js 24.x + npm + gulp-cli (frontend build pipeline)
# ---------------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL https://nodejs.org/dist/v24.0.0/node-v24.0.0-linux-x64.tar.xz \
         -o /tmp/node.tar.xz; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1; \
    rm /tmp/node.tar.xz; \
    npm install -g npm@latest gulp-cli@^4

# ---------------------------------------------------------------------------
# 6. Workspace + filesystem layout
# ---------------------------------------------------------------------------
# Apache's DocumentRoot in the official image is /var/www/html.
# We will mount the agent's workspace there.
WORKDIR /var/www/html
RUN set -eux; \
    chown -R www-data:www-data /var/www/html /var/log/apache2; \
    mkdir -p /var/www/html/sites/default/documents/oauth2; \
    chown -R www-data:www-data /var/www/html/sites

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=10 \
    CMD curl -fsS -o /dev/null -w "%{http_code}" "http://127.0.0.1/" \
        | grep -E "^(200|301|302|401|403|404)$" \
        || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/apache2-foreground"]
