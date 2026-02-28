# MVP Runbook

## Scope
Runbook for MVP SaaS core (`auth`, `credits`, `stripe`, `jobs`, `worker`) implemented in `backend/mvp_billing.py`.
Legacy `kling` job endpoints in `backend/app.py` are kept only for backward compatibility and marked as deprecated.
Go-live checklist: `backend/docs/MVP_GO_LIVE_CHECKLIST.md`.
Incident response playbook: `backend/docs/INCIDENT_RESPONSE_PLAYBOOK.md`.
Staging setup: `backend/docs/STAGING_SETUP.md`.

## Required Environment
- `DATABASE_URL`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_CREDIT_PRICE_CENTS` (default `100`)
- `ADMIN_TOKEN`

Optional:
- `REPLICATE_API_TOKEN`
- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE`
- `MVP_RUNNING_STALE_SECONDS` (default `300`, recovery stale `running` jobs on worker start)
- `AUTH_ORIGIN_ALLOWLIST`
- `CORS_ALLOW_ORIGINS`
- `PUBLIC_ORIGIN_ALLOWLIST`
- `ALLOW_LOCALHOST_ORIGINS` (set `false` on production)
- `ALLOW_NULL_ORIGIN` (set `false` on production)
- `AUTH_LOGIN_*`
- `MONITOR_ALERT_WEBHOOK_URL` (GitHub Actions secret dla alertow z `backend-monitor.yml`)

## Processes
- Web API:
  - command: `python -m uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
  - env: `MVP_WORKER_ENABLED=false`, `LEGACY_QUEUE_WORKER_ENABLED=false`
- Worker:
  - command: `python -m backend.mvp_worker_runner`
  - env: `MVP_WORKER_ENABLED=true`, `LEGACY_QUEUE_WORKER_ENABLED=false`

## Write Idempotency
- Send `Idempotency-Key` for:
  - `POST /api/jobs`
  - `POST /api/billing/checkout-session`
- `POST /api/jobs` also supports body field `idempotency_key`.
- Repeated request with same key returns existing job and does not create extra credit hold.

## Release Procedure
1. Deploy new image/build.
2. Run migrations: `python backend/migrate_postgres.py`.
3. Start web + worker.
4. Verify:
   - `GET /api/health`
   - `GET /api/ready`
   - `GET /api/ops/metrics` (with admin token)
   - `GET /api/ops/dead-letters` (with admin token)
   - `GET /api/ops/webhook-events?status=failed` (with admin token)

## Backup and Restore
- Create backup: `.\backup-postgres.ps1`
- Restore backup: `.\restore-postgres.ps1 -BackupPath <file> -ResetPublicSchema`
- Verify restore on temp DB: `.\verify-postgres-backup-restore.ps1 -BackupPath <file>`

## Rollback
1. Roll app back to previous release.
2. Keep DB schema forward-compatible where possible.
3. If rollback needs data repair:
   - inspect `webhook_events`
   - inspect `credit_ledger`
   - inspect `job_dead_letters`

## Incidents

### Stripe webhook errors
Symptoms:
- `webhook_failed_last_hour > 0`

Checklist:
1. Confirm `STRIPE_WEBHOOK_SECRET`.
2. Inspect recent rows in `webhook_events` with `status='failed'` (API: `GET /api/ops/webhook-events?status=failed`).
3. Replay event from Stripe Dashboard after fix.

### Worker stuck / queue growing
Symptoms:
- `/api/ready` => `worker_ok=false`
- `queue_depth.queued` rising

Checklist:
1. Confirm worker process is running.
2. Check `worker_last_heartbeat`.
3. Check worker recovery summary (`worker.recovered_last_summary`) in `GET /api/ops/metrics`.
4. Check `last_error` in `jobs`.
5. Check `job_dead_letters`.

### Credits mismatch
Symptoms:
- user balance unexpected

Checklist:
1. Recalculate from `credit_ledger` (`SUM(amount)`).
2. Verify idempotency keys (`stripe:{event_id}:topup`, `job:{job_id}:*`).
3. If compensation needed, use `adjustment` ledger entry (never mutate old rows).
4. Use endpoint `POST /api/ops/credits/adjust` (admin token), not manual SQL.

## Alerts (minimum)
- `webhook_failed_last_hour > 0`
- `jobs_failed_last_hour > threshold`
- worker heartbeat age > 60s
- queued jobs grows for 10+ minutes
- dead-letter growth > threshold (`dead_letters_last_24h`)

## Security Operations
- Rotate leaked/old Stripe keys immediately.
- Do not store live secrets in repo.
- Keep `ADMIN_TOKEN` separate from user auth tokens.
