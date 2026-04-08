#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy.sh — Build container images, push to ACR, deploy to AKS
#
# Prerequisites:
#   - Azure CLI logged in
#   - kubectl configured for the target AKS cluster
#   - ACR_NAME env var set (or pass as argument)
#
# Usage:
#   ACR_NAME=fedexacr1234 ./scripts/deploy.sh [TAG]
#
#   TAG defaults to the short git SHA.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Configuration ─────────────────────────────────────────────────────────────
ACR_NAME="${ACR_NAME:-fedexcr}"
TAG="${1:-$(git -C "${REPO_ROOT}" rev-parse --short HEAD)}"
NAMESPACE="fedex"

ACR_LOGIN_SERVER=$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)

BACKEND_IMAGE="${ACR_LOGIN_SERVER}/fedex-backend:${TAG}"
FRONTEND_IMAGE="${ACR_LOGIN_SERVER}/fedex-frontend:${TAG}"

echo "═══════════════════════════════════════════════════════════════════"
echo "  FedEx Notification Service — Build & Deploy"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  ACR       : ${ACR_LOGIN_SERVER}"
echo "  Tag       : ${TAG}"
echo "  Backend   : ${BACKEND_IMAGE}"
echo "  Frontend  : ${FRONTEND_IMAGE}"
echo ""

# ── 1. Log in to ACR ─────────────────────────────────────────────────────────
echo "▶ Logging in to ACR..."
az acr login --name "${ACR_NAME}"

# ── 2. Build images ──────────────────────────────────────────────────────────
echo "▶ Building backend image..."
docker build \
  -t "${BACKEND_IMAGE}" \
  -f docker/backend/Dockerfile \
  "${REPO_ROOT}"

echo "▶ Building frontend image..."
docker build \
  -t "${FRONTEND_IMAGE}" \
  -f docker/frontend/Dockerfile \
  "${REPO_ROOT}"

# ── 3. Push images ───────────────────────────────────────────────────────────
echo "▶ Pushing backend image..."
docker push "${BACKEND_IMAGE}"

echo "▶ Pushing frontend image..."
docker push "${FRONTEND_IMAGE}"

# ── 4. Deploy to Kubernetes ──────────────────────────────────────────────────
echo "▶ Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml

# Set the real image on the deployment manifests using kustomize-style patching
kubectl apply -f k8s/backend-service.yaml
kubectl apply -f k8s/frontend-service.yaml
kubectl apply -f k8s/ingress.yaml

# Deploy backend with the actual image
sed "s|image: IMAGE_PLACEHOLDER|image: ${BACKEND_IMAGE}|" k8s/backend-deployment.yaml \
  | kubectl apply -f -

# Deploy frontend with the actual image
sed "s|image: IMAGE_PLACEHOLDER|image: ${FRONTEND_IMAGE}|" k8s/frontend-deployment.yaml \
  | kubectl apply -f -

# ── 5. Wait for rollout ─────────────────────────────────────────────────────
echo "▶ Waiting for backend rollout..."
kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=120s

echo "▶ Waiting for frontend rollout..."
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=120s

# ── 6. Show status ───────────────────────────────────────────────────────────
INGRESS_IP=$(kubectl get ingress fedex-ingress -n "${NAMESPACE}" \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "<pending>")

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  Backend  : ${BACKEND_IMAGE}"
echo "  Frontend : ${FRONTEND_IMAGE}"
echo "  Ingress  : http://${INGRESS_IP}"
echo ""
echo "  Verify:"
echo "    curl http://${INGRESS_IP}/api/businesses?limit=2"
echo "    curl http://${INGRESS_IP}/"
echo ""
kubectl get pods -n "${NAMESPACE}"
