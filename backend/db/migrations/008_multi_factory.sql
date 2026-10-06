-- Migration 008: multi-company / factory selection + onboarding (ADDITIVE ONLY).
-- Run this manually in the Supabase SQL editor after 001..007.
-- Safe to run multiple times. No table is dropped, no data is deleted, and
-- every existing row keeps working (factory_id stays NULL = legacy company).
--
-- Design:
--   * factory_profile becomes the factory/company registry. Each row is one
--     company/factory. `onboarding` holds the 8-step wizard state as JSONB.
--   * The oldest existing row (the single factory this app shipped with)
--     becomes the DEFAULT / LEGACY company (is_default = true). Its existing
--     approved profile + operational data are untouched.
--   * factory_id columns let newly created companies own their own rows.
--     Legacy rows keep factory_id = NULL and stay visible to the default
--     company only.

-- ---------------------------------------------------------------------------
-- 1. Factory / company registry (extend the existing factory_profile table)
-- ---------------------------------------------------------------------------
ALTER TABLE factory_profile ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE factory_profile ADD COLUMN IF NOT EXISTS onboarding JSONB;
ALTER TABLE factory_profile ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;

-- Mark the oldest profile row as the legacy/default company (one-time).
UPDATE factory_profile SET name = COALESCE(name, industry, 'IndAI Factory')
WHERE name IS NULL;
UPDATE factory_profile SET is_default = TRUE
WHERE id = (SELECT id FROM factory_profile ORDER BY created_at ASC, id ASC LIMIT 1)
  AND NOT EXISTS (SELECT 1 FROM factory_profile WHERE is_default = TRUE);

-- ---------------------------------------------------------------------------
-- 2. Factory scoping columns on operational tables (all nullable -> safe)
-- ---------------------------------------------------------------------------
ALTER TABLE employees          ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE machines           ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE orders             ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE tasks              ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE production_runs    ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE machine_telemetry  ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE maintenance        ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE incidents          ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE factory_memory     ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE ai_recommendations ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE work_plans         ADD COLUMN IF NOT EXISTS factory_id UUID;
ALTER TABLE plan_assignments   ADD COLUMN IF NOT EXISTS factory_id UUID;

-- ---------------------------------------------------------------------------
-- 3. Onboarding-friendly fields the existing models did not carry.
--    (Additive; NULL for every existing row, so nothing is rewritten.)
-- ---------------------------------------------------------------------------
ALTER TABLE employees ADD COLUMN IF NOT EXISTS employee_code VARCHAR(50);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS department VARCHAR(255);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS experience_years INTEGER;

ALTER TABLE machines ADD COLUMN IF NOT EXISTS machine_code VARCHAR(50);
ALTER TABLE machines ADD COLUMN IF NOT EXISTS department VARCHAR(255);
ALTER TABLE machines ADD COLUMN IF NOT EXISTS criticality VARCHAR(50);

-- ---------------------------------------------------------------------------
-- 4. Indexes for factory-scoped reads.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_employees_factory       ON employees(factory_id);
CREATE INDEX IF NOT EXISTS idx_machines_factory        ON machines(factory_id);
CREATE INDEX IF NOT EXISTS idx_orders_factory          ON orders(factory_id);
CREATE INDEX IF NOT EXISTS idx_tasks_factory           ON tasks(factory_id);
CREATE INDEX IF NOT EXISTS idx_production_runs_factory ON production_runs(factory_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_factory       ON machine_telemetry(factory_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_factory     ON maintenance(factory_id);
CREATE INDEX IF NOT EXISTS idx_incidents_factory       ON incidents(factory_id);
CREATE INDEX IF NOT EXISTS idx_factory_memory_factory  ON factory_memory(factory_id);
CREATE INDEX IF NOT EXISTS idx_ai_recs_factory         ON ai_recommendations(factory_id);
