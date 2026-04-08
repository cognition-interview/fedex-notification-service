#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy-infra.sh — Deploy Azure infrastructure via ARM template
#
# Deploys the ARM template at infra/azuredeploy.json to the 'fedex' resource
# group. Checks if resources already exist and skips deployment when everything
# is already provisioned.
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
#   --force     Deploy even if all resources already exist
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RESOURCE_GROUP="fedex"
TEMPLATE_FILE="${REPO_ROOT}/infra/azuredeploy.json"
PARAMETERS_FILE="${REPO_ROOT}/infra/azuredeploy.parameters.json"
DEPLOYMENT_NAME="fedex-infra-$(date +%Y%m%d-%H%M%S)"

echo "═══════════════════════════════════════════════════════════════════"
echo "  FedEx Notification Service — ARM Template Deployment"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "  Resource Group  : ${RESOURCE_GROUP}"
echo "  Template        : ${TEMPLATE_FILE}"
echo "  Parameters      : ${PARAMETERS_FILE}"
echo "  Deployment Name : ${DEPLOYMENT_NAME}"
echo ""

# ── Validate template ────────────────────────────────────────────────────────
echo "▶ Validating ARM template..."
az deployment group validate \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${TEMPLATE_FILE}" \
  --parameters "@${PARAMETERS_FILE}" \
  --output none

echo "  Template is valid."
echo ""

# ── Check existing resources ─────────────────────────────────────────────────
check_resource() {
  local TYPE="$1" NAME="$2" LABEL="$3"
  if az resource show --resource-group "${RESOURCE_GROUP}" \
       --resource-type "${TYPE}" --name "${NAME}" --output none 2>/dev/null; then
    echo "  ✓ ${LABEL} (${NAME}) exists"
    return 0
  else
    echo "  ✗ ${LABEL} (${NAME}) does NOT exist"
    return 1
  fi
}

check_all_resources() {
  local ACR_NAME AKS_NAME COMM_NAME FUNC_NAME STORAGE_NAME
  ACR_NAME=$(jq -r '.parameters.acrName.value' "${PARAMETERS_FILE}")
  AKS_NAME=$(jq -r '.parameters.aksClusterName.value' "${PARAMETERS_FILE}")
  COMM_NAME=$(jq -r '.parameters.communicationServiceName.value' "${PARAMETERS_FILE}")
  FUNC_NAME=$(jq -r '.parameters.functionAppName.value' "${PARAMETERS_FILE}")
  STORAGE_NAME=$(jq -r '.parameters.functionStorageAccountName.value' "${PARAMETERS_FILE}")

  echo "▶ Checking which resources already exist..."
  local MISSING=0
  check_resource "Microsoft.ContainerRegistry/registries" "${ACR_NAME}" "Container Registry" || MISSING=1
  check_resource "Microsoft.ContainerService/managedClusters" "${AKS_NAME}" "AKS Cluster" || MISSING=1
  check_resource "Microsoft.Communication/communicationServices" "${COMM_NAME}" "Communication Services" || MISSING=1
  check_resource "Microsoft.Storage/storageAccounts" "${STORAGE_NAME}" "Storage Account" || MISSING=1
  check_resource "Microsoft.Web/serverfarms" "${FUNC_NAME}-plan" "App Service Plan" || MISSING=1
  check_resource "Microsoft.Web/sites" "${FUNC_NAME}" "Function App" || MISSING=1
  echo ""

  return ${MISSING}
}

# ── Deploy or what-if ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--what-if" ]]; then
  echo "▶ Running what-if preview (no changes will be made)..."
  az deployment group what-if \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${TEMPLATE_FILE}" \
    --parameters "@${PARAMETERS_FILE}"
else
  FORCE=false
  if [[ "${1:-}" == "--force" ]]; then
    FORCE=true
  fi

  NEEDS_DEPLOY=true
  if check_all_resources; then
    if [[ "${FORCE}" == "true" ]]; then
      echo "  All resources exist but --force specified. Deploying anyway."
    else
      NEEDS_DEPLOY=false
      echo "═══════════════════════════════════════════════════════════════════"
      echo "  All resources already exist — skipping deployment."
      echo "  Use --force to re-deploy, or --what-if to preview changes."
      echo "═══════════════════════════════════════════════════════════════════"
    fi
  fi

  if [[ "${NEEDS_DEPLOY}" == "true" ]]; then
    echo "▶ Deploying ARM template (this may take 10-15 minutes)..."
    az deployment group create \
      --resource-group "${RESOURCE_GROUP}" \
      --name "${DEPLOYMENT_NAME}" \
      --template-file "${TEMPLATE_FILE}" \
      --parameters "@${PARAMETERS_FILE}" \
      --output table

    echo ""
    echo "▶ Fetching deployment outputs..."
    az deployment group show \
      --resource-group "${RESOURCE_GROUP}" \
      --name "${DEPLOYMENT_NAME}" \
      --query "properties.outputs" \
      --output table

    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  Infrastructure deployment complete!"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
    echo "  Next steps:"
    echo "    1. Get AKS credentials:"
    echo "         az aks get-credentials --resource-group ${RESOURCE_GROUP} --name fedex-k8-cluster"
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
    echo ""
  fi
fi
