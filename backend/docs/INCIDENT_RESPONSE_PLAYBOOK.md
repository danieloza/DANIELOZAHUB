# Incident Response Playbook (MVP)

## Scope
Dotyczy incydentow backendu MVP (`auth`, `billing`, `jobs`, `worker`, `stripe webhook`).

## Severity
- `SEV-1`: produkcja nie przyjmuje platnosci albo tworzenie jobow jest niedostepne dla wiekszosci userow.
- `SEV-2`: degradacja (rosnaca kolejka, opoznienia, pojedyncze bledy webhook/job).
- `SEV-3`: pojedyncze przypadki, niski impact, brak utraty przychodu.

## First 10 Minutes
1. Potwierdz alert i otworz incydent.
2. Uruchom szybki triage:
   - `.\incident-triage.ps1 -BackendBaseUrl <url> -BackendAdminToken <token>`
   - artefakt JSON zapisuje sie do `backend/reports/incident-triage-*.json`
3. Sprawdz:
   - `ready_ok`
   - `db_ok`
   - `worker_running` + heartbeat
   - `queue_depth.queued`
   - `webhook_failed_last_hour`
   - `jobs_failed_last_hour`
   - `dead_letters_last_24h`
4. Przypisz ownera i severity (`SEV-1/2/3`).
5. Jesli `SEV-1`, od razu wpis status update do klientow/kanalu wewnetrznego.

## Triage Decision Tree
### A) `webhook_failed_last_hour > 0`
1. Zweryfikuj `STRIPE_WEBHOOK_SECRET` na runtime.
2. Sprawdz ostatnie `webhook_events` z `status='failed'` przez `GET /api/ops/webhook-events?status=failed`.
3. Po fixie replay eventu Stripe (idempotencja powinna zapobiec duplikatom).

### B) `queue_depth.queued` rosnie lub `worker_running=false`
1. Sprawdz heartbeat workera i logi deploya.
2. Potwierdz `MVP_WORKER_ENABLED=true` i `LEGACY_QUEUE_WORKER_ENABLED=false`.
3. Sprawdz `worker.recovered_last_summary` w `GET /api/ops/metrics` (czy recovery stale `running` jobs zadzialal).
4. Zrob redeploy (`Backend Deploy`) i monitoruj metryki przez 10-15 min.

### C) `jobs_failed_last_hour` lub `dead_letters_last_24h` rosna
1. Pobierz `/api/ops/dead-letters`.
2. Zidentyfikuj wspolny powod (`reason`, `provider`, `input`).
3. W razie regresji: rollback deploy + otwarcie hotfix branch.

### D) `db_ok=false`
1. Traktuj jako `SEV-1`.
2. Sprawdz status DB (Render/Fly) i connectivity.
3. Wstrzymaj deploye do czasu stabilizacji.

## Communication Template
`[SEV-X] <timestamp UTC> - Incident <short title>. Impact: <who/how many>. Current status: <investigating|mitigating|resolved>. Next update in <N> min.`

## Resolution Checklist
1. Potwierdz normalizacje metryk przez >= 15 min.
2. Uruchom `Backend Live Smoke`.
3. Zweryfikuj recznie:
   - signup/login
   - checkout webhook processed
   - job created + succeeded
4. Zamknij incydent i zapisz timeline.

## Postmortem (max 24h)
1. Root cause.
2. Co wykrylo incydent i czy wykrylo na czas.
3. Co zatrzymalo eskalacje.
4. Dzialania zapobiegawcze (owner + deadline).
