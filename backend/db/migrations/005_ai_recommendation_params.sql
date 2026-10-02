-- Phase 4 (mobile-app track): params for assistant-proposed actions.
-- Additive only: one nullable JSONB column, IF NOT EXISTS. Never drop/reset.
-- If this migration is NOT applied, the decision endpoint degrades clearly
-- (assistant proposals report "params column missing" instead of executing).
ALTER TABLE ai_recommendations ADD COLUMN IF NOT EXISTS params JSONB;
