# ── Frontend: Angular build + Nginx serve ─────────────────────────────────────
# Copies a pre-built Angular dist into Nginx for serving.
# Production environment uses relative URLs (apiUrl: '') so the Ingress
# controller handles routing /api requests to the backend service.
#
# The CI workflow runs `npm ci && npm run build` before `docker build`
# to avoid network timeouts inside the Docker build.

FROM nginx:1.27-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
