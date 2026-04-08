#!/usr/bin/env bash
# deploy-synapse-migration.sh
# Deploys the Synapse data migration pipeline:
#   1. Creates the Synapse schema (DDL) in the dedicated SQL pool
#   2. Deploys linked service, datasets, and pipeline via az synapse CLI
#   3. Optionally runs the pipeline
#
# Prerequisites:
#   - az login (service principal with Synapse Administrator RBAC)
#   - POSTGRES_CONNECTION_STRING environment variable
#   - pyodbc + ODBC Driver 18 for SQL Server (for DDL execution)
#
# Usage:
#   ./scripts/deploy-synapse-migration.sh            # Deploy artifacts only
#   ./scripts/deploy-synapse-migration.sh --run       # Deploy and run pipeline
#   ./scripts/deploy-synapse-migration.sh --run --wait # Deploy, run, and wait for completion

set -euo pipefail

WORKSPACE="fedexsynapseus"
RESOURCE_GROUP="fedex"
SQL_POOL="fedexpool"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNAPSE_DIR="$REPO_ROOT/migrations/synapse"

RUN_PIPELINE=false
WAIT_FOR_COMPLETION=false

for arg in "$@"; do
  case "$arg" in
    --run)  RUN_PIPELINE=true ;;
    --wait) WAIT_FOR_COMPLETION=true ;;
  esac
done

echo "==> Parsing POSTGRES_CONNECTION_STRING..."
if [ -z "${POSTGRES_CONNECTION_STRING:-}" ]; then
  echo "ERROR: POSTGRES_CONNECTION_STRING is not set." >&2
  exit 1
fi

PG_HOST=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).hostname)" "$POSTGRES_CONNECTION_STRING")
PG_PORT=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).port or 5432)" "$POSTGRES_CONNECTION_STRING")
PG_DB=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).path.lstrip('/'))" "$POSTGRES_CONNECTION_STRING")
PG_USER=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).username)" "$POSTGRES_CONNECTION_STRING")
PG_PASS=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlparse(sys.argv[1]).password)" "$POSTGRES_CONNECTION_STRING")

echo "   Host: $PG_HOST | Port: $PG_PORT | DB: $PG_DB | User: $PG_USER"

# --- Step 1: Create Synapse schema via pyodbc with AAD token auth ---
echo ""
echo "==> Step 1: Creating Synapse schema in $SQL_POOL..."

python3 - "$SYNAPSE_DIR/001_create_synapse_schema.sql" <<'PYEOF'
import sys, struct, subprocess, pyodbc

ddl_file = sys.argv[1]

# Get AAD access token for Azure SQL
result = subprocess.run(
    ["az", "account", "get-access-token",
     "--resource", "https://database.windows.net/",
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, check=True
)
token = result.stdout.strip()
token_bytes = token.encode("UTF-16-LE")
token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=fedexsynapseus.sql.azuresynapse.net;"
    "DATABASE=fedexpool;",
    attrs_before={1256: token_struct},
    autocommit=True
)
cursor = conn.cursor()

with open(ddl_file, "r") as f:
    ddl = f.read()

# Execute each statement separately (split on semicolons)
for stmt in ddl.split(";"):
    # Strip comment-only lines, keep actual SQL
    lines = [l for l in stmt.strip().splitlines() if not l.strip().startswith("--")]
    sql = "\n".join(lines).strip()
    if sql:
        try:
            cursor.execute(stmt.strip())
            print(f"   OK: {sql[:80]}...")
        except Exception as e:
            print(f"   ERROR: {e}")
            print(f"   Statement: {sql[:120]}")
            raise

conn.close()
print("   Schema created successfully.")
PYEOF

# --- Step 2: Generate and deploy linked service ---
echo ""
echo "==> Step 2: Deploying PostgresSource linked service..."

LINKED_SERVICE_FILE=$(mktemp /tmp/PostgresSource.XXXXXX.json)
sed -e "s|__POSTGRES_HOST__|$PG_HOST|g" \
    -e "s|__POSTGRES_PORT__|$PG_PORT|g" \
    -e "s|__POSTGRES_DB__|$PG_DB|g" \
    -e "s|__POSTGRES_USER__|$PG_USER|g" \
    -e "s|__POSTGRES_PASSWORD__|$PG_PASS|g" \
    "$SYNAPSE_DIR/linked-services/PostgresSource.template.json" > "$LINKED_SERVICE_FILE"

az synapse linked-service create \
  --workspace-name "$WORKSPACE" \
  --name PostgresSource \
  --file @"$LINKED_SERVICE_FILE" \
  --output none

rm -f "$LINKED_SERVICE_FILE"
echo "   Linked service deployed."

# --- Step 3: Deploy datasets ---
echo ""
echo "==> Step 3: Deploying datasets..."

for dataset_file in "$SYNAPSE_DIR"/datasets/*.json; do
  dataset_name=$(basename "$dataset_file" .json)
  echo "   Deploying dataset: $dataset_name"
  az synapse dataset create \
    --workspace-name "$WORKSPACE" \
    --name "$dataset_name" \
    --file @"$dataset_file" \
    --output none
done
echo "   All datasets deployed."

# --- Step 4: Deploy pipeline ---
echo ""
echo "==> Step 4: Deploying pipeline..."

az synapse pipeline create \
  --workspace-name "$WORKSPACE" \
  --name MigratePostgresToSynapse \
  --file @"$SYNAPSE_DIR/pipelines/MigratePostgresToSynapse.json" \
  --output none

echo "   Pipeline deployed."

# --- Step 5: Optionally run the pipeline ---
if [ "$RUN_PIPELINE" = true ]; then
  echo ""
  echo "==> Step 5: Running pipeline..."

  RUN_ID=$(az synapse pipeline create-run \
    --workspace-name "$WORKSPACE" \
    --name MigratePostgresToSynapse \
    --query runId -o tsv)

  echo "   Pipeline run started. Run ID: $RUN_ID"

  if [ "$WAIT_FOR_COMPLETION" = true ]; then
    echo "   Waiting for pipeline to complete..."
    while true; do
      STATUS=$(az synapse pipeline-run show \
        --workspace-name "$WORKSPACE" \
        --run-id "$RUN_ID" \
        --query status -o tsv 2>/dev/null || echo "InProgress")

      echo "   Status: $STATUS"

      if [ "$STATUS" = "Succeeded" ]; then
        echo "   Pipeline completed successfully!"
        break
      elif [ "$STATUS" = "Failed" ] || [ "$STATUS" = "Cancelled" ]; then
        echo "   Pipeline $STATUS!"
        az synapse pipeline-run show \
          --workspace-name "$WORKSPACE" \
          --run-id "$RUN_ID" \
          --output json
        exit 1
      fi

      sleep 15
    done
  fi
else
  echo ""
  echo "==> Skipping pipeline run (use --run to execute, --run --wait to execute and wait)."
fi

echo ""
echo "==> Migration deployment complete."
