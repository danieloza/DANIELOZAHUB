# GA4 Reporting Setup (Recommended)

## 0) Connect Measurement ID
In `assets/js/analytics.config.js` set:
- `ga4_measurement_id: "G-XXXXXXXXXX"`

## 1) Register Event-Scoped Custom Dimensions
In GA4: Admin -> Custom definitions -> Create custom dimensions.

Create these event-scoped dimensions:
- `label`
- `path`
- `href`
- `session_id`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_term`
- `utm_content`
- `percent`
- `seconds`
- `max_scroll_percent`
- `metric`
- `value`
- `rating`

## 2) Mark Key Events as Conversions
In GA4: Admin -> Events -> Mark as conversion:
- `form_submit`
- `cta_click` (optionally, if you segment by `label`)

## 3) Recommended Explorations

### A) Funnel: Landing -> Oferta -> Kontakt -> Form Submit
- Technique: Funnel exploration
- Steps:
  1. `page_view` where `path` = `/index.html` (or landing path)
  2. `page_view` where `path` = `/oferta.html`
  3. `page_view` where `path` = `/kontakt.html`
  4. `form_submit` where `label` = `kontakt_form_submit`

### B) CTA Quality by Label
- Technique: Free form
- Rows: `label`
- Metrics: Event count, Conversions
- Filter: Event name in (`cta_click`, `form_submit`)

### C) Content Engagement by Page
- Technique: Free form
- Rows: `path`
- Metrics:
  - Event count (`scroll_depth`)
  - Event count (`engaged_time`)
  - Event count (`page_exit`)
  - Average of `seconds` (from `page_exit`)

## 4) Naming Discipline
- Keep `data-track-label` stable over time.
- Avoid changing label names after campaigns start.
- Prefer lowercase snake-case labels for new events.

## 5) QA Checklist
- Open page with `?debugAnalytics=1`.
- Confirm floating debug panel is visible (bottom-right).
- Click `Hide` and verify launcher badge `A <count>` can reopen panel.
- Click `Export` in panel and verify JSON file is downloaded.
- Verify `page_view` appears once.
- Click one CTA and verify `cta_click`.
- Submit `audyt` or `kontakt` form and verify `form_submit`.
- Scroll past 50% and verify `scroll_depth` for `25`, `50`.
- Click external link and verify `outbound_click`.

## 6) Sampling Controls (Optional)
- Temporary URL override: `?sampleRate=0.3`
- Persistent local override: `localStorage.setItem('dz_event_sample','0.3')`
- Remove override: `localStorage.removeItem('dz_event_sample')`
- Runtime helper: `window.DANIELOZA_ANALYTICS.setSampleRate(0.3)`

## 7) Weekly Digest (Backend)
- API report endpoint: `GET /api/reports/weekly?days=7&fmt=json`
- Markdown version: `GET /api/reports/weekly?days=7&fmt=md`
- Optional protection token:
  - set env `WEEKLY_REPORT_TOKEN=...`
  - pass `x-report-token` header or `?token=...`
- Generate digest files manually:
  - `.\run-weekly-digest.ps1`
- Optional webhook push:
  - set env `WEEKLY_DIGEST_WEBHOOK_URL=https://...`
