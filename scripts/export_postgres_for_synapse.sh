#!/usr/bin/env bash
# export_postgres_for_synapse.sh
#
# Exports data from PostgreSQL in a format compatible with Azure Synapse Analytics.
# Handles type conversions:
#   - TIMESTAMPTZ → timezone-stripped UTC timestamps (for DATETIME2)
#   - BOOLEAN → 0/1 integers (for BIT)
#   - Custom ENUMs → plain text (for NVARCHAR)
#
# Usage:
#   export POSTGRES_CONNECTION_STRING="postgresql://user:pass@host:5432/dbname"
#   ./scripts/export_postgres_for_synapse.sh [output_dir]
#
# Output: CSV files in output_dir (default: ./pg_export)

set -euo pipefail

OUTPUT_DIR="${1:-./pg_export}"
mkdir -p "$OUTPUT_DIR"

if [ -z "${POSTGRES_CONNECTION_STRING:-}" ]; then
  echo "ERROR: POSTGRES_CONNECTION_STRING is not set" >&2
  exit 1
fi

echo "Exporting PostgreSQL data to $OUTPUT_DIR ..."

echo "  → businesses"
psql "$POSTGRES_CONNECTION_STRING" -c "\COPY (
  SELECT id, name, account_number, address, contact_email, phone,
         created_at AT TIME ZONE 'UTC' AS created_at
  FROM businesses
) TO '$OUTPUT_DIR/businesses.csv' WITH (FORMAT CSV, HEADER, ENCODING 'UTF8')"

echo "  → orders"
psql "$POSTGRES_CONNECTION_STRING" -c "\COPY (
  SELECT id, business_id, tracking_number, origin, destination,
         status::text, weight_lbs, service_type::text,
         estimated_delivery, actual_delivery,
         created_at AT TIME ZONE 'UTC' AS created_at,
         updated_at AT TIME ZONE 'UTC' AS updated_at
  FROM orders
) TO '$OUTPUT_DIR/orders.csv' WITH (FORMAT CSV, HEADER, ENCODING 'UTF8')"

echo "  → shipment_events"
psql "$POSTGRES_CONNECTION_STRING" -c "\COPY (
  SELECT id, order_id, event_type::text, location, description,
         occurred_at AT TIME ZONE 'UTC' AS occurred_at
  FROM shipment_events
) TO '$OUTPUT_DIR/shipment_events.csv' WITH (FORMAT CSV, HEADER, ENCODING 'UTF8')"

echo "  → notifications"
psql "$POSTGRES_CONNECTION_STRING" -c "\COPY (
  SELECT id, order_id, business_id, type::text, message,
         CASE WHEN is_read THEN 1 ELSE 0 END AS is_read,
         created_at AT TIME ZONE 'UTC' AS created_at
  FROM notifications
) TO '$OUTPUT_DIR/notifications.csv' WITH (FORMAT CSV, HEADER, ENCODING 'UTF8')"

echo ""
echo "Export complete. Row counts:"
wc -l "$OUTPUT_DIR"/*.csv
