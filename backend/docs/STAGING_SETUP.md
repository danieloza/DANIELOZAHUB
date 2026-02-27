# Staging Setup (Render)

## Goal
Oddzielne srodowisko staging do testow przed produkcja, bez ryzyka naruszenia runtime prod.

## Minimal Staging Topology
1. `web` service: `danieloza-ai-staging-web`
2. (opcjonalnie) `worker` service: `danieloza-ai-staging-worker`
3. osobna baza Postgres: `danieloza-ai-staging-db`

## Required GitHub Secrets (staging)
- `RENDER_STAGING_WEB_SERVICE_ID`
- `RENDER_STAGING_WORKER_SERVICE_ID` (optional)
- `STAGING_BACKEND_BASE_URL`
- `STAGING_BACKEND_ADMIN_TOKEN`
- `STAGING_STRIPE_WEBHOOK_SECRET`
- `STAGING_MONITOR_ALERT_WEBHOOK_URL` (optional)

## Workflows
- deploy staging: `.github/workflows/backend-deploy-staging.yml`
- monitor staging: `.github/workflows/backend-monitor-staging.yml`
- smoke staging: `.github/workflows/backend-live-smoke-staging.yml`

## Suggested Runtime Settings
- `MVP_WORKER_ENABLED=true` (all-in-one fallback) lub web+worker oddzielnie.
- `LEGACY_QUEUE_WORKER_ENABLED=false`
- `AUTH_ORIGIN_ALLOWLIST` tylko do staging URL + localhost.
- stagingowy `ADMIN_TOKEN` inny niz production.
- stagingowy `STRIPE_WEBHOOK_SECRET` inny niz production.

## Recommended Flow
1. Deploy feature branch na staging.
2. Run `Backend Live Smoke Staging`.
3. Run `Backend Monitor Staging`.
4. Dopiero po zielonym staging -> deploy production.
