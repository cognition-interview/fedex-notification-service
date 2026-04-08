# ── Frontend: Angular build + Nginx serve ─────────────────────────────────────
# Multi-stage build: compile Angular in Node, serve static files via Nginx.
# Production environment uses relative URLs (apiUrl: '') so the Ingress
# controller handles routing /api requests to the backend service.

# Stage 1 — Build
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2 — Serve
FROM nginx:1.27-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
