# Analytics Events Map

## Scope
Tracking is handled in `assets/js/main.js` and currently supports:
- `window.plausible(...)` if present
- `window.gtag(...)` if present
- `window.dataLayer.push(...)` if present
- runtime config via `assets/js/analytics.config.js` (`window.DANIELOZA_ANALYTICS_CONFIG`)
- GA4 script auto-load when `ga4_measurement_id` is set in runtime config
- backend ingestion endpoint: `POST /api/analytics/events`

## Core Event Names
- `cta_click`
- `form_submit`
- `billing_toggle`
- `page_view`
- `scroll_depth`
- `outbound_click`
- `engaged_time`
- `page_exit`
- `web_vital`
- `consent_update`
- `lead_submit_success`
- `lead_submit_error`
- `signup` (app panel)
- `checkout_started` (app panel)
- `checkout_success` (app panel)
- `job_created` (app panel)
- `job_succeeded` (app panel)

## Payload (props)
- `label`: human-readable action label
- `href`: clicked URL (or page marker for form submit)
- `path`: current pathname
- `session_id`: per-tab session identifier
- `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content` (when available)
- `percent` (for `scroll_depth`)
- `seconds` (for `engaged_time`, `page_exit`)
- `max_scroll_percent` (for `engaged_time`, `page_exit`)
- `metric`, `value`, `rating` (for `web_vital`)

## Where We Tag Explicitly
- `index.html`: nav, hero CTA, hub cards/buttons, mobile sticky CTA, mini-case CTA
- `oferta.html`: nav, billing switches, plan CTA buttons
- `portfolio.html`: nav, key outbound links (repo/live), demo/audyt links
- `audyt.html`: nav, form submit, form action buttons
- `kontakt.html`: nav, form submit, action buttons, email/social links in contact card

## Fallback Tracking (No `data-track` required)
If an element has no explicit `data-track`, script still tracks clicks on:
- `.socialbtn`
- `header nav a`
- `.btn`
- `.homeBtn`
- `.mobileCtaBarBtn`

## Debug Mode
Debug logs are enabled when one of the following is true:
- Host is `localhost` or `127.0.0.1`
- URL contains `?debugAnalytics=1`
- `localStorage.setItem('debugAnalytics','1')`
- `window.DANIELOZA_DEBUG_ANALYTICS = true`

Debug output:
- `console.table(...)` per event
- in-memory buffer: `window.__dzAnalyticsLog`
- floating debug panel in page corner (event counters + last events)
- launcher badge `A <count>` for hide/show and live event count
- `Export` button in panel downloads current debug event log as JSON

## Note About Forms
Submit buttons inside forms with `data-track-submit` are not counted as click CTA to avoid double-counting.
Form completion is tracked via the `submit` event (`form_submit`).
Forms with `data-track-submit` are automatically enriched with hidden fields:
`session_id`, `referrer`, `landing_path`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`.

## Additional Behavior
- `page_view` is sent on each page load.
- `scroll_depth` fires once per milestone: 25, 50, 75, 90.
- `outbound_click` fires for links leaving current origin.
- `engaged_time` fires for 15s, 30s, 60s (only when tab is visible).
- `page_exit` fires once when page is hidden/unloaded.
- `web_vital` sends LCP, CLS, INP (with rating: good / needs_improvement / poor).
- UTM values are read from URL and persisted to localStorage for later events.
- events are batched and sent to backend only when consent state is `granted`.
- app panel (`app.html`) sends `signup/checkout/job*` events directly to `POST /api/analytics/events`
  with `label=app_panel` and `payload.source=app_panel`.

## Consent Mode
- Consent key: `localStorage['dz_analytics_consent']`
- States: `pending`, `granted`, `denied`
- Default state is configurable in `assets/js/analytics.config.js` (`consent_default`)
- In `pending`/`denied`, external analytics providers and backend event ingestion are blocked.
- Consent banner is shown when state is `pending` (can be disabled via config).

## Sampling And Throttling
- Session-stable sampling is enabled in tracker:
  - default sample rates:
    - `scroll_depth`: `0.5`
    - `engaged_time`: `0.5`
    - others: `1.0`
- Override sample rate globally:
  - URL: `?sampleRate=0.2`
  - localStorage: `localStorage.setItem('dz_event_sample','0.2')`
- Event throttling is enabled for rapid repeats:
  - `cta_click`: 800ms
  - `outbound_click`: 800ms
  - `billing_toggle`: 250ms
- Values can be overridden in `assets/js/analytics.config.js` via:
  - `sample_rates`
  - `throttle_ms`

## Runtime API
Global helper object is available:
- `window.DANIELOZA_ANALYTICS.track(eventName, props)`
- `window.DANIELOZA_ANALYTICS.setSampleRate(0.3)`
- `window.DANIELOZA_ANALYTICS.clearSampleRate()`
- `window.DANIELOZA_ANALYTICS.getSampleRate('scroll_depth')`
- `window.DANIELOZA_ANALYTICS.getLogs()`
- `window.DANIELOZA_ANALYTICS.clearLogs()`
- `window.DANIELOZA_ANALYTICS.exportLogs()`
