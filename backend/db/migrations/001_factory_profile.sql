-- Phase A: factory_profile (additive only, safe to run multiple times).
-- Run this manually in Supabase SQL editor. Never drop/reset existing tables.
-- Endpoints return a clear error naming this file when the table is missing.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS factory_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    industry VARCHAR(255),
    status VARCHAR(50) DEFAULT 'DRAFT',
    answers JSONB,
    profile JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
