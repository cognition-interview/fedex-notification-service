# PostgreSQL → Azure Synapse Analytics Migration

This directory contains scripts and SQL to migrate data from the PostgreSQL database to an Azure Synapse Analytics dedicated SQL pool.

## Architecture

```
PostgreSQL (source)
    │
    │  scripts/export_postgres_for_synapse.sh
    ▼
CSV files (local)
    │
    │  az storage fs file upload
    ▼
Azure Data Lake Storage (fedexstorageus/synapse/migration/)
    │
    │  COPY INTO (Managed Identity)
    ▼
Azure Synapse dedicated SQL pool (fedexpool)
```

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
| `TIMESTAMPTZ` | `DATETIME2` | Timezone stripped during export (UTC) |
| `BOOLEAN` | `BIT` | Exported as `0`/`1` |
| Custom ENUMs | `NVARCHAR(50)` | Cast to text during export |
| `NUMERIC(8,2)` | `DECIMAL(8,2)` | Direct mapping |
| `DATE` | `DATE` | Direct mapping |

## Files

| File | Purpose |
|------|---------|
| `migrations/synapse/001_create_schema.sql` | Creates all four tables in Synapse |
| `migrations/synapse/002_load_data.sql` | COPY INTO statements to load CSVs from Data Lake |
| `scripts/export_postgres_for_synapse.sh` | Exports PostgreSQL data as Synapse-compatible CSVs |

## How to Run

### 1. Export data from PostgreSQL

```bash
export POSTGRES_CONNECTION_STRING="postgresql://user:pass@host:5432/dbname"
./scripts/export_postgres_for_synapse.sh /tmp/pg_export
```

### 2. Upload CSVs to Azure Data Lake Storage

```bash
STORAGE_KEY=$(az storage account keys list \
  --account-name fedexstorageus \
  --resource-group fedex \
  --query "[0].value" -o tsv)

for f in /tmp/pg_export/*.csv; do
  az storage fs file upload \
    --file-system synapse \
    --path "migration/$(basename $f)" \
    --source "$f" \
    --account-name fedexstorageus \
    --account-key "$STORAGE_KEY" \
    --overwrite
done
```

### 3. Create schema and load data

Connect to Synapse using `sqlcmd` or Azure Data Studio:

```bash
sqlcmd -S fedexsynapseus.sql.azuresynapse.net \
  -d fedexpool -U sqladminuser -P '<password>' \
  -C -I -i migrations/synapse/001_create_schema.sql

sqlcmd -S fedexsynapseus.sql.azuresynapse.net \
  -d fedexpool -U sqladminuser -P '<password>' \
  -C -I -i migrations/synapse/002_load_data.sql
```

## Data Volumes

| Table | Row Count |
|-------|-----------|
| `businesses` | 300 |
| `orders` | 10,000 |
| `shipment_events` | 54,841 |
| `notifications` | 54,847 |
