# MVP Go-Live Checklist

## Security
- [ ] Rotate `STRIPE_SECRET_KEY` in Stripe Dashboard.
- [ ] Rotate `STRIPE_WEBHOOK_SECRET` and update app env.
- [ ] Rotate `ADMIN_TOKEN`.
- [ ] Set `AUTH_ORIGIN_ALLOWLIST` to production origins only.
- [ ] Set `CORS_ALLOW_ORIGINS` and `PUBLIC_ORIGIN_ALLOWLIST` to production origins only.
- [ ] Set `ALLOW_LOCALHOST_ORIGINS=false` and `ALLOW_NULL_ORIGIN=false` on production.

## Database and Recovery
- [ ] Run migrations: `python backend/migrate_postgres.py`.
- [ ] Create backup: `.\backup-postgres.ps1`.
- [ ] Verify restore on temp DB: `.\verify-postgres-backup-restore.ps1 -BackupPath <path>`.
- [ ] Confirm backup retention policy.

## Stripe
- [ ] Configure production webhook URL to `/api/billing/stripe/webhook`.
- [ ] Subscribe only required events (`checkout.session.completed`).
- [ ] Run replay/idempotency test (same event twice => single topup).
- [ ] Verify checkout session request uses `Idempotency-Key`.

## Runtime
- [ ] Deploy web process with `MVP_WORKER_ENABLED=false`.
- [ ] Deploy worker process with `MVP_WORKER_ENABLED=true`.
- [ ] Set `LEGACY_QUEUE_WORKER_ENABLED=false` on both.
- [ ] Verify `/api/ready` is `ok=true`.
- [ ] If worker service is unavailable on plan, run fallback all-in-one mode:
  - web only
  - `MVP_WORKER_ENABLED=true`
  - monitor `worker_heartbeat_age_s` from `/api/ops/metrics`

## Monitoring and Alerts
- [ ] Configure `SENTRY_DSN`.
- [ ] Configure alert checks for:
  - webhook failures per hour
  - failed jobs per hour
  - worker heartbeat age
  - queue growth
  - dead-letter growth
- [ ] Configure GitHub workflow `Backend Monitor` secrets:
  - `BACKEND_BASE_URL`
  - `BACKEND_ADMIN_TOKEN`
  - `MONITOR_ALERT_WEBHOOK_URL` (optional)
- [ ] Enable and check `Backend Live Smoke` workflow.
- [ ] Enable and check `Backend Monitor Staging` + `Backend Live Smoke Staging` before prod cutover.

## Incident Readiness
- [ ] Validate `.\incident-triage.ps1` against production URL.
- [ ] Keep `backend/docs/INCIDENT_RESPONSE_PLAYBOOK.md` up to date.

## Quality Gate
- [ ] Run one-shot script: `.\go-live-all-at-once.ps1 -Target render`.
- [ ] CI passing on branch (`Backend CI`).
- [ ] Manual deploy uses `Backend Deploy` preflight gate.
- [ ] Run local smoke tests:
  - `python -m unittest -q backend/mvp_critical_path_test.py`
  - `python -m unittest -q backend/mvp_billing_integrity_test.py`
- [ ] Verify `POST /api/jobs` with same `Idempotency-Key` returns same job id and single hold.
