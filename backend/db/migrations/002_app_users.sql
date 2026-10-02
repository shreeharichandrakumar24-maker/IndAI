-- Phase 1: app_users (additive only, safe to run multiple times).
-- Links Supabase Auth users to IndAI roles. Never drop/reset anything.
CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supabase_uid TEXT UNIQUE NOT NULL,
    email VARCHAR(255),
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'OPERATOR',
    employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_app_users_supabase_uid ON app_users(supabase_uid);
