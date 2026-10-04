-- Worker auth fields (additive only, safe to run multiple times).
-- Extends the app's OWN worker_credentials table only. Never drop/reset.
ALTER TABLE worker_credentials ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE worker_credentials ADD COLUMN IF NOT EXISTS employee_code VARCHAR(50);
ALTER TABLE worker_credentials ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;
ALTER TABLE worker_credentials ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_credentials_email ON worker_credentials (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_credentials_code ON worker_credentials (employee_code) WHERE employee_code IS NOT NULL;
