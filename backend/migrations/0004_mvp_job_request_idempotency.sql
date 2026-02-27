ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS request_idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_user_request_idempotency
  ON jobs (user_id, request_idempotency_key)
  WHERE request_idempotency_key IS NOT NULL;
