#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy-infra.sh — Deploy Azure infrastructure via split ARM templates
#
# Each resource has its own template in infra/. The script checks which
# resources already exist and only deploys templates for missing ones.
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Contributor role on the 'fedex' resource group
#
# Usage:
#   ./scripts/deploy-infra.sh [--what-if] [--force]
#
# Options:
#   --what-if   Preview changes without deploying (dry run)
#   --force     Deploy all templates even if resources already exist
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RESOURCE_GROUP="fedex"
PARAMETERS_FILE="${REPO_ROOT}/infra/azuredeploy.parameters.json"

echo "═══════════════════════════════════════════════════════════════════"
echo "  FedEx Notification Service — ARM Template Deployment"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  Resource Group : ${RESOURCE_GROUP}"
echo "  Templates      : infra/acr.json, infra/aks.json, infra/communication.json, infra/function-app.json"
echo ""

# ── Read resource names from parameters ──────────────────────────────────────
ACR_NAME=$(jq -r '.parameters.acrName.value' "${PARAMETERS_FILE}")
AKS_NAME=$(jq -r '.parameters.aksClusterName.value' "${PARAMETERS_FILE}")
COMM_NAME=$(jq -r '.parameters.communicationServiceName.value' "${PARAMETERS_FILE}")
FUNC_NAME=$(jq -r '.parameters.functionAppName.value' "${PARAMETERS_FILE}")
FUNC_SA_NAME=$(jq -r '.parameters.functionStorageAccountName.value' "${PARAMETERS_FILE}")

# ── Validate all templates ───────────────────────────────────────────────────
echo "▶ Validating ARM templates..."
az deployment group validate \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${REPO_ROOT}/infra/acr.json" \
  --output none
az deployment group validate \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${REPO_ROOT}/infra/aks.json" \
  --parameters assignAcrPullRole=false \
  --output none
az deployment group validate \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${REPO_ROOT}/infra/communication.json" \
  --output none
az deployment group validate \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${REPO_ROOT}/infra/function-app.json" \
  --output none
echo "  All templates valid."
echo ""

# ── Check existing resources ─────────────────────────────────────────────────
resource_exists() {
  az resource show --resource-group "${RESOURCE_GROUP}" \
    --resource-type "$1" --name "$2" --output none 2>/dev/null
}

echo "▶ Checking which resources already exist..."
ACR_EXISTS=false
AKS_EXISTS=false
COMM_EXISTS=false
FUNC_EXISTS=false

if resource_exists "Microsoft.ContainerRegistry/registries" "${ACR_NAME}"; then
  echo "  ✓ ACR (${ACR_NAME}) exists"
  ACR_EXISTS=true
else
  echo "  ✗ ACR (${ACR_NAME}) missing"
fi

if resource_exists "Microsoft.ContainerService/managedClusters" "${AKS_NAME}"; then
  echo "  ✓ AKS (${AKS_NAME}) exists"
  AKS_EXISTS=true
else
  echo "  ✗ AKS (${AKS_NAME}) missing"
fi

if resource_exists "Microsoft.Communication/communicationServices" "${COMM_NAME}"; then
  echo "  ✓ Communication Services (${COMM_NAME}) exists"
  COMM_EXISTS=true
else
  echo "  ✗ Communication Services (${COMM_NAME}) missing"
fi

if resource_exists "Microsoft.Web/sites" "${FUNC_NAME}"; then
  echo "  ✓ Function App (${FUNC_NAME}) exists"
  FUNC_EXISTS=true
else
  echo "  ✗ Function App (${FUNC_NAME}) missing"
fi
echo ""

# ── Deploy or what-if ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--what-if" ]]; then
  echo "▶ Running what-if preview (no changes will be made)..."
  echo ""
  echo "=== ACR ==="
  az deployment group what-if \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${REPO_ROOT}/infra/acr.json"
  echo ""
  echo "=== AKS ==="
  az deployment group what-if \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${REPO_ROOT}/infra/aks.json" \
    --parameters assignAcrPullRole=false
  echo ""
  echo "=== Communication Services ==="
  az deployment group what-if \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${REPO_ROOT}/infra/communication.json"
  echo ""
  echo "=== Function App ==="
  az deployment group what-if \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${REPO_ROOT}/infra/function-app.json"
