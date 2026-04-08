-- Synapse dedicated SQL pool: fedexpool
-- Create tables matching PostgreSQL schema with Synapse-compatible types
-- Type mappings: UUID->NVARCHAR(36), TEXT->NVARCHAR(n), TIMESTAMPTZ->DATETIME2,
--                BOOLEAN->BIT, ENUMs->NVARCHAR(50), NUMERIC->DECIMAL, DATE->DATE

-- Drop tables in reverse dependency order if they exist
IF OBJECT_ID('dbo.notifications', 'U') IS NOT NULL DROP TABLE dbo.notifications;
IF OBJECT_ID('dbo.shipment_events', 'U') IS NOT NULL DROP TABLE dbo.shipment_events;
IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
IF OBJECT_ID('dbo.businesses', 'U') IS NOT NULL DROP TABLE dbo.businesses;

CREATE TABLE dbo.businesses (
    id              NVARCHAR(36)    NOT NULL,
    name            NVARCHAR(255)   NOT NULL,
    account_number  NVARCHAR(100)   NOT NULL,
    address         NVARCHAR(500)   NULL,
    contact_email   NVARCHAR(255)   NULL,
    phone           NVARCHAR(50)    NULL,
    created_at      DATETIME2       NOT NULL
)
WITH (
    DISTRIBUTION = REPLICATE,
    CLUSTERED COLUMNSTORE INDEX
);

CREATE TABLE dbo.orders (
    id                  NVARCHAR(36)    NOT NULL,
    business_id         NVARCHAR(36)    NOT NULL,
    tracking_number     NVARCHAR(100)   NOT NULL,
    origin              NVARCHAR(255)   NOT NULL,
    destination         NVARCHAR(255)   NOT NULL,
    status              NVARCHAR(50)    NOT NULL,
    weight_lbs          DECIMAL(8,2)    NULL,
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

CREATE TABLE dbo.notifications (
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    business_id NVARCHAR(36)    NOT NULL,
    type        NVARCHAR(50)    NOT NULL,
    message     NVARCHAR(4000)  NOT NULL,
    is_read     BIT             NOT NULL,
    created_at  DATETIME2       NOT NULL
)
WITH (
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);
