# ── Backend: PHP-FPM + Nginx ──────────────────────────────────────────────────
# Serves the Slim Framework PHP API behind Nginx on port 80.
# Env vars (POSTGRES_CONNECTION_STRING, AZURE_EMAIL_CONNECTION_STRING, etc.)
# are written to /var/www/.env at container startup so phpdotenv can load them.

FROM composer:2 AS deps
WORKDIR /app
COPY backend/composer*.json ./
RUN composer install --no-dev --no-interaction --optimize-autoloader
COPY backend/ ./

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM php:8.3-fpm-alpine

RUN apk add --no-cache \
        libpq-dev \
        nginx \
        supervisor \
    && docker-php-ext-install pdo pdo_pgsql \
    && rm -rf /var/cache/apk/*

COPY --from=deps /app /var/www/backend

COPY docker/backend/nginx.conf   /etc/nginx/http.d/default.conf
COPY docker/backend/supervisord.conf /etc/supervisord.conf
COPY docker/backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Ensure Nginx pid directory and log dirs exist
RUN mkdir -p /run/nginx /var/log/nginx

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
