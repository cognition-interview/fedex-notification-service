-- Synapse DDL for FedEx Notification Service
-- Type mappings from PostgreSQL:
--   UUID         → NVARCHAR(36)
--   TEXT         → NVARCHAR(n)
--   TIMESTAMPTZ  → DATETIME2
--   BOOLEAN      → BIT
--   Custom ENUMs → NVARCHAR(50)
--   NUMERIC(8,2) → DECIMAL(8,2)
--   DATE         → DATE

-- Drop tables in reverse dependency order
IF OBJECT_ID('dbo.notifications', 'U') IS NOT NULL DROP TABLE dbo.notifications;
IF OBJECT_ID('dbo.shipment_events', 'U') IS NOT NULL DROP TABLE dbo.shipment_events;
IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
IF OBJECT_ID('dbo.businesses', 'U') IS NOT NULL DROP TABLE dbo.businesses;

-- Small dimension table: REPLICATE distribution
CREATE TABLE dbo.businesses (
    id              NVARCHAR(36)   NOT NULL,
    name            NVARCHAR(100)  NOT NULL,
    account_number  NVARCHAR(50)   NOT NULL,
    address         NVARCHAR(200)  NULL,
    contact_email   NVARCHAR(200)  NULL,
    phone           NVARCHAR(50)   NULL,
    created_at      DATETIME2      NOT NULL
)
WITH (
    DISTRIBUTION = REPLICATE,
    CLUSTERED COLUMNSTORE INDEX
);

-- Large fact table: HASH on business_id for join-aligned distribution
CREATE TABLE dbo.orders (
    id                  NVARCHAR(36)   NOT NULL,
    business_id         NVARCHAR(36)   NOT NULL,
    tracking_number     NVARCHAR(50)   NOT NULL,
    origin              NVARCHAR(200)  NOT NULL,
    destination         NVARCHAR(200)  NOT NULL,
    status              NVARCHAR(50)   NOT NULL,
    weight_lbs          DECIMAL(8,2)   NULL,
    service_type        NVARCHAR(50)   NOT NULL,
    estimated_delivery  DATE           NULL,
    actual_delivery     DATE           NULL,
    created_at          DATETIME2      NOT NULL,
    updated_at          DATETIME2      NOT NULL
)
WITH (
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);

-- Large fact table: HASH on order_id for join-aligned distribution
CREATE TABLE dbo.shipment_events (
    id          NVARCHAR(36)   NOT NULL,
    order_id    NVARCHAR(36)   NOT NULL,
    event_type  NVARCHAR(50)   NOT NULL,
    location    NVARCHAR(200)  NOT NULL,
    description NVARCHAR(500)  NULL,
    occurred_at DATETIME2      NOT NULL
)
WITH (
    DISTRIBUTION = HASH(order_id),
    CLUSTERED COLUMNSTORE INDEX
);

-- Large fact table: HASH on business_id for join-aligned distribution
CREATE TABLE dbo.notifications (
    id          NVARCHAR(36)   NOT NULL,
    order_id    NVARCHAR(36)   NOT NULL,
    business_id NVARCHAR(36)   NOT NULL,
    type        NVARCHAR(50)   NOT NULL,
    message     NVARCHAR(500)  NOT NULL,
    is_read     BIT            NOT NULL,
    created_at  DATETIME2      NOT NULL
)
WITH (
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);
