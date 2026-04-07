FROM php:8.3-cli-alpine

RUN apk add --no-cache libpq-dev \
    && docker-php-ext-install pdo pdo_pgsql

COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

WORKDIR /app

EXPOSE 8000

CMD ["sh", "-c", "cd backend && composer install --no-interaction && php -S 0.0.0.0:8000 -t public"]
