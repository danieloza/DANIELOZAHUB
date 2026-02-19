# DANIELOZA AI Site

Public portfolio website for DANIELOZA.AI: offer, case studies, demo playgrounds, and AI tool mockups.

## Live Scope
- Landing and offer pages: `index.html`, `oferta.html`, `kontakt.html`, `faq.html`
- Portfolio and audit: `portfolio.html`, `audyt.html`
- Studio pages: `demo.html`, `kling.html`, `seedance-1-5-pro.html`, `gemini.html`, `seedream-4-0.html`, `seedream-4-5.html`

## Stack
- HTML5
- CSS3 (`assets/css/style.css`)
- Vanilla JavaScript (`assets/js/main.js`)

## Run Local

Option 1 (project helper):
```powershell
.\start-dev.ps1
```

Option 2 (simple static server):
```powershell
cd C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site
python -m http.server 5500 --bind 127.0.0.1
```

Then open: `http://127.0.0.1:5500`

## Project Notes
- Design direction: `SITE_DIRECTION_2026-02-17.md`
- Legacy cleanup log: `LEGACY_CLEANUP_REPORT_2026-02-17.md`
- Old variants and backups are stored in `_legacy_archive/`
- Analytics event map and debug mode: `ANALYTICS_EVENTS.md`
- GA4 setup and report templates: `GA4_REPORTING_SETUP.md`
- Analytics runtime config: `assets/js/analytics.config.js`
- Weekly digest runner: `run-weekly-digest.ps1`

## Backend Additions
- Lead endpoint: `POST /api/leads`
- Analytics ingest: `POST /api/analytics/events`
- Weekly KPI report: `GET /api/reports/weekly`
- Admin summary: `GET /api/admin/summary`
- Admin leads: `GET /api/admin/leads`
  - Win prediction enabled by query: `GET /api/admin/leads?include_win=true`
- Lead backfill: `POST /api/admin/leads/backfill`
- Feature flags status: `GET /api/admin/features`
- Channel cost CSV import: `POST /api/admin/channel-costs/import-csv`

Helpers:
```powershell
.\run-leads-backfill.ps1 -Limit 5000
.\run-api-rollout-tests.ps1
```
- Admin recent events: `GET /api/admin/events/recent`
- Lead meta update: `POST /api/admin/leads/{lead_id}/meta`
- Follow-up templates: `GET/POST /api/admin/followups/templates`
- Follow-up logs: `GET /api/admin/followups/logs`

## SEO + Legal
- `robots.txt`
- `sitemap.xml`
- `privacy.html`
- `cookies.html`

## SMTP Lead Notifications (optional)
Set in `backend/.env`:
- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_FROM` (fallback: `SMTP_USER`)
- `SMTP_STARTTLS` (`true`/`false`, default `true`)
- `LEAD_NOTIFY_TO` (owner mailbox for new leads)
- `LEAD_AUTOREPLY_ENABLED` (`true`/`false`, default `true`)

Security rotation helper:
```powershell
.\rotate-smtp-pass.ps1
```
This updates only `SMTP_PASS` in `backend/.env` using hidden input.

## E2E Forms Test (real DB write + SMTP send)
```powershell
.\run-e2e-forms.ps1
```
The test:
- starts local SMTP capture server,
- posts real leads for `audyt` and `kontakt`,
- verifies lead rows in SQLite,
- verifies outgoing notify + autoreply messages.

## GA4 Measurement ID
Set in `assets/js/analytics.config.js`:
- `ga4_measurement_id: "G-XXXXXXXXXX"`

## Role split (fixed)
- Lead operator (non-technical): use only `admin-simple.html`
- Ops/admin technical: use only `admin.html`

## Operational cadence
Daily:
- queue handling + complete `deal_value`/`lost_reason`

Weekly:
- run `./run-api-rollout-tests.ps1`
- quick ROI review (channel costs and gaps)

## Free Admin Dashboard
- Open `admin.html`
- Beginner mode: open `admin-simple.html` (single-lead, full-screen KROK 1/2/3, auto next lead, help call button)
- Set API base (default: `http://127.0.0.1:8000`)
- If `ADMIN_TOKEN` is set, paste it into dashboard token field
- Set `operator@email` in admin top bar (used in task audit as actor)
- `Eksport CSV` button downloads recent leads from dashboard table
- Panel `Feature flags + backfill` in `admin.html` allows:
  - rollout toggle (`AUTOPILOT_ENABLED`, `WIN_MODEL_ENABLED`, `ROI_ENABLED`)
  - one-click leads backfill (autopilot + win snapshot)
- Auto refresh every 30s with retry on temporary fetch failure
- CRM actions: status (`new/in_progress/won/lost`), notes, follow-up datetime
- Follow-up template editor (24h/72h) and follow-up logs preview
- Kanban board: drag lead card between columns to change status quickly
- Auto lead tier scoring (`hot/warm/cold`) with tier filter and score preview
- Duplicate detection by email (duplicate badge + `dup only` filter + KPI duplicates)
- Follow-up due queue with quick postpone actions (`+24h`, `+72h`)

