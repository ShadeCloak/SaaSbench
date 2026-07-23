FROM php:8.3-apache

ARG TIMEZONE="UTC"

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/*.sources 2>/dev/null; \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends \
        bash curl git unzip haveged \
        libicu-dev libldap2-dev libpng-dev libzip-dev \
        libxslt1-dev libfreetype6-dev default-mysql-client \
    && docker-php-ext-configure gd --with-freetype \
    && docker-php-ext-install -j$(nproc) gd intl ldap pdo_mysql zip xsl opcache \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/${TIMEZONE} /etc/localtime \
    && echo ${TIMEZONE} > /etc/timezone

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

RUN a2enmod rewrite

COPY 000-default.conf /etc/apache2/sites-available/000-default.conf

RUN mkdir -p /app/public \
    && echo '<?php echo "Environment ready.";' > /app/public/index.php \
    && chown -R www-data:www-data /app

RUN mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini" \
    && echo "memory_limit = 512M" >> "$PHP_INI_DIR/conf.d/custom.ini" \
    && echo "max_execution_time = 120" >> "$PHP_INI_DIR/conf.d/custom.ini" \
    && echo "date.timezone = ${TIMEZONE}" >> "$PHP_INI_DIR/conf.d/custom.ini"

ENV COMPOSER_HOME=/composer
RUN mkdir -p /composer && chown -R www-data:www-data /composer

WORKDIR /app
EXPOSE 80
