# MVP Go-Live Checklist

## Security
- [ ] Rotate `STRIPE_SECRET_KEY` in Stripe Dashboard.
- [ ] Rotate `STRIPE_WEBHOOK_SECRET` and update app env.
- [ ] Rotate `ADMIN_TOKEN`.
- [ ] Set `AUTH_ORIGIN_ALLOWLIST` to production origins only.

## Database and Recovery
- [ ] Run migrations: `python backend/migrate_postgres.py`.
- [ ] Create backup: `.\backup-postgres.ps1`.
- [ ] Verify restore on temp DB: `.\verify-postgres-backup-restore.ps1 -BackupPath <path>`.
- [ ] Confirm backup retention policy.

## Stripe
- [ ] Configure production webhook URL to `/api/billing/stripe/webhook`.
- [ ] Subscribe only required events (`checkout.session.completed`).
- [ ] Run replay/idempotency test (same event twice => single topup).

## Runtime
- [ ] Deploy web process with `MVP_WORKER_ENABLED=false`.
- [ ] Deploy worker process with `MVP_WORKER_ENABLED=true`.
- [ ] Set `LEGACY_QUEUE_WORKER_ENABLED=false` on both.
- [ ] Verify `/api/ready` is `ok=true`.

## Monitoring and Alerts
- [ ] Configure `SENTRY_DSN`.
- [ ] Configure alert checks for:
  - webhook failures per hour
  - worker heartbeat age
  - queue growth
  - dead-letter growth
- [ ] Configure GitHub workflow `Backend Monitor` secrets:
  - `BACKEND_BASE_URL`
  - `BACKEND_ADMIN_TOKEN`

## Quality Gate
- [ ] Run one-shot script: `.\go-live-all-at-once.ps1 -Target render`.
- [ ] CI passing on branch (`Backend CI`).
- [ ] Manual deploy uses `Backend Deploy` preflight gate.
- [ ] Run local smoke tests:
  - `python -m unittest -q backend/mvp_critical_path_test.py`
  - `python -m unittest -q backend/mvp_billing_integrity_test.py`
