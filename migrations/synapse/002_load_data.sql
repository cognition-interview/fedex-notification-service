-- Load data from Azure Data Lake Storage into Synapse dedicated SQL pool
-- Prerequisites:
--   1. Tables created via 001_create_schema.sql
--   2. CSV files uploaded to: https://fedexstorageus.dfs.core.windows.net/synapse/migration/
--   3. Master key exists in the database
--
-- CSV format notes (PostgreSQL → Synapse compatibility):
--   - Timestamps exported without timezone (AT TIME ZONE 'UTC') for DATETIME2
--   - Booleans exported as 0/1 for BIT columns
--   - Enum values exported as plain text (::text cast) for NVARCHAR columns

IF NOT EXISTS (SELECT * FROM sys.symmetric_keys WHERE name = '##MS_DatabaseMasterKey##')
    CREATE MASTER KEY;

-- Load businesses
COPY INTO [businesses]
FROM 'https://fedexstorageus.dfs.core.windows.net/synapse/migration/businesses.csv'
WITH (
    FILE_TYPE = 'CSV',
    FIRSTROW = 2,
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0A',
    FIELDQUOTE = '"',
    ENCODING = 'UTF8',
    CREDENTIAL = (IDENTITY = 'Managed Identity')
);

-- Load orders
COPY INTO [orders]
FROM 'https://fedexstorageus.dfs.core.windows.net/synapse/migration/orders.csv'
WITH (
    FILE_TYPE = 'CSV',
    FIRSTROW = 2,
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0A',
    FIELDQUOTE = '"',
    ENCODING = 'UTF8',
    CREDENTIAL = (IDENTITY = 'Managed Identity')
);

-- Load shipment_events
COPY INTO [shipment_events]
FROM 'https://fedexstorageus.dfs.core.windows.net/synapse/migration/shipment_events.csv'
WITH (
    FILE_TYPE = 'CSV',
    FIRSTROW = 2,
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0A',
    FIELDQUOTE = '"',
    ENCODING = 'UTF8',
    CREDENTIAL = (IDENTITY = 'Managed Identity')
);

-- Load notifications
COPY INTO [notifications]
FROM 'https://fedexstorageus.dfs.core.windows.net/synapse/migration/notifications.csv'
WITH (
    FILE_TYPE = 'CSV',
    FIRSTROW = 2,
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0A',
    FIELDQUOTE = '"',
    ENCODING = 'UTF8',
    CREDENTIAL = (IDENTITY = 'Managed Identity')
);

-- Verify counts
SELECT 'businesses' AS table_name, COUNT(*) AS row_count FROM businesses
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'shipment_events', COUNT(*) FROM shipment_events
UNION ALL
SELECT 'notifications', COUNT(*) FROM notifications;
