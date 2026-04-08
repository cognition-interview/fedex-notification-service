-- Azure Synapse Analytics Schema for FedEx Notification Service
-- Dedicated SQL Pool: fedexpool
-- Workspace: fedexsynapseus
--
-- This schema mirrors the PostgreSQL source schema with Synapse-compatible types:
--   PostgreSQL UUID       -> NVARCHAR(36)
--   PostgreSQL TEXT       -> NVARCHAR(n)
--   PostgreSQL TIMESTAMPTZ -> DATETIME2
--   PostgreSQL BOOLEAN    -> BIT
--   PostgreSQL custom ENUMs -> NVARCHAR(50)
--   PostgreSQL NUMERIC(8,2) -> DECIMAL(8,2)

-- ============================================================
-- Table: businesses
-- ============================================================
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'businesses')
CREATE TABLE businesses (
    id              NVARCHAR(36)    NOT NULL,
    name            NVARCHAR(500)   NOT NULL,
    account_number  NVARCHAR(100)   NOT NULL,
    address         NVARCHAR(1000)  NULL,
    contact_email   NVARCHAR(500)   NULL,
    phone           NVARCHAR(50)    NULL,
    created_at      DATETIME2       NOT NULL
);

-- ============================================================
-- Table: orders
-- ============================================================
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'orders')
CREATE TABLE orders (
    id                  NVARCHAR(36)    NOT NULL,
    business_id         NVARCHAR(36)    NOT NULL,
    tracking_number     NVARCHAR(100)   NOT NULL,
    origin              NVARCHAR(500)   NOT NULL,
    destination         NVARCHAR(500)   NOT NULL,
    status              NVARCHAR(50)    NOT NULL,   -- order_status enum values
    weight_lbs          DECIMAL(8,2)    NULL,
    service_type        NVARCHAR(50)    NOT NULL,   -- service_type enum values
    estimated_delivery  DATE            NULL,
    actual_delivery     DATE            NULL,
    created_at          DATETIME2       NOT NULL,
    updated_at          DATETIME2       NOT NULL
);

-- ============================================================
-- Table: shipment_events
-- ============================================================
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'shipment_events')
CREATE TABLE shipment_events (
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    event_type  NVARCHAR(50)    NOT NULL,   -- event_type enum values
    location    NVARCHAR(500)   NOT NULL,
    description NVARCHAR(2000)  NULL,
    occurred_at DATETIME2       NOT NULL
);

-- ============================================================
-- Table: notifications
-- ============================================================
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'notifications')
CREATE TABLE notifications (
    id          NVARCHAR(36)    NOT NULL,
    order_id    NVARCHAR(36)    NOT NULL,
    business_id NVARCHAR(36)    NOT NULL,
    type        NVARCHAR(50)    NOT NULL,   -- notification_type enum values
    message     NVARCHAR(4000)  NOT NULL,
    is_read     BIT             NOT NULL,
    created_at  DATETIME2       NOT NULL
);
