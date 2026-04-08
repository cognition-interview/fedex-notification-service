#!/usr/bin/env python3
"""
Direct PostgreSQL → Azure Synapse migration script.

Reads from PostgreSQL and writes directly to the Synapse dedicated SQL pool
in batches — no intermediate CSV files needed. This is the CLI equivalent of
a Synapse Pipeline Copy Activity.

Usage:
    export POSTGRES_CONNECTION_STRING="postgresql://user:pass@host:5432/dbname"
    python3 scripts/migrate_pg_to_synapse.py \
        --synapse-server fedexsynapseus.sql.azuresynapse.net \
        --synapse-db fedexpool \
        --synapse-user sqladminuser \
        --synapse-password '<password>'

Requirements:
    pip install pyodbc psycopg2-binary
"""

import argparse
import os
import sys
import time
import pyodbc
import psycopg2


TABLES = [
    {
        "name": "businesses",
        "source_query": """
            SELECT id::text, name, account_number, address, contact_email, phone,
                   created_at AT TIME ZONE 'UTC' AS created_at
            FROM businesses
        """,
        "insert_sql": """
            INSERT INTO businesses (id, name, account_number, address, contact_email, phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        "columns": 7,
    },
    {
        "name": "orders",
        "source_query": """
            SELECT id::text, business_id::text, tracking_number, origin, destination,
                   status::text, weight_lbs, service_type::text,
                   estimated_delivery, actual_delivery,
                   created_at AT TIME ZONE 'UTC' AS created_at,
                   updated_at AT TIME ZONE 'UTC' AS updated_at
            FROM orders
        """,
        "insert_sql": """
            INSERT INTO orders (id, business_id, tracking_number, origin, destination,
                                status, weight_lbs, service_type,
                                estimated_delivery, actual_delivery, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        "columns": 12,
    },
    {
        "name": "shipment_events",
        "source_query": """
            SELECT id::text, order_id::text, event_type::text, location, description,
                   occurred_at AT TIME ZONE 'UTC' AS occurred_at
            FROM shipment_events
        """,
        "insert_sql": """
            INSERT INTO shipment_events (id, order_id, event_type, location, description, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
        "columns": 6,
    },
    {
        "name": "notifications",
        "source_query": """
            SELECT id::text, order_id::text, business_id::text, type::text, message,
                   CASE WHEN is_read THEN 1 ELSE 0 END AS is_read,
                   created_at AT TIME ZONE 'UTC' AS created_at
            FROM notifications
        """,
        "insert_sql": """
            INSERT INTO notifications (id, order_id, business_id, type, message, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        "columns": 7,
    },
]

BATCH_SIZE = 1000


def migrate_table(pg_conn, synapse_conn, table_def):
    """Copy a single table from PostgreSQL to Synapse in batches."""
    name = table_def["name"]
    pg_cur = pg_conn.cursor()
    syn_cur = synapse_conn.cursor()

    # Count source rows
    pg_cur.execute(f"SELECT COUNT(*) FROM {name}")
    total = pg_cur.fetchone()[0]

    # Check existing rows in Synapse
    syn_cur.execute(f"SELECT COUNT(*) FROM [{name}]")
    existing = syn_cur.fetchone()[0]
    if existing > 0:
        print(f"  {name}: already has {existing} rows, skipping (truncate first to reload)")
        return existing

    print(f"  {name}: migrating {total} rows ...", end="", flush=True)
    start = time.time()

    # Stream from PostgreSQL
    pg_cur.execute(table_def["source_query"])

    migrated = 0
    batch = []
    for row in pg_cur:
        batch.append(tuple(row))
        if len(batch) >= BATCH_SIZE:
            syn_cur.executemany(table_def["insert_sql"], batch)
            migrated += len(batch)
            batch = []
            print(f"\r  {name}: {migrated}/{total} rows", end="", flush=True)

    if batch:
        syn_cur.executemany(table_def["insert_sql"], batch)
        migrated += len(batch)

    synapse_conn.commit()
    elapsed = time.time() - start
    print(f"\r  {name}: {migrated}/{total} rows ({elapsed:.1f}s)")
    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migrate PostgreSQL data to Azure Synapse Analytics")
    parser.add_argument("--synapse-server", required=True, help="Synapse SQL endpoint")
    parser.add_argument("--synapse-db", required=True, help="Synapse dedicated SQL pool name")
    parser.add_argument("--synapse-user", required=True, help="SQL admin username")
    parser.add_argument("--synapse-password", required=True, help="SQL admin password")
    parser.add_argument("--pg-connection-string", default=None,
                        help="PostgreSQL connection string (default: $POSTGRES_CONNECTION_STRING)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Rows per batch (default: 1000)")
    args = parser.parse_args()

    global BATCH_SIZE
    BATCH_SIZE = args.batch_size

    pg_conn_str = args.pg_connection_string or os.environ.get("POSTGRES_CONNECTION_STRING")
    if not pg_conn_str:
        print("ERROR: PostgreSQL connection string not provided", file=sys.stderr)
        sys.exit(1)

    synapse_conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={args.synapse_server};"
        f"DATABASE={args.synapse_db};"
        f"UID={args.synapse_user};"
        f"PWD={args.synapse_password};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )

    print("Connecting to PostgreSQL ...")
    pg_conn = psycopg2.connect(pg_conn_str)

    print("Connecting to Synapse ...")
    synapse_conn = pyodbc.connect(synapse_conn_str, autocommit=False)

    print("\n=== Migration ===")
    results = {}
    for table_def in TABLES:
        try:
            count = migrate_table(pg_conn, synapse_conn, table_def)
            results[table_def["name"]] = count
        except Exception as e:
            print(f"\n  ERROR migrating {table_def['name']}: {e}")
            results[table_def["name"]] = f"ERROR: {e}"

    # Verification
    print("\n=== Verification ===")
    syn_cur = synapse_conn.cursor()
    pg_cur = pg_conn.cursor()
    all_ok = True
    for table_def in TABLES:
        name = table_def["name"]
        pg_cur.execute(f"SELECT COUNT(*) FROM {name}")
        pg_count = pg_cur.fetchone()[0]
        syn_cur.execute(f"SELECT COUNT(*) FROM [{name}]")
        syn_count = syn_cur.fetchone()[0]
        match = "OK" if pg_count == syn_count else "MISMATCH"
        if match != "OK":
            all_ok = False
        print(f"  {name}: PG={pg_count} Synapse={syn_count} [{match}]")

    pg_conn.close()
    synapse_conn.close()

    if all_ok:
        print("\nMigration complete — all counts match!")
    else:
        print("\nWARNING: Some counts do not match!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