## Free Hardening
Set in `backend/.env`:
- `CORS_ALLOW_ORIGINS=https://twoja-domena.pl,http://127.0.0.1:5500`
- `PUBLIC_ORIGIN_ALLOWLIST=https://twoja-domena.pl,http://127.0.0.1:5500`
- `ADMIN_TOKEN=...` (protects `/api/admin/*`)
- `AUTOPILOT_ENABLED=true|false`
- `WIN_MODEL_ENABLED=true|false`
- `ROI_ENABLED=true|false`

## Data Quality Guardrails
- `status=won` requires `deal_value > 0`
- `status=lost` requires non-empty `lost_reason`
- Lead hygiene validation at ingest:
  - always valid `email`
  - for `kontakt`: valid `telefon`, non-empty `budzet`, non-empty `zakres/cel/opis`

## Free Alerts (no paid tools)
Set in `backend/.env`:
- `ALERT_NOTIFY_TO=twoj@mail.pl`
- `ALERT_HEALTH_URL=http://127.0.0.1:8000/api/health`
- `ALERT_MIN_LEADS_24H=1`
- `OPS_ALERT_EMAIL=twoj@mail.pl` (P1 SLA task alerts)
- `OPS_SLACK_WEBHOOK_URL=` (optional Slack webhook for P1 SLA task alerts)

Run manually:
```powershell
.\run-health-check.ps1
```

## Follow-up Automation (24h/72h)
Run manually:
```powershell
.\run-followup-dispatch.ps1
```
Templates are editable in `admin.html`.

## Quality Monitoring (daily/weekly)
Set in `backend/.env`:
- `ALERT_MIN_LEADS_AUDYT_24H`
- `ALERT_MIN_LEADS_KONTAKT_24H`
- `ALERT_CONV_DROP_PCT` (default `30`, alert on WoW drop >= 30%)
- `QUALITY_REPORT_SEND_ALWAYS=true`

Run manually:
```powershell
.\run-quality-report.ps1 -Mode daily
.\run-quality-report.ps1 -Mode weekly
```

## Backup / Restore / Export
Backup with retention:
```powershell
.\backup-db.ps1 -RetentionDays 14
```
Restore from backup:
```powershell
.\restore-db.ps1 -BackupPath .\backend\backups\jobs-YYYYMMDD_HHMMSS.sqlite3
```
Full export (JSON + CSV):
```powershell
.\run-export-data.ps1
```

Set free automation in Windows Task Scheduler:
```powershell
.\setup-free-automation.ps1
```

Task scripts use `backend-task-bootstrap.ps1`:
- load `backend/.env`
- use `backend/.venv`
- install dependencies only when `backend/requirements.txt` hash changes

## Portfolio Highlights
- Custom multi-page UI system with consistent studio navigation
- Mock AI workflows (generation queue, slots, status, preview)
- Reusable styling architecture and responsive layouts

## License
Private portfolio project. Reuse only with author permission.

## Self-booking + Cockpit (new)
- Public booking page: `booking.html`
- Booking API: `GET /api/public/booking/{lead_id}?token=...`
- Booking confirm API: `POST /api/public/booking/{lead_id}/confirm`
- Cockpit list API: `GET /api/admin/cockpit/today`
- Cockpit one-click API: `POST /api/admin/leads/{lead_id}/cockpit-action`
- Pipeline report API: `GET /api/admin/reports/pipeline`

### Extra env vars
- `BOOKING_PAGE_URL`
- `LEAD_TEST_EMAIL_DOMAINS`
- `LEAD_FAKE_PATTERNS`
- `LEAD_IP_REPEAT_THRESHOLD`
- `PIPELINE_REPORT_SEND_ALWAYS`

### Daily pipeline runner
```powershell
.\run-pipeline-report.ps1 -Days 1
```

## Autonomous Engine (live connectors)
Connector endpoints:
- `GET /api/admin/autonomous/connectors`
- `POST /api/admin/autonomous/connectors`
- `POST /api/admin/autonomous/connectors/{channel}/sync`
- `POST /api/admin/autonomous/plans/{plan_id}/submit`
- `POST /api/admin/autonomous/approvals/{approval_id}/decision`
- `POST /api/admin/autonomous/plans/{plan_id}/apply-approved`
- `POST /api/admin/autonomous/run-daily`

Env for live execution:
- `AUTONOMOUS_CONNECTOR_DEFAULT_APPLY_URL`
- `AUTONOMOUS_CONNECTOR_DEFAULT_HEALTH_URL`
- `AUTONOMOUS_CONNECTOR_DEFAULT_TOKEN`

Per-channel override (example for `google_ads`):
- `AUTONOMOUS_GOOGLE_ADS_APPLY_URL`
- `AUTONOMOUS_GOOGLE_ADS_HEALTH_URL`
- `AUTONOMOUS_GOOGLE_ADS_TOKEN`

Notes:
- `mode=simulate` -> no external call, internal dry-run.
- `mode=live` -> backend sends signed HTTP request to connector URL.
- Guardrail limit `daily_change_limit_pct` blocks oversize budget deltas before connector call.

Quick setup on local backend (mock live connectors):
```powershell
.\setup-live-connectors.ps1
```
This script:
- sets connector env vars in `backend/.env`,
- configures channels (`google_ads`, `meta_ads`, `linkedin`) as `live`,
- runs connector sync checks.



