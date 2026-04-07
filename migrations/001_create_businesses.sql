-- Migration: 001_create_businesses
-- Creates the businesses table

CREATE TABLE IF NOT EXISTS businesses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    account_number TEXT NOT NULL UNIQUE,
    address     TEXT,
    contact_email TEXT,
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
