# AKS Migration Guide

> **Migration story:** VM (single box, Nginx + PHP-FPM) → Containers (separate frontend/backend images) → Kubernetes (AKS)

---

## Architecture Overview

```
                              ┌────────────────────────────────┐
                              │        Azure Load Balancer     │
                              │        (public IP)             │
                              └──────────────┬─────────────────┘
                                             │
                              ┌──────────────▼─────────────────┐
                              │    NGINX Ingress Controller    │
                              │    (ingress-nginx namespace)   │
                              └──────┬───────────────┬─────────┘
                                     │               │
                          path: /api │               │ path: /
                                     │               │
                       ┌─────────────▼──┐    ┌───────▼──────────┐
                       │  backend (svc) │    │  frontend (svc)  │
                       │  ClusterIP:80  │    │  ClusterIP:80    │
                       └───────┬────────┘    └────────┬─────────┘
                               │                      │
                   ┌───────────▼───────────┐  ┌───────▼───────────┐
                   │  backend deployment   │  │ frontend deployment│
                   │  (2 replicas)         │  │ (2 replicas)       │
                   │  PHP-FPM + Nginx      │  │ Nginx + Angular    │
                   └───────────┬───────────┘  └───────────────────┘
                               │
                   ┌───────────▼───────────┐
                   │   PostgreSQL (cloud)   │
                   │   Azure Email (HTTPS)  │
                   └───────────────────────┘
```

### Request Flow

1. User's browser hits the **public Ingress IP** (Azure Load Balancer)
2. **NGINX Ingress Controller** inspects the path:
   - `/api/*` → routed to `backend` ClusterIP service → PHP-FPM container
   - `/*` (everything else) → routed to `frontend` ClusterIP service → Nginx serving Angular SPA
3. Angular app makes API calls to `/api/...` (relative URLs in production build) which the Ingress routes to the backend
4. Backend connects to **cloud-hosted PostgreSQL** and **Azure Communication Services** using env vars from Kubernetes Secrets

### Key Differences from VM Setup

| Aspect | VM (Before) | AKS (After) |
|--------|-------------|-------------|
| Frontend serving | Nginx on VM | Dedicated Nginx container |
| Backend serving | PHP-FPM on VM | Dedicated PHP-FPM + Nginx container |
| Routing | Single Nginx config | Kubernetes Ingress rules |
| Scaling | Vertical (bigger VM) | Horizontal (more pods) |
| Service discovery | localhost/hardcoded | Kubernetes DNS (ClusterIP) |
| Secrets | `.env` file on disk | Kubernetes Secrets |
| Deployment | SSH + git pull | Container image push + kubectl |
| Health checks | None | Liveness + readiness probes |

---

## Directory Structure

```
├── docker/
│   ├── backend/
│   │   ├── Dockerfile          # PHP-FPM + Nginx (multi-stage)
│   │   ├── nginx.conf          # Nginx config for PHP-FPM proxying
│   │   ├── supervisord.conf    # Runs Nginx + PHP-FPM together
│   │   └── entrypoint.sh       # Writes env vars to .env for phpdotenv
│   └── frontend/
│       ├── Dockerfile          # Angular build + Nginx serve (multi-stage)
│       └── nginx.conf          # Nginx config for SPA routing
├── k8s/
│   ├── namespace.yaml          # 'fedex' namespace
│   ├── backend-deployment.yaml # Backend pods (2 replicas)
│   ├── backend-service.yaml    # ClusterIP service for backend
│   ├── frontend-deployment.yaml# Frontend pods (2 replicas)
│   ├── frontend-service.yaml   # ClusterIP service for frontend
│   ├── ingress.yaml            # NGINX Ingress routing rules
│   └── secrets.yaml.example    # Template for Kubernetes secrets
├── scripts/
│   ├── provision-aks.sh        # One-time AKS + ACR + Ingress setup
│   └── deploy.sh               # Build, push, deploy images
└── .github/workflows/
    └── deploy-aks.yml          # CI/CD: test → build → deploy
```

---

## Step-by-Step Setup

### Prerequisites

