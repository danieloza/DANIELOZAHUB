# MVP SaaS Implementation Plan (Hardening First)

Date: 2026-02-27

## Goal
Ship MVP that survives first paying users without billing bugs, double-credit spends, or silent queue failures.

## Non-Negotiables
1. Credits are an immutable ledger (`credit_ledger`), never a mutable counter.
2. Stripe webhook is idempotent (`webhook_events` dedup + safe replay).
3. Async execution has retries, backoff, and explicit statuses.
4. Job status and execution history are persisted from day 1.
5. Deploy includes minimum monitoring and logs from day 1.

## Target Stack
- API: FastAPI
- DB: PostgreSQL (required)
- Queue: DB-backed queue first (`jobs` table), Redis optional later
- Hosting: Render (faster start) or Fly.io (more worker control)
- Domain: `danieloza.ai`

## Data Model (PostgreSQL)

### `users`
- `id UUID PRIMARY KEY`
- `email CITEXT UNIQUE NOT NULL`
- `password_hash TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `is_active BOOLEAN NOT NULL DEFAULT true`

### `plans`
- `id TEXT PRIMARY KEY` (for example: `starter`, `pro`)
- `name TEXT NOT NULL`
- `monthly_price_cents INTEGER NOT NULL`
- `monthly_credits INTEGER NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### `credit_ledger`
Immutable transactions, positive and negative.
- `id UUID PRIMARY KEY`
- `user_id UUID NOT NULL REFERENCES users(id)`
- `entry_type TEXT NOT NULL` (`topup`, `hold`, `consume`, `release`, `refund`, `adjustment`)
- `amount INTEGER NOT NULL` (signed credits)
- `balance_after INTEGER` (optional snapshot for audit/debug)
- `source_type TEXT NOT NULL` (`stripe_event`, `job`, `admin`, `system`)
- `source_id TEXT NOT NULL`
- `idempotency_key TEXT NOT NULL UNIQUE`
- `meta JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `(user_id, created_at DESC)`
- `(source_type, source_id)`

### `jobs`
- `id UUID PRIMARY KEY`
- `user_id UUID NOT NULL REFERENCES users(id)`
- `provider TEXT NOT NULL` (for example: `replicate`)
- `operation TEXT NOT NULL` (for example: `image.generate`)
- `status TEXT NOT NULL` (`queued`, `running`, `succeeded`, `failed`)
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `max_attempts INTEGER NOT NULL DEFAULT 5`
- `available_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `started_at TIMESTAMPTZ`
- `finished_at TIMESTAMPTZ`
- `provider_job_id TEXT`
- `input_json JSONB NOT NULL`
- `result_json JSONB`
- `last_error TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `(status, available_at)`
- `(user_id, created_at DESC)`

### `job_events`
Append-only execution history.
- `id BIGSERIAL PRIMARY KEY`
- `job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE`
- `event_type TEXT NOT NULL` (`queued`, `started`, `retry_scheduled`, `succeeded`, `failed`)
- `payload JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Index:
- `(job_id, created_at)`

### `webhook_events`
- `id BIGSERIAL PRIMARY KEY`
- `provider TEXT NOT NULL` (`stripe`)
- `event_id TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `payload JSONB NOT NULL`
- `received_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `processed_at TIMESTAMPTZ`
- `status TEXT NOT NULL DEFAULT 'received'` (`received`, `processed`, `ignored`, `failed`)
- `error_text TEXT`

Constraint:
- `UNIQUE(provider, event_id)`

## Critical Flows

### 1) Stripe checkout -> credit ledger
1. Verify Stripe signature.
2. Insert into `webhook_events` with `UNIQUE(provider, event_id)`.
3. If unique conflict: return HTTP 200 (already handled).
4. Inside DB transaction:
   - Resolve `user_id`.
   - Insert ledger row with deterministic `idempotency_key` (for example `stripe:{event_id}:topup`).
   - Optionally persist `balance_after`.
   - Mark webhook row as `processed`.
5. Return HTTP 200 only after commit.

### 2) Create job -> reserve/consume credits
1. API validates request and required credit cost.
2. In one transaction:
   - Validate available balance (`SUM(amount)` or precomputed balance row with lock).
   - Insert ledger `hold` (negative amount, idempotency by `job_id`).
   - Insert `jobs` with status `queued`.
   - Insert `job_events` = `queued`.
3. Worker marks `running`.
4. On success: convert reservation to final consume (or keep `hold` + compensating `release/consume` policy).
5. On failure: release credits with ledger `release`.

## Queue and Retry Strategy
- Worker pull query uses `FOR UPDATE SKIP LOCKED` to avoid double processing.
- Retry policy: exponential backoff with jitter (for example 10s, 30s, 90s, 5m, 15m).
- Failed attempt updates:
  - `attempt_count += 1`
  - `status = queued` + `available_at = next_retry_at` (if attempts left)
  - else `status = failed` + `finished_at = now()`
- Every transition writes `job_events`.

## Monitoring and Logs (Day 1)
Minimum required:
- Structured JSON logs with: `request_id`, `user_id`, `job_id`, `stripe_event_id`, `status`, `latency_ms`.
- Health endpoints:
  - `/api/health` (liveness)
  - `/api/ready` (DB connectivity + worker heartbeat age)
- Error tracking: Sentry (or equivalent) for API + worker.
- Metrics to expose and alert:
  - queue depth (`jobs` queued/running/failed)
  - webhook failures per hour
  - job failure rate
  - p95 job duration

## 30-Day Execution Plan

### Days 1-7 (Foundation)
- Auth + session/JWT.
- Create DB schema: `users`, `plans`, `credit_ledger`, `jobs`, `job_events`, `webhook_events`.
- Add migrations and rollback scripts.
- Basic logged-in user panel.

Definition of done:
- user can register/login/logout
- DB migrations run on clean environment
- audit trail exists for credits and jobs

### Days 8-14 (Billing)
- Stripe Checkout integration.
- Webhook endpoint with signature verification and dedup.
- Credit top-up entries in `credit_ledger`.
- Credit reservation on job creation.

Definition of done:
- replaying same Stripe event does not duplicate credits
- creating job without balance returns deterministic 402/400 error

### Days 15-21 (AI Execution)
- Integrate one provider (Replicate suggested).
- Worker loop with retry + backoff.
- Persist provider IDs, outputs, errors.

Definition of done:
- status lifecycle is visible (`queued/running/succeeded/failed`)
- retries happen automatically and stop at `max_attempts`

### Days 22-30 (User Panel + Production)
- User dashboard: balance, ledger history, job history, limits.
- Deploy API + worker + Postgres on Render or Fly.
- Domain setup (`danieloza.ai`).
- E2E tests for critical path:
  - signup -> buy credits -> create job -> receive result

Definition of done:
- one-click release procedure exists
- logs and alerting are active in production
- critical E2E passes in CI

## MVP Out of Scope
- Multi-provider routing
- Advanced plan/proration logic
- Complex admin analytics
- Redis queue optimization before first paid traction

## Immediate Next Implementation Tasks
1. Add SQL migration `0001_mvp_core.sql` (Postgres) with tables and indexes above.
2. Add `backend/billing/stripe_webhook.py` with dedup transaction flow.
3. Add `backend/worker/runner.py` with retry and event logging.
4. Add API endpoints: `POST /api/jobs`, `GET /api/jobs`, `GET /api/credits/ledger`.
5. Add E2E smoke test for billing + job lifecycle.
