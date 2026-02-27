# OPERATIONS PLAYBOOK

## 0. Staly podzial pracy
1. Osoba obslugujaca leady pracuje tylko w `admin-simple.html`.
2. Ops/admin techniczny pracuje tylko w `admin.html`.
3. `admin.html` sluzy do: feature flags, backfill, ROI, incydenty, testy i konfiguracja.
4. Nie mieszamy paneli w codziennej obsludze.

## 0b. Rytm operacyjny
Codziennie:
1. Obsluga kolejki leadow (priorytet + win + due) w `admin-simple.html`.
2. Domkniecie danych: `deal_value` dla `won`, `lost_reason` dla `lost`.

Co tydzien:
1. Uruchom `./run-api-rollout-tests.ps1`.
2. Szybki przeglad ROI (koszty kanalow, odchylenia, brakujace wpisy).`r`n`r`n## 1. Start System
1. Open PowerShell.
2. Run:
```powershell
cd C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site
.\start-all.bat
```
3. Open:
- `http://127.0.0.1:5500/`
- `http://127.0.0.1:5500/admin.html`

## 2. Admin Login Setup
In `admin.html` top bar:
1. `API base`: `http://127.0.0.1:8000`
2. `ADMIN_TOKEN`: value from `backend/.env` (`ADMIN_TOKEN=...`)
3. `operator@email`: e.g. `ops@local` (saved in task audit)

## 3. Daily Lead Workflow
1. Filter by `priority`, `status`, `win reco`.
2. In `Autopilot queue`, handle leads in this order:
- `P1` first
- highest `Win%` first
- nearest `Due` first
3. Update lead status via Kanban/table.
4. Daily mandatory data close:
- every `won` lead must have `deal_value > 0`
- every `lost` lead must have non-empty `lost_reason`

## 4. Incident / Task Workflow
Use `Incident center`:
1. Work on `pending` and `in_progress` tasks.
2. Actions per task:
- `start`
- `reopen`
- `done`
- `cancel`
- `owner`
- `prio`
3. Batch actions for filtered list:
- `Batch done (filtered)`
- `Batch +24h (filtered)`
4. Verify all changes in `Task audit`.

## 5. Feature Flags and Rollout
Use `Feature flags + backfill` panel:
1. Click `Refresh flags`.
2. Set:
- `AUTOPILOT_ENABLED`
- `WIN_MODEL_ENABLED`
- `ROI_ENABLED`
3. Click `Save flags`.
4. Keep `persist .env` enabled if flags should survive restart.

API equivalents:
- `GET /api/admin/features`
- `POST /api/admin/features`

## 6. Backfill Historical Leads
From UI:
1. Set `limit` (e.g. `5000`).
2. Choose:
- `include_test`
- `include_spam`
- `refresh_autopilot`
- `refresh_win`
3. Click `Run backfill`.

Script alternative:
```powershell
.\run-leads-backfill.ps1 -Limit 5000
```

## 7. ROI Costs (Manual + CSV)
Manual:
1. Fill `date`, `channel`, `cost`.
2. Click `Zapisz koszt`.

CSV import:
1. Paste CSV in `Import CSV kosztow`.
2. Click `Import CSV kosztow`.

CSV format:
```csv
date_iso,channel,cost
2026-02-18,google_ads,120.50
2026-02-18,meta_ads,99
```

## 8. API/Worker Regression Tests
Run:
```powershell
.\run-api-rollout-tests.ps1
```
Expected:
- all tests `OK`

## 9. Data Quality Rules
Lead ingest validation:
1. Valid `email` required.
2. For `kontakt` form:
- valid `telefon`
- non-empty `budzet`
- non-empty `zakres/cel/opis`

Status consistency:
1. `won` requires `deal_value > 0`
2. `lost` requires `lost_reason`

## 10. Troubleshooting
1. `403 forbidden`:
- wrong/missing `ADMIN_TOKEN`
2. Empty dashboard:
- backend not running
- wrong `API base`
3. Autopilot/ROI/Win missing:
- check feature flags
4. `won` update fails:
- set `deal_value` first
5. `lost` update fails:
- provide `lost_reason`

## 11. Important Files
- `admin.html`
- `backend/app.py`
- `backend/db.py`
- `backend/.env`
- `backend/.env.example`
- `backend/api_rollout_tests.py`
- `run-api-rollout-tests.ps1`
- `run-leads-backfill.ps1`


