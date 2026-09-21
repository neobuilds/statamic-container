FROM composer:2@sha256:a5f59b9fd2faf31218632be4809dc6491761085e8064c31dc3b84378c48c248b AS composer
FROM php:8.4-apache-bookworm@sha256:0629e7852d88a0939841973910d94157de7cd68e48acefac44546f8534b45d31 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends libfreetype6-dev libjpeg62-turbo-dev libpng-dev libwebp-dev libzip-dev libicu-dev libonig-dev unzip gosu ca-certificates curl \
 && docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
 && docker-php-ext-install -j2 gd zip intl mbstring bcmath opcache pdo_mysql \
 && a2enmod rewrite headers setenvif && rm -rf /var/lib/apt/lists/*
COPY --from=composer /usr/bin/composer /usr/local/bin/composer
WORKDIR /var/www/html
RUN curl -fsSL https://github.com/statamic/statamic/archive/341050105099ead5f0c0db39f5f7d2e7f3239012.tar.gz -o /tmp/upstream.tar.gz \
 && echo "f7c903eb249deee87ba88a3bfffaa8fed108ecbe74eb24e5e458987b0b285820  /tmp/upstream.tar.gz" | sha256sum -c - \
 && tar xzf /tmp/upstream.tar.gz --strip-components=1 && rm /tmp/upstream.tar.gz
COPY composer.lock ./composer.lock
RUN COMPOSER_ALLOW_SUPERUSER=1 composer install --no-dev --prefer-dist --no-interaction --optimize-autoloader --no-progress \
 && composer check-platform-reqs --no-dev && rm /usr/local/bin/composer \
 && mkdir -p /opt/statamic-seed /data \
 && for path in content users resources config storage public/assets; do \
      mkdir -p "$path"; mkdir -p "/opt/statamic-seed/$(dirname "$path")"; \
      mv "$path" "/opt/statamic-seed/$path"; ln -s "/data/$path" "$path"; \
    done \
 && ln -s /data/storage/app/public public/storage \
 && chown root:root /var/www/html && chmod 755 /var/www/html \
 && chown -R www-data:www-data bootstrap/cache
COPY apache.conf /etc/apache2/sites-available/000-default.conf
COPY production.ini /usr/local/etc/php/conf.d/zz-production.ini
COPY entrypoint.sh /usr/local/bin/statamic-entrypoint
COPY bootstrap-admin.php /opt/statamic-bootstrap-admin.php
RUN chmod 755 /usr/local/bin/statamic-entrypoint
ENV APP_ENV=production APP_DEBUG=false LOG_CHANNEL=stderr SESSION_DRIVER=file CACHE_STORE=file QUEUE_CONNECTION=sync STATAMIC_PRO_ENABLED=false
ARG PACKAGING_VERSION=6.33.0-xcloud.3
LABEL org.opencontainers.image.source="https://github.com/neobuilds/statamic-container" \
 org.opencontainers.image.version="${PACKAGING_VERSION}" \
 org.opencontainers.image.description="Unmodified Statamic CMS with Core defaults; xCloud deployment packaging"
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=45s CMD curl -fsS http://127.0.0.1/up >/dev/null || exit 1
ENTRYPOINT ["statamic-entrypoint"]
CMD ["apache2-foreground"]
