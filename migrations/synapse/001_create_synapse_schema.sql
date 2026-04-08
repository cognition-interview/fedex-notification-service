-- Migration: 001_create_synapse_schema
-- Creates Synapse-compatible schema in dedicated SQL pool (fedexpool)
-- Type mappings from PostgreSQL:
--   UUID         → NVARCHAR(36)
--   TEXT         → NVARCHAR(n)
--   TIMESTAMPTZ  → DATETIME2
--   BOOLEAN      → BIT
--   Custom ENUMs → NVARCHAR(50)
--   NUMERIC(p,s) → DECIMAL(p,s)
--   DATE         → DATE
--
-- Distribution strategy:
--   REPLICATE    → small dimension tables (businesses)
--   HASH(key)    → large fact tables (orders, shipment_events, notifications)
--   All tables   → CLUSTERED COLUMNSTORE INDEX for analytics workloads

-- Drop tables in reverse dependency order
IF OBJECT_ID('dbo.notifications', 'U') IS NOT NULL DROP TABLE dbo.notifications;
IF OBJECT_ID('dbo.shipment_events', 'U') IS NOT NULL DROP TABLE dbo.shipment_events;
IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
IF OBJECT_ID('dbo.businesses', 'U') IS NOT NULL DROP TABLE dbo.businesses;

-- businesses (small dimension table → REPLICATE)
CREATE TABLE dbo.businesses (
    id              NVARCHAR(36)    NOT NULL,
    name            NVARCHAR(255)   NOT NULL,
    account_number  NVARCHAR(50)    NOT NULL,
    address         NVARCHAR(500)   NULL,
    contact_email   NVARCHAR(255)   NULL,
    phone           NVARCHAR(50)    NULL,
    created_at      DATETIME2       NOT NULL
)
WITH (
    DISTRIBUTION = REPLICATE,
    CLUSTERED COLUMNSTORE INDEX
);

-- orders (large fact table → HASH on business_id for join performance)
CREATE TABLE dbo.orders (
    id                  NVARCHAR(36)    NOT NULL,
    business_id         NVARCHAR(36)    NOT NULL,
    tracking_number     NVARCHAR(50)    NOT NULL,
    origin              NVARCHAR(255)   NOT NULL,
    destination         NVARCHAR(255)   NOT NULL,
    status              NVARCHAR(50)    NOT NULL,
    weight_lbs          DECIMAL(8, 2)   NULL,
    service_type        NVARCHAR(50)    NOT NULL,
    estimated_delivery  DATE            NULL,
    actual_delivery     DATE            NULL,
    created_at          DATETIME2       NOT NULL,
    updated_at          DATETIME2       NOT NULL
)
WITH (
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);

-- shipment_events (large fact table → HASH on order_id for join performance)
CREATE TABLE dbo.shipment_events (
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    event_type  NVARCHAR(50)    NOT NULL,
    location    NVARCHAR(255)   NOT NULL,
    description NVARCHAR(1000)  NULL,
    occurred_at DATETIME2       NOT NULL
)
WITH (
    DISTRIBUTION = HASH(order_id),
    CLUSTERED COLUMNSTORE INDEX
);

-- notifications (large fact table → HASH on business_id for join performance)
CREATE TABLE dbo.notifications (
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    business_id NVARCHAR(36)    NOT NULL,
    type        NVARCHAR(50)    NOT NULL,
    message     NVARCHAR(2000)  NOT NULL,
    is_read     BIT             NOT NULL,
    created_at  DATETIME2       NOT NULL
)
WITH (
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);
