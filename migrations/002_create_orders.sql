-- Migration: 002_create_orders
-- Creates the orders table

CREATE TYPE order_status AS ENUM (
    'Picked Up',
    'In Transit',
    'Out for Delivery',
    'Delivered',
    'Delayed',
    'Exception'
);

CREATE TYPE service_type AS ENUM (
    'FedEx Ground',
    'FedEx Express',
    'FedEx Overnight',
    'FedEx 2Day',
    'FedEx International'
);

CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    tracking_number TEXT NOT NULL UNIQUE,
    origin          TEXT NOT NULL,
    destination     TEXT NOT NULL,
    status          order_status NOT NULL DEFAULT 'Picked Up',
    weight_lbs      NUMERIC(8, 2),
    service_type    service_type NOT NULL DEFAULT 'FedEx Ground',
    estimated_delivery DATE,
    actual_delivery    DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_business_id ON orders(business_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);
