#!/bin/sh
set -eu
umask 027
: "${APP_KEY:?APP_KEY is required}"
: "${APP_URL:?APP_URL is required}"
for path in content users resources config storage public/assets; do
    if [ ! -e "/data/$path" ]; then
        mkdir -p "/data/$(dirname "$path")"
        stage="/data/$(dirname "$path")/.seed-$(basename "$path")"
        rm -rf "$stage"
        cp -a "/opt/statamic-seed/$path" "$stage"
        chown -R www-data:www-data "$stage"
        mv "$stage" "/data/$path"
    fi
done
mkdir -p /data/storage/framework/cache/data /data/storage/framework/sessions /data/storage/framework/views /data/storage/app/public
chown www-data:www-data /data /data/public /data/storage/framework/cache/data /data/storage/framework/sessions /data/storage/framework/views /data/storage/app/public
gosu www-data php /opt/statamic-bootstrap-admin.php
gosu www-data php artisan optimize:clear --no-interaction >/dev/null
exec docker-php-entrypoint "$@"
