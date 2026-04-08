# Stage 1: Build Angular frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Install PHP dependencies
FROM composer:2 AS backend-build
WORKDIR /app/backend
COPY backend/composer*.json ./
RUN composer install --no-dev --no-interaction --optimize-autoloader
COPY backend/ ./

# Final stage: nginx + PHP-FPM + supervisord
FROM php:8.3-fpm-alpine

RUN apk add --no-cache \
        libpq-dev \
        nginx \
        supervisor \
    && docker-php-ext-install pdo pdo_pgsql

# PHP backend
COPY --from=backend-build /app/backend /var/www/backend

# Angular static files
COPY --from=frontend-build /app/frontend/dist/frontend/browser /var/www/html

# nginx config: serve Angular at /, proxy /api to PHP-FPM
RUN printf 'server {\n\
    listen 80;\n\
\n\
    root /var/www/html;\n\
    index index.html;\n\
\n\
    # Angular app — fallback to index.html for client-side routing\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
\n\
    # PHP backend via FastCGI\n\
    location /api {\n\
        root /var/www/backend/public;\n\
        fastcgi_pass 127.0.0.1:9000;\n\
        fastcgi_index index.php;\n\
        fastcgi_param SCRIPT_FILENAME /var/www/backend/public/index.php;\n\
        include fastcgi_params;\n\
    }\n\
}\n' > /etc/nginx/http.d/default.conf

# supervisord config: run nginx + php-fpm together
RUN printf '[supervisord]\n\
nodaemon=true\n\
logfile=/dev/stdout\n\
logfile_maxbytes=0\n\
\n\
[program:php-fpm]\n\
command=php-fpm -F\n\
autostart=true\n\
autorestart=true\n\
stdout_logfile=/dev/stdout\n\
stdout_logfile_maxbytes=0\n\
stderr_logfile=/dev/stderr\n\
stderr_logfile_maxbytes=0\n\
\n\
[program:nginx]\n\
command=nginx -g "daemon off;"\n\
autostart=true\n\
autorestart=true\n\
stdout_logfile=/dev/stdout\n\
stdout_logfile_maxbytes=0\n\
stderr_logfile=/dev/stderr\n\
stderr_logfile_maxbytes=0\n' > /etc/supervisord.conf

EXPOSE 80

CMD ["supervisord", "-c", "/etc/supervisord.conf"]
