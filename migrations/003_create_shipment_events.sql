-- Migration: 003_create_shipment_events
-- Creates the shipment_events table (scan history per order)

CREATE TYPE event_type AS ENUM (
    'Package Picked Up',
    'Arrived at FedEx Hub',
    'Departed FedEx Hub',
    'In Transit',
    'Out for Delivery',
    'Delivery Attempted',
    'Delivered',
    'Delay Reported',
    'Exception',
    'Package at Local Facility'
);

CREATE TABLE IF NOT EXISTS shipment_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id    UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    event_type  event_type NOT NULL,
    location    TEXT NOT NULL,
    description TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shipment_events_order_id ON shipment_events(order_id);
CREATE INDEX idx_shipment_events_occurred_at ON shipment_events(occurred_at);
