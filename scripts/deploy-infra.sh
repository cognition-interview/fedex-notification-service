#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy-infra.sh — Deploy Azure infrastructure via ARM template
#
# Deploys the ARM template at infra/azuredeploy.json to the 'fedex' resource
# group. Creates: ACR, AKS cluster, Communication Services, and ACR pull
# role assignment.
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Contributor role on the 'fedex' resource group
#
# Usage:
#   ./scripts/deploy-infra.sh [--what-if]
#
# Options:
#   --what-if   Preview changes without deploying (dry run)
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

# ── Deploy or what-if ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--what-if" ]]; then
  echo "▶ Running what-if preview (no changes will be made)..."
  az deployment group what-if \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${TEMPLATE_FILE}" \
    --parameters "@${PARAMETERS_FILE}"
else
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
