# =============================================================================
# task_rjhcjrst (Personal Finance Manager / PFM)
# =============================================================================
# This Dockerfile is the local-build fallback. The actually-published image
# is shadetocloak/task_rjhcjrst-app:latest, which already contains:
#   - PHP 8.4 + extensions (bcmath/gd/gmp/intl/mbstring/opcache/pcntl/pdo_mysql/sodium/zip/exif)
#   - Composer 2 + system tools (git/curl/cron/mysql-client/...)
#   - Apache 2 (mod_rewrite, mod_headers; DocumentRoot=/var/www/html/public)
#   - /var/cache/workspace_deps/{vendor, public_build, helpers/, conf/}
#     (Composer vendor + Vite manifest stub + 6 helper PHP scripts + Apache vhost)
#
# At runtime, prepare_workspace.sh copies the frozen deps + helpers back into
# /var/www/html so the agent doesn't have to re-run `composer install` (which
# would otherwise take 5-10 minutes inside the container).
# =============================================================================

FROM php:8.4-apache-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    APP_ENV=local \
    APP_DEBUG=true \
    COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_NO_INTERACTION=1 \
    PHP_MEMORY_LIMIT=512M \
    PHP_UPLOAD_MAX_FILESIZE=64M \
    PHP_POST_MAX_SIZE=64M

# ---------- System dependencies ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl wget unzip ca-certificates cron \
        netcat-openbsd procps default-mysql-client \
        libicu-dev libxml2-dev libonig-dev libsodium-dev libzip-dev \
        libcurl4-openssl-dev libssl-dev zlib1g-dev \
        libpng-dev libjpeg-dev libfreetype6-dev libwebp-dev libgmp-dev \
    && rm -rf /var/lib/apt/lists/*

# ---------- PHP extensions (task.md §2.1 hard requirements) ----------
RUN docker-php-ext-configure intl \
    && docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j"$(nproc)" \
        bcmath gd gmp intl mbstring opcache pcntl pdo_mysql sockets sodium zip exif

RUN php -m | tee /tmp/php-modules.txt \
    && for ext in bcmath ctype curl dom fileinfo gd iconv intl json mbstring openssl pdo pdo_mysql session simplexml sodium tokenizer xml xmlwriter zip; do \
         if ! grep -qi "^${ext}$" /tmp/php-modules.txt; then echo "MISSING: ${ext}"; exit 1; fi; \
       done

# ---------- Composer 2 ----------
RUN curl -fsSL https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer \
    && composer --version

# ---------- Custom PHP config ----------
RUN { \
        echo "memory_limit=${PHP_MEMORY_LIMIT}"; \
        echo "upload_max_filesize=${PHP_UPLOAD_MAX_FILESIZE}"; \
        echo "post_max_size=${PHP_POST_MAX_SIZE}"; \
        echo "max_execution_time=120"; \
        echo "max_input_time=120"; \
        echo "date.timezone=${TZ}"; \
        echo "session.cookie_secure=0"; \
        echo "session.cookie_samesite=Lax"; \
        echo "expose_php=Off"; \
    } > /usr/local/etc/php/conf.d/zz-pfm.ini

# ---------- Apache: enable rewrite + redirect DocumentRoot to /public ----------
RUN a2enmod rewrite headers \
    && sed -i 's|/var/www/html|/var/www/html/public|g' /etc/apache2/sites-available/000-default.conf \
    && { \
        echo "<Directory /var/www/html/public>"; \
        echo "    Options Indexes FollowSymLinks"; \
        echo "    AllowOverride All"; \
        echo "    Require all granted"; \
        echo "</Directory>"; \
    } > /etc/apache2/conf-available/pfm.conf \
    && a2enconf pfm

# Copy the canonical Apache vhost (matches docker-compose mount)
COPY apache-pfm.conf /etc/apache2/sites-available/000-default.conf

WORKDIR /var/www/html
RUN mkdir -p /var/www/html \
    && chown -R www-data:www-data /var/www/html \
    && chmod -R 775 /var/www/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=20 \
    CMD curl -fsS -o /dev/null -w "%{http_code}" http://localhost/ \
        | grep -E "^(200|301|302|401|403|404|500|503)$" >/dev/null \
        || exit 1

CMD ["apache2-foreground"]
