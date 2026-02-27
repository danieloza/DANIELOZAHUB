# DANIELOZA AI Site

## TL;DR
- Projekt przechodzi z portfolio/lead backendu do MVP SaaS z platnosciami i kredytami.
- Celem jest dzialajacy produkt: `auth + credits + Stripe + 1 provider + user history`.
- Marketing ma wspierac produkt, nie odwrotnie.

## Why This Exists
Ten projekt istnieje po to, aby zamienic ruch i leady w realny self-serve produkt AI:
- user zaklada konto,
- kupuje kredyty,
- uruchamia generacje,
- widzi status i historie zadan.

## Kierunek (2026)
- `Faza teraz`: stabilny marketing site i obsluga leadow.
- `Faza docelowa`: produkt self-serve (konto usera, kredyty, platnosci, joby async).
- `Priorytet`: najpierw fundament techniczny i monetyzacja, potem rozszerzanie demo.

## Scope Guardrails (MVP)
Na MVP robimy tylko:
- auth
- credits
- Stripe
- 1 provider AI
- 1 typ generacji (np. image)
- prosty dashboard usera

Poza MVP (na pozniej):
- rozbudowa wielu podstron/demo,
- dodatkowi providerzy,
- szerokie eksperymenty contentowe.

## MVP w 30 dni

### Etap 1 (Auth + Billing Core)
- logowanie i konta uzytkownikow
- kredyty w DB jako `ledger` (transakcje), nie tylko licznik
- Stripe Checkout + webhook (idempotentny)
- odejmowanie kredytow przy tworzeniu joba

### Etap 2 (Generacja AI)
- integracja z 1 API (np. Replicate)
- async queue + retry
- status joba: `queued`, `running`, `succeeded`, `failed`

### Etap 3 (Panel Usera)
- minimalny panel klienta
- historia generacji
- limity i widoczne saldo kredytow

### Deploy
- app: `Render` lub `Fly.io`
- DB: `PostgreSQL`
- domena: `danieloza.ai`

## Architecture (Target MVP)
```text
[Browser / UI]
      |
      v
[FastAPI API] -----> [PostgreSQL]
      |                    |
      |                    +--> users, jobs, credit_ledger, webhook_events
      |
      +--> [Stripe Webhook Endpoint] (idempotent + dedup)
      |
      +--> [Queue / Worker] -----> [AI Provider API]
                      |
                      +--> job status + retry + timeout
```

## System Design Highlights
- Credits stored as immutable ledger
- Credit reservation to avoid double spending
- Async job queue with retry and timeout handling
- Webhook idempotency with event deduplication
- Cost tracking per provider request

## Production Concerns
- idempotent Stripe webhooks
- retry logic with backoff
- rate limiting per user
- credit reservation system (prevent double spend)
- async job monitoring

## Aktualny zakres projektu
- strony glowne: `index.html`, `oferta.html`, `kontakt.html`, `faq.html`
- portfolio i audyt: `portfolio.html`, `case-studies.html`, `audyt.html`
- studio/demo: `demo.html`, `kling.html`, `seedance-1-5-pro.html`, `gemini.html`, `seedream-4-0.html`, `seedream-4-5.html`
- SEO/legal: `robots.txt`, `sitemap.xml`, `privacy.html`, `cookies.html`
- backend API: katalog `backend/`

## Stack
- frontend: HTML + CSS + JS
- backend: Python + FastAPI
- analytics: GA4 (`assets/js/analytics.config.js`)

## Uruchomienie lokalne

### Opcja 1 (zalecana)
```powershell
.\start-dev.ps1
```

### Opcja 2 (manualnie)
Frontend:
```powershell
python -m http.server 5500 --bind 127.0.0.1
```
Backend (osobny terminal):
```powershell
.\start-backend.ps1
```

Migracje MVP (PostgreSQL):
```powershell
cd backend
$env:DATABASE_URL="postgresql://USER:PASS@HOST:5432/DB"
.\.venv\Scripts\python.exe migrate_postgres.py
```

Smoke test krytycznej sciezki MVP:
```powershell
$env:DATABASE_URL="postgresql://USER:PASS@HOST:5432/DB"
$env:STRIPE_WEBHOOK_SECRET="whsec_..."
.\backend\.venv\Scripts\python.exe -m unittest -q backend\mvp_critical_path_test.py
.\backend\.venv\Scripts\python.exe -m unittest -q backend\mvp_billing_integrity_test.py
```