- Azure CLI (`az`) — [Install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- kubectl — [Install](https://kubernetes.io/docs/tasks/tools/)
- Helm 3 — [Install](https://helm.sh/docs/intro/install/)
- Docker — [Install](https://docs.docker.com/get-docker/)

### 1. Authenticate with Azure

```bash
az login --service-principal \
  -u "$AZURE_APP_ID" \
  -p "$AZURE_PASSWORD" \
  --tenant "$AZURE_TENANT_ID"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
```

### 2. Provision Infrastructure (One-Time)

```bash
# Set configuration (optional — defaults are sensible)
export AZURE_RESOURCE_GROUP="fedex"
export AZURE_LOCATION="eastus"
export AKS_CLUSTER_NAME="fedex-aks"

# Run provisioning
chmod +x scripts/provision-aks.sh
./scripts/provision-aks.sh
```

This creates:
- Resource group
- Azure Container Registry (ACR)
- AKS cluster (2 nodes, Standard_B2s)
- NGINX Ingress Controller (via Helm)
- `fedex` Kubernetes namespace

### 3. Create Kubernetes Secrets

```bash
kubectl create secret generic backend-secrets \
  --namespace fedex \
  --from-literal=POSTGRES_CONNECTION_STRING='postgresql://user:pass@host:5432/db' \
  --from-literal=AZURE_EMAIL_CONNECTION_STRING='endpoint=https://...;accesskey=...' \
  --from-literal=AZURE_EMAIL_FROM_ADDRESS='DoNotReply@your-domain.azurecomm.net'
```

### 4. Build & Deploy

```bash
chmod +x scripts/deploy.sh
ACR_NAME=your-acr-name ./scripts/deploy.sh
```

Or deploy a specific tag:

```bash
ACR_NAME=your-acr-name ./scripts/deploy.sh v1.0.0
```

### 5. Verify Deployment

```bash
# Get the public IP
INGRESS_IP=$(kubectl get ingress fedex-ingress -n fedex \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "App available at: http://${INGRESS_IP}"

# Check pods are healthy
kubectl get pods -n fedex

# View logs
kubectl logs -n fedex -l app=backend --tail=50
kubectl logs -n fedex -l app=frontend --tail=50
```

---

## Demo: curl Examples

Once deployed, use the Ingress public IP to interact with the application:

```bash
# Set the ingress IP
INGRESS_IP=$(kubectl get ingress fedex-ingress -n fedex \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# ── Frontend ─────────────────────────────────────────────────────────────────
# Fetch the Angular SPA (should return HTML)
curl -s "http://${INGRESS_IP}/" | head -20

# ── Backend API ──────────────────────────────────────────────────────────────
# List businesses (paginated)
curl -s "http://${INGRESS_IP}/api/businesses?limit=3" | jq .

# Get order statistics
curl -s "http://${INGRESS_IP}/api/orders/stats" | jq .

# List orders with filters
curl -s "http://${INGRESS_IP}/api/orders?limit=5&status=In%20Transit" | jq .

# Get delivery insights
curl -s "http://${INGRESS_IP}/api/insights" | jq .

# List unread notifications
curl -s "http://${INGRESS_IP}/api/notifications?read=false&limit=5" | jq .
```

---

## CI/CD Pipeline

The `.github/workflows/deploy-aks.yml` workflow runs on every push to `main`:

```
push to main
    │
    ▼
┌─────────┐     ┌───────────────┐     ┌────────────┐
│  test   │ ──► │ build & push  │ ──► │ deploy to  │
│ PHPUnit │     │ to ACR        │     │ AKS        │
│ Vitest  │     │               │     │            │
└─────────┘     └───────────────┘     └────────────┘
```

### Required GitHub Secrets & Variables

| Type | Name | Description |
|------|------|-------------|
| Secret | `AZURE_APP_ID` | Service principal app ID |
| Secret | `AZURE_PASSWORD` | Service principal password |
| Secret | `AZURE_TENANT_ID` | Azure AD tenant ID |
| Variable | `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| Variable | `AZURE_RESOURCE_GROUP` | Resource group name |
| Variable | `AKS_CLUSTER_NAME` | AKS cluster name |
| Variable | `ACR_NAME` | ACR registry name |

---

## Observability

### Logs

```bash
# Backend logs (PHP-FPM + Nginx)
kubectl logs -n fedex -l app=backend -f

# Frontend logs (Nginx access/error)
kubectl logs -n fedex -l app=frontend -f

# Specific pod logs
kubectl logs -n fedex <pod-name> --tail=100
```

### Health Checks

- **Backend readiness:** `GET /api/businesses?limit=1` (validates DB connectivity)
- **Backend liveness:** TCP check on port 80
- **Frontend liveness/readiness:** `GET /` on port 80

### Debugging

```bash
# Describe a pod for events/errors
kubectl describe pod -n fedex <pod-name>

# Exec into a backend pod
kubectl exec -it -n fedex deployment/backend -- sh

# Check Ingress Controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx -f
```

---

## Scaling

```bash
# Scale backend to 4 replicas
kubectl scale deployment backend -n fedex --replicas=4

# Scale frontend to 3 replicas
kubectl scale deployment frontend -n fedex --replicas=3

# Enable Horizontal Pod Autoscaler (example)
kubectl autoscale deployment backend -n fedex \
  --min=2 --max=10 --cpu-percent=70
```

---

## Rollback

```bash
# View rollout history
kubectl rollout history deployment/backend -n fedex

# Roll back to previous version
kubectl rollout undo deployment/backend -n fedex

# Roll back to a specific revision
kubectl rollout undo deployment/backend -n fedex --to-revision=2
```
