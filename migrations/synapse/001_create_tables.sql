-- Synapse dedicated SQL pool schema for FedEx Notification Service
-- Migrated from PostgreSQL; uses Synapse-compatible T-SQL types.
-- Distribution strategy: REPLICATE for small dimension tables, HASH for fact tables.

-- =============================================
-- businesses (dimension table — 300 rows)
-- =============================================
IF OBJECT_ID('dbo.notifications', 'U') IS NOT NULL DROP TABLE dbo.notifications;
IF OBJECT_ID('dbo.shipment_events', 'U') IS NOT NULL DROP TABLE dbo.shipment_events;
IF OBJECT_ID('dbo.orders', 'U') IS NOT NULL DROP TABLE dbo.orders;
IF OBJECT_ID('dbo.businesses', 'U') IS NOT NULL DROP TABLE dbo.businesses;

CREATE TABLE dbo.businesses
(
    id              NVARCHAR(36)    NOT NULL,
    name            NVARCHAR(200)   NOT NULL,
    account_number  NVARCHAR(50)    NOT NULL,
    address         NVARCHAR(500)   NULL,
    contact_email   NVARCHAR(320)   NULL,
    phone           NVARCHAR(30)    NULL,
    created_at      DATETIME2       NOT NULL
)
WITH
(
    DISTRIBUTION = REPLICATE,
    CLUSTERED COLUMNSTORE INDEX
);

-- =============================================
-- orders (fact table — 10 000 rows)
-- =============================================
CREATE TABLE dbo.orders
(
    id                  NVARCHAR(36)    NOT NULL,
    business_id         NVARCHAR(36)    NOT NULL,
    tracking_number     NVARCHAR(50)    NOT NULL,
    origin              NVARCHAR(200)   NOT NULL,
    destination         NVARCHAR(200)   NOT NULL,
    status              NVARCHAR(50)    NOT NULL,
    weight_lbs          DECIMAL(8,2)    NULL,
    service_type        NVARCHAR(50)    NOT NULL,
    estimated_delivery  DATE            NULL,
    actual_delivery     DATE            NULL,
    created_at          DATETIME2       NOT NULL,
    updated_at          DATETIME2       NOT NULL
)
WITH
(
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);

-- =============================================
-- shipment_events (fact table — ~55 000 rows)
-- =============================================
CREATE TABLE dbo.shipment_events
(
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    event_type  NVARCHAR(50)    NOT NULL,
    location    NVARCHAR(200)   NOT NULL,
    description NVARCHAR(1000)  NULL,
    occurred_at DATETIME2       NOT NULL
)
WITH
(
    DISTRIBUTION = HASH(order_id),
    CLUSTERED COLUMNSTORE INDEX
);

-- =============================================
-- notifications (fact table — ~55 000 rows)
-- =============================================
CREATE TABLE dbo.notifications
(
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    business_id NVARCHAR(36)    NOT NULL,
    type        NVARCHAR(50)    NOT NULL,
    message     NVARCHAR(4000)  NOT NULL,
    is_read     BIT             NOT NULL,
    created_at  DATETIME2       NOT NULL
)
WITH
(
    DISTRIBUTION = HASH(business_id),
    CLUSTERED COLUMNSTORE INDEX
);
