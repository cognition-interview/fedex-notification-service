#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# provision-aks.sh — One-time setup for AKS + ACR + NGINX Ingress Controller
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - kubectl installed
#   - Helm 3 installed
#
# Usage:
#   export AZURE_SUBSCRIPTION_ID="your-sub-id"   # optional if already set
#   ./scripts/provision-aks.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration (override with env vars) ────────────────────────────────────
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-fedex-aks-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"
AKS_CLUSTER="${AKS_CLUSTER_NAME:-fedex-aks}"
ACR_NAME="${ACR_NAME:-fedexacr$(openssl rand -hex 4)}"
NODE_COUNT="${AKS_NODE_COUNT:-2}"
NODE_VM_SIZE="${AKS_NODE_VM_SIZE:-Standard_B2s}"
K8S_VERSION="${AKS_K8S_VERSION:-1.30}"

echo "═══════════════════════════════════════════════════════════════════"
echo "  FedEx Notification Service — AKS Provisioning"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  Resource Group : ${RESOURCE_GROUP}"
echo "  Location       : ${LOCATION}"
echo "  AKS Cluster    : ${AKS_CLUSTER}"
echo "  ACR Registry   : ${ACR_NAME}"
echo "  Node Count     : ${NODE_COUNT}"
echo "  Node VM Size   : ${NODE_VM_SIZE}"
echo ""

# ── 1. Resource Group ─────────────────────────────────────────────────────────
echo "▶ Creating resource group..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

# ── 2. Azure Container Registry ──────────────────────────────────────────────
echo "▶ Creating Azure Container Registry..."
az acr create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --sku Basic \
  --output none

ACR_LOGIN_SERVER=$(az acr show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --query loginServer \
  --output tsv)

echo "  ACR login server: ${ACR_LOGIN_SERVER}"

# ── 3. AKS Cluster ───────────────────────────────────────────────────────────
echo "▶ Creating AKS cluster (this may take 5-10 minutes)..."
az aks create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${AKS_CLUSTER}" \
  --node-count "${NODE_COUNT}" \
  --node-vm-size "${NODE_VM_SIZE}" \
  --kubernetes-version "${K8S_VERSION}" \
  --attach-acr "${ACR_NAME}" \
  --generate-ssh-keys \
  --enable-managed-identity \
  --network-plugin azure \
  --output none

# ── 4. Get AKS credentials ───────────────────────────────────────────────────
echo "▶ Fetching kubeconfig..."
az aks get-credentials \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${AKS_CLUSTER}" \
  --overwrite-existing

# ── 5. Install NGINX Ingress Controller ──────────────────────────────────────
echo "▶ Installing NGINX Ingress Controller via Helm..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update

helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.replicaCount=2 \
  --set controller.service.externalTrafficPolicy=Local \
  --wait

# ── 6. Create Kubernetes namespace ───────────────────────────────────────────
echo "▶ Applying namespace..."
kubectl apply -f k8s/namespace.yaml

# ── 7. Wait for Ingress external IP ─────────────────────────────────────────
echo "▶ Waiting for Ingress Controller external IP..."
EXTERNAL_IP=""
for i in $(seq 1 30); do
  EXTERNAL_IP=$(kubectl get svc ingress-nginx-controller \
    -n ingress-nginx \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
  if [ -n "${EXTERNAL_IP}" ]; then
    break
  fi
  echo "  Waiting... (attempt ${i}/30)"
  sleep 10
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Provisioning complete!"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  AKS Cluster     : ${AKS_CLUSTER}"
echo "  ACR Login Server : ${ACR_LOGIN_SERVER}"
echo "  Ingress IP       : ${EXTERNAL_IP:-<pending — check with: kubectl get svc -n ingress-nginx>}"
echo ""
echo "  Next steps:"
echo "    1. Create secrets:  kubectl create secret generic backend-secrets \\"
echo "         --namespace fedex \\"
echo "         --from-literal=POSTGRES_CONNECTION_STRING='...' \\"
echo "         --from-literal=AZURE_EMAIL_CONNECTION_STRING='...' \\"
echo "         --from-literal=AZURE_EMAIL_FROM_ADDRESS='...'"
echo ""
echo "    2. Build & deploy:  ACR_NAME=${ACR_NAME} ./scripts/deploy.sh"
echo ""
