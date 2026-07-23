FROM php:8.2-apache

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libzip-dev \
    libpng-dev \
    libjpeg62-turbo-dev \
    libfreetype6-dev \
    libwebp-dev \
    libicu-dev \
    libxml2-dev \
    libcurl4-openssl-dev \
    libonig-dev \
    libmagickwand-dev \
    libmemcached-dev \
    libgmp-dev \
    libbz2-dev \
    libldap2-dev \
    unzip \
    git \
    curl \
    vim \
    sudo \
    postgresql-client \
    cron \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

RUN docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j$(nproc) \
    pdo \
    pdo_pgsql \
    pgsql \
    gd \
    zip \
    intl \
    mbstring \
    xml \
    curl \
    opcache \
    bcmath \
    gmp \
    bz2 \
    ldap \
    exif \
    pcntl \
    sockets

RUN pecl install apcu redis imagick memcached \
    && docker-php-ext-enable apcu redis imagick memcached

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN a2enmod rewrite headers env dir mime setenvif ssl

COPY 000-default.conf /etc/apache2/sites-available/000-default.conf

RUN echo "ServerName localhost" >> /etc/apache2/apache2.conf

RUN sed -i 's/Listen 80/Listen 8033/' /etc/apache2/ports.conf

RUN { \
    echo 'opcache.enable=1'; \
    echo 'opcache.memory_consumption=256'; \
    echo 'opcache.max_accelerated_files=20000'; \
    echo 'opcache.revalidate_freq=0'; \
    echo 'memory_limit=512M'; \
    echo 'upload_max_filesize=16G'; \
    echo 'post_max_size=16G'; \
    echo 'max_execution_time=3600'; \
    echo 'max_input_time=3600'; \
    echo 'output_buffering=0'; \
    } > /usr/local/etc/php/conf.d/cloudcollab.ini

WORKDIR /app

RUN chown -R www-data:www-data /app

EXPOSE 8033

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:8033/status.php || exit 1

CMD ["apache2-foreground"]
