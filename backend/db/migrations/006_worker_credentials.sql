-- Part A: worker_credentials (additive only, safe to run multiple times).
-- Mobile/prototype login for demo workers. Passwords stored as hashes ONLY.
-- Never drop/reset anything.
CREATE TABLE IF NOT EXISTS worker_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL UNIQUE REFERENCES employees(id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_worker_credentials_username ON worker_credentials(username);