Backup i restore Postgresa:
```powershell
.\backup-postgres.ps1
.\verify-postgres-backup-restore.ps1 -BackupPath .\backend\backups\postgres\postgres-YYYYMMDD_HHMMSS.sql
```

One-shot go-live preflight + deploy:
```powershell
.\go-live-all-at-once.ps1 -Target render
```
Opcjonalnie `-Target fly` lub `-SkipDeploy` (tylko preflight bez triggera deploy).
Na start nie potrzebujesz wlasnej domeny: wystarczy URL uslugi z Render/Fly.

Rotacja runtime sekretow + hardening (lokalny `.env` + GitHub secrets + Render env):
```powershell
.\rotate-mvp-runtime-secrets.ps1 -RenderApiKey "<rnd_...>" -RenderWebServiceId "<srv_...>"
```
Uwaga: automatyzuje rotacje `ADMIN_TOKEN` i `STRIPE_WEBHOOK_SECRET`.
`STRIPE_SECRET_KEY` (klucz API) rotuj recznie w Stripe Dashboard.

Szybki triage incydentu (ready + metrics + dead letters):
```powershell
.\incident-triage.ps1 -BackendBaseUrl "https://danieloza-ai-web.onrender.com" -BackendAdminToken "<token>"
```

Adresy lokalne:
- frontend: `http://127.0.0.1:5500`
- backend: `http://127.0.0.1:8000`
- admin: `http://127.0.0.1:5500/admin.html`
- app panel: `http://127.0.0.1:5500/app.html`

## CI/CD i Deploy
- CI: `.github/workflows/backend-ci.yml` (Postgres service + migracje + testy MVP)
- CD manualny: `.github/workflows/backend-deploy.yml` (Render/Fly)
- Monitoring workflow: `.github/workflows/backend-monitor.yml` (ready + metrics thresholds)
- Live smoke workflow: `.github/workflows/backend-live-smoke.yml` (register -> webhook -> job na live backendzie)
- Staging deploy workflow: `.github/workflows/backend-deploy-staging.yml`
- Staging monitor workflow: `.github/workflows/backend-monitor-staging.yml`
- Staging live smoke workflow: `.github/workflows/backend-live-smoke-staging.yml`
- Render blueprint: `render.yaml`
- Render staging blueprint: `render.staging.yaml`
- Fly config: `fly.toml`
- Kontener: `Dockerfile`

## Struktura katalogow
- `assets/` - CSS, JS, obrazy, pliki statyczne
- `backend/` - API, raporty, worker, logika operacyjna
- `docs/` - plany, raporty, analityka (indeks: `docs/README.md`)
- `_legacy_archive/` - archiwum starych wariantow i backupow

## Najwazniejsze dokumenty
- `docs/README.md`
- `docs/MVP_SAAS_IMPLEMENTATION_PLAN_2026-02-27.md`
- `docs/ANALYTICS_EVENTS.md`
- `docs/GA4_REPORTING_SETUP.md`
- `docs/OPERATIONS_PLAYBOOK.md`
- `docs/MASTER_EXECUTION_PLAN_2026-2027.md`
- `backend/docs/MVP_RUNBOOK.md`
- `backend/docs/MVP_GO_LIVE_CHECKLIST.md`
- `backend/docs/STAGING_SETUP.md`
- `backend/docs/INCIDENT_RESPONSE_PLAYBOOK.md`

## API (skrot)
- `POST /api/leads`
- `POST /api/analytics/events`
- `GET /api/health`
- `POST /api/admin/*`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/credits/balance`
- `GET /api/credits/ledger`
- `POST /api/billing/checkout-session`
- `POST /api/billing/stripe/webhook`
- `POST /api/jobs`
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `GET /api/ready`
- `GET /api/ops/metrics` (admin token)
- `GET /api/ops/dead-letters` (admin token)
- `GET /api/ops/webhook-events` (admin token)
- `POST /api/ops/credits/adjust` (admin token)

Uwaga:
- legacy endpointy `/api/kling/jobs*` sa oznaczone jako deprecated (utrzymane pod kompatybilnosc).

## Status porzadkowania
- dokumentacja przeniesiona do `docs/`
- backupy Pythona przeniesione do `_legacy_archive/python-backups/`
- lokalne artefakty runtime izolowane w `.local-trash/` (niecommitowane)

## Licencja
Projekt prywatny. Wykorzystanie i reuse tylko za zgoda autora.