else
  FORCE=false
  [[ "${1:-}" == "--force" ]] && FORCE=true

  DEPLOYED=0

  if [[ "${ACR_EXISTS}" == "false" ]] || [[ "${FORCE}" == "true" ]]; then
    echo "▶ Deploying ACR..."
    az deployment group create \
      --resource-group "${RESOURCE_GROUP}" \
      --name "fedex-acr-$(date +%Y%m%d-%H%M%S)" \
      --template-file "${REPO_ROOT}/infra/acr.json" \
      --output table
    echo ""
    DEPLOYED=$((DEPLOYED + 1))
  fi

  if [[ "${AKS_EXISTS}" == "false" ]] || [[ "${FORCE}" == "true" ]]; then
    echo "▶ Deploying AKS (this may take 10-15 minutes)..."
    az deployment group create \
      --resource-group "${RESOURCE_GROUP}" \
      --name "fedex-aks-$(date +%Y%m%d-%H%M%S)" \
      --template-file "${REPO_ROOT}/infra/aks.json" \
      --output table
    echo ""
    DEPLOYED=$((DEPLOYED + 1))
  fi

  if [[ "${COMM_EXISTS}" == "false" ]] || [[ "${FORCE}" == "true" ]]; then
    echo "▶ Deploying Communication Services..."
    az deployment group create \
      --resource-group "${RESOURCE_GROUP}" \
      --name "fedex-comm-$(date +%Y%m%d-%H%M%S)" \
      --template-file "${REPO_ROOT}/infra/communication.json" \
      --output table
    echo ""
    DEPLOYED=$((DEPLOYED + 1))
  fi

  if [[ "${FUNC_EXISTS}" == "false" ]] || [[ "${FORCE}" == "true" ]]; then
    echo "▶ Deploying Function App..."
    az deployment group create \
      --resource-group "${RESOURCE_GROUP}" \
      --name "fedex-funcapp-$(date +%Y%m%d-%H%M%S)" \
      --template-file "${REPO_ROOT}/infra/function-app.json" \
      --parameters \
        postgresConnectionString="${POSTGRES_CONNECTION_STRING}" \
        azureEmailConnectionString="${AZURE_EMAIL_CONNECTION_STRING}" \
        azureEmailFromAddress="${AZURE_EMAIL_FROM_ADDRESS}" \
      --output table
    echo ""
    DEPLOYED=$((DEPLOYED + 1))
  fi

  echo "═══════════════════════════════════════════════════════════════════"
  if [[ "${DEPLOYED}" -eq 0 ]]; then
    echo "  All resources already exist — nothing was deployed."
    echo "  Use --force to re-deploy, or --what-if to preview changes."
  else
    echo "  Deployed ${DEPLOYED} template(s) successfully!"
    echo ""
    echo "  Next steps:"
    echo "    1. Get AKS credentials:"
    echo "         az aks get-credentials --resource-group ${RESOURCE_GROUP} --name ${AKS_NAME}"
    echo ""
    echo "    2. Install NGINX Ingress Controller:"
    echo "         kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/cloud/deploy.yaml"
    echo ""
    echo "    3. Create K8s secrets:"
    echo "         kubectl create secret generic backend-secrets \\"
    echo "           --namespace fedex \\"
    echo "           --from-literal=POSTGRES_CONNECTION_STRING='...' \\"
    echo "           --from-literal=AZURE_EMAIL_CONNECTION_STRING='...' \\"
    echo "           --from-literal=AZURE_EMAIL_FROM_ADDRESS='...'"
    echo ""
    echo "    4. Build & deploy the app:"
    echo "         ./scripts/deploy.sh"
  fi
  echo "═══════════════════════════════════════════════════════════════════"
fi
