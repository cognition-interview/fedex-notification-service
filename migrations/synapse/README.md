# PostgreSQL → Azure Synapse Analytics Migration

This directory contains scripts, SQL, and Synapse Pipeline JSON definitions to migrate data from the PostgreSQL database to an Azure Synapse Analytics dedicated SQL pool.

## Architecture (Recommended: Synapse Pipeline)

```
PostgreSQL (source)
    │
    │  Synapse Pipeline Copy Activity
    │  (az synapse pipeline create-run)
    ▼
Azure Synapse dedicated SQL pool (fedexpool)
```

The pipeline reads directly from PostgreSQL and writes to Synapse — no intermediate files needed. Type conversions (timestamps, booleans, enums) are handled inline in the source queries.

### Alternative: CSV-based migration

```
PostgreSQL → CSV export → Data Lake upload → COPY INTO Synapse
```

See `002_load_data.sql` and `scripts/export_postgres_for_synapse.sh` for this approach. The pipeline method above is preferred for all migrations.

## Azure Resources

| Resource | Name | Details |
|----------|------|---------|
| Synapse Workspace | `fedexsynapseus` | Central US |
| Dedicated SQL Pool | `fedexpool` | DW100c performance level |
| Storage Account | `fedexstorageus` | Data Lake Gen2, filesystem: `synapse` |
| SQL Admin Login | `sqladminuser` | — |
| SQL Endpoint | `fedexsynapseus.sql.azuresynapse.net` | — |

## Type Mappings

| PostgreSQL | Synapse (T-SQL) | Notes |
|-----------|-----------------|-------|
| `UUID` | `NVARCHAR(36)` | Stored as string |
| `TEXT` | `NVARCHAR(n)` | Sized per column usage |
| `TIMESTAMPTZ` | `DATETIME2` | Timezone stripped via `AT TIME ZONE 'UTC'` |
| `BOOLEAN` | `BIT` | Converted via `CASE WHEN col THEN 1 ELSE 0 END` |
| Custom ENUMs | `NVARCHAR(50)` | Cast to text via `::text` |
| `NUMERIC(8,2)` | `DECIMAL(8,2)` | Direct mapping |
| `DATE` | `DATE` | Direct mapping |

## Files

| File | Purpose |
|------|---------|
| `001_create_schema.sql` | Creates all four tables in Synapse |
| `002_load_data.sql` | COPY INTO statements (CSV-based alternative) |
| `pipeline/pipeline_pg_to_synapse.json` | Synapse Pipeline definition with Copy Activities |
| `pipeline/dataset_pg_source.json` | Source dataset (PostgreSQL) |
| `pipeline/dataset_synapse_*.json` | Sink datasets (one per table) |
| `scripts/export_postgres_for_synapse.sh` | CSV export script (alternative method) |
| `scripts/migrate_pg_to_synapse.py` | Direct Python migration script (alternative method) |

## How to Run (Pipeline Method — Recommended)

### Prerequisites

- `az` CLI with `az synapse` extension
- Service principal with **Synapse Administrator** RBAC role on the workspace
- PostgreSQL connection string

### 1. Create schema in Synapse

```bash
sqlcmd -S fedexsynapseus.sql.azuresynapse.net \
  -d fedexpool -U sqladminuser -P '<password>' \
  -C -I -i migrations/synapse/001_create_schema.sql
```

### 2. Create linked service for PostgreSQL

```bash
# Create a JSON file with your PG connection string:
cat > /tmp/pg_linked_service.json << EOF
{
  "properties": {
    "type": "AzurePostgreSql",
    "typeProperties": {
      "connectionString": "Server=<host>;Port=5432;Database=<db>;UID=<user>;Password=<pwd>;SslMode=Require"
    }
  }
}
EOF

az synapse linked-service create \
  --workspace-name fedexsynapseus \
  --name PostgreSqlSource \
  --file @/tmp/pg_linked_service.json
```

### 3. Deploy datasets

```bash
for f in migrations/synapse/pipeline/dataset_*.json; do
  NAME=$(basename "$f" .json | sed 's/dataset_//' | python3 -c "import sys; parts=sys.stdin.read().strip().split('_'); print(''.join(w.capitalize() for w in parts))")
  # Source dataset uses different naming
  if [[ "$f" == *"pg_source"* ]]; then NAME="PgSourceDataset"; fi
  az synapse dataset create \
    --workspace-name fedexsynapseus \
    --name "$NAME" \
    --file @"$f"
done
```

### 4. Deploy and run pipeline

```bash
# Create pipeline
az synapse pipeline create \
  --workspace-name fedexsynapseus \
  --name PgToSynapseMigration \
  --file @migrations/synapse/pipeline/pipeline_pg_to_synapse.json

# Run pipeline
az synapse pipeline create-run \
  --workspace-name fedexsynapseus \
  --name PgToSynapseMigration

# Monitor (use the runId from the output above)
az synapse pipeline-run show \
  --workspace-name fedexsynapseus \
  --run-id <run-id>
```

### 5. Verify

```sql
SELECT 'businesses' AS tbl, COUNT(*) AS cnt FROM businesses
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'shipment_events', COUNT(*) FROM shipment_events
UNION ALL SELECT 'notifications', COUNT(*) FROM notifications;
```

## Data Volumes

| Table | Row Count |
|-------|-----------|
| `businesses` | 300 |
| `orders` | 10,000 |
| `shipment_events` | 54,841 |
| `notifications` | 54,847 |

## Important Notes

- **All `az synapse` artifact JSON files must have a `"properties": { ... }` wrapper.**
- The workspace default SQL linked service (`fedexsynapseus-WorkspaceDefaultSqlServer`) requires a `DBName` parameter — pass the pool name (`fedexpool`) in each sink dataset's `linkedServiceName.parameters`.
- **Synapse RBAC ≠ Azure RBAC.** The service principal needs the **Synapse Administrator** role on the workspace (separate from Azure Contributor).
- **Truncate tables before re-running** to avoid duplicate data.
- **Pause the SQL pool** when not in use to save costs: `az synapse sql pool pause --name fedexpool --workspace-name fedexsynapseus --resource-group fedex`
