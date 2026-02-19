(() => {
  const analyticsCfg = window.DANIELOZA_ANALYTICS_CONFIG || {};
  const host = window.location.hostname;
  const params = new URLSearchParams(window.location.search);
  const isDevHost = host === "localhost" || host === "127.0.0.1" || host === "";
  const consentStorageKey = "dz_analytics_consent";

  const debugAnalytics =
    analyticsCfg.force_debug === true ||
    isDevHost ||
    params.get("debugAnalytics") === "1" ||
    localStorage.getItem("debugAnalytics") === "1" ||
    window.DANIELOZA_DEBUG_ANALYTICS === true;

  const sessionId = (() => {
    try {
      const key = "dz_session_id";
      const existing = sessionStorage.getItem(key);
      if (existing) return existing;
      const created = "s_" + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem(key, created);
      return created;
    } catch (_) {
      return "s_fallback";
    }
  })();

  function buildApiUrl(pathLike, fallbackPath) {
    const value = pathLike || fallbackPath || "";
    if (!value) return "";
    if (/^https?:\/\//i.test(value)) return value;
    const base = (analyticsCfg.api_base || "http://127.0.0.1:8000").replace(/\/$/, "");
    const path = value.startsWith("/") ? value : "/" + value;
    return base + path;
  }

  const eventsIngestUrl = buildApiUrl(analyticsCfg.events_endpoint, "/api/analytics/events");
  const leadsUrl = buildApiUrl(analyticsCfg.leads_endpoint, "/api/leads");
  const ga4MeasurementId = String(analyticsCfg.ga4_measurement_id || "").trim();
  let ga4Initialized = false;

  function ensureGa4Ready() {
    if (ga4Initialized || !ga4MeasurementId) return;

    window.dataLayer = window.dataLayer || [];
    if (typeof window.gtag !== "function") {
      window.gtag = function gtag() {
        window.dataLayer.push(arguments);
      };
    }

    window.gtag("js", new Date());
    window.gtag("config", ga4MeasurementId, {
      send_page_view: false,
      anonymize_ip: true
    });

    const src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ga4MeasurementId);
    if (!document.querySelector(`script[src="${src}"]`)) {
      const script = document.createElement("script");
      script.async = true;
      script.src = src;
      document.head.appendChild(script);
    }

    ga4Initialized = true;
  }

  function readUtm() {
    const keys = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];
    const out = {};
    keys.forEach((k) => {
      const fromUrl = params.get(k);
      if (fromUrl) {
        out[k] = fromUrl;
        try {
          localStorage.setItem("dz_" + k, fromUrl);
        } catch (_) {}
        return;
      }
      try {
        const stored = localStorage.getItem("dz_" + k);
        if (stored) out[k] = stored;
      } catch (_) {}
    });
    return out;
  }

  const utm = readUtm();
  const pageStartMs = Date.now();
  let maxScrollPercent = 0;
  let exitSent = false;
  let hasSentPageView = false;
  const pageType =
    Array.from(document.body.classList).find((cls) => cls.startsWith("page-")) ||
    (window.location.pathname === "/" || window.location.pathname.endsWith("index.html") ? "page-home" : "page-generic");

  const lastEventAt = {};
  const eventSampleDefaults = {
    page_view: 1,
    cta_click: 1,
    outbound_click: 1,
    form_submit: 1,
    billing_toggle: 1,
    page_exit: 1,
    scroll_depth: 0.5,
    engaged_time: 0.5,
    web_vital: 1,
    consent_update: 1,
    lead_submit_success: 1,
    lead_submit_error: 1
  };
  const throttleDefaults = {
    cta_click: 800,
    outbound_click: 800,
    billing_toggle: 250
  };
  const eventSampleConfig = { ...eventSampleDefaults, ...(analyticsCfg.sample_rates || {}) };
  const throttleConfig = { ...throttleDefaults, ...(analyticsCfg.throttle_ms || {}) };

  function getConsentState() {
    try {
      const stored = localStorage.getItem(consentStorageKey);
      if (stored === "granted" || stored === "denied") return stored;
    } catch (_) {}
    return analyticsCfg.consent_default || "pending";
  }

  let consentState = getConsentState();

  function canSendAnalytics(force) {
    return !!force || consentState === "granted";
  }

  function debugLog(payload) {
    if (!debugAnalytics) return;
    const row = {
      time: new Date().toISOString(),
      event: payload.eventName,
      label: payload.label || "",
      href: payload.href || "",
      path: payload.path || window.location.pathname,
      consent_state: consentState
    };
    try {
      console.table([row]);
    } catch (_) {
      console.log("[analytics]", row);
    }
    window.__dzAnalyticsLog = window.__dzAnalyticsLog || [];
    window.__dzAnalyticsLog.push(row);
  }

  function stableHash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i += 1) {
      h ^= str.charCodeAt(i);
      h += (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24);
    }
    return (h >>> 0) / 4294967295;
  }

  function getSampleRate(eventName) {
    const urlRate = Number(params.get("sampleRate"));
    if (!Number.isNaN(urlRate) && urlRate >= 0 && urlRate <= 1) return urlRate;

    try {
      const stored = Number(localStorage.getItem("dz_event_sample"));
      if (!Number.isNaN(stored) && stored >= 0 && stored <= 1) return stored;
    } catch (_) {}

    return eventSampleConfig[eventName] == null ? 1 : eventSampleConfig[eventName];
  }

  function shouldSampleIn(eventName) {
    const rate = getSampleRate(eventName);
    if (rate >= 1) return true;
    if (rate <= 0) return false;
    const bucket = stableHash(sessionId + "|" + eventName);
    return bucket <= rate;
  }

  function isThrottled(eventName, props) {
    const wait = throttleConfig[eventName];
    if (!wait) return false;

    const key = `${eventName}|${(props && props.label) || ""}|${(props && props.href) || ""}|${window.location.pathname}`;
    const now = Date.now();
    if (lastEventAt[key] && now - lastEventAt[key] < wait) return true;
    lastEventAt[key] = now;
    return false;
  }

  function exportDebugLogs() {
    const logs = Array.isArray(window.__dzAnalyticsLog) ? window.__dzAnalyticsLog : [];
    const payload = {
      exported_at: new Date().toISOString(),
      path: window.location.pathname,
      session_id: sessionId,
      events: logs
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `analytics-debug-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const serverEventQueue = [];
  let serverFlushTimer = null;

  function queueServerEvent(eventName, payload) {
    if (!eventsIngestUrl || consentState !== "granted") return;
    serverEventQueue.push({
      event_name: eventName,
      label: payload.label || "",
      path: payload.path || window.location.pathname,
      href: payload.href || "",
      session_id: payload.session_id || sessionId,
      consent_state: consentState,
      created_at: new Date().toISOString(),
      payload
    });
    if (serverEventQueue.length > 50) {
      serverEventQueue.splice(0, serverEventQueue.length - 50);
    }

    if (!serverFlushTimer) {
      serverFlushTimer = window.setTimeout(() => {
        serverFlushTimer = null;
        flushServerEvents(false);
      }, 1200);
    }
  }

  function flushServerEvents(useBeacon) {
    if (!eventsIngestUrl || consentState !== "granted") return;
    if (!serverEventQueue.length) return;

    const chunk = serverEventQueue.splice(0, 50);
    const body = JSON.stringify({ events: chunk });

    if (useBeacon && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(eventsIngestUrl, blob);
      return;
    }

    fetch(eventsIngestUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
      credentials: "omit"
    }).catch(() => {
      // drop silently to avoid UI impact
    });
  }

  function trackEvent(eventName, props, opts) {
    const options = opts || {};

    if (!options.force) {
      if (!shouldSampleIn(eventName)) return;
      if (isThrottled(eventName, props)) return;
    }

    const payload = {
      session_id: sessionId,
      consent_state: consentState,
      ...utm,
      ...(props || {})
    };

    debugLog({
      eventName,
      label: payload.label,
      href: payload.href,
      path: payload.path
    });

    if (!canSendAnalytics(options.force)) return;
    ensureGa4Ready();

    try {
      if (typeof window.plausible === "function") {
        window.plausible(eventName, { props: payload });
      }
      if (typeof window.gtag === "function") {
        window.gtag("event", eventName, payload);
      }
      if (Array.isArray(window.dataLayer)) {
        window.dataLayer.push({ event: eventName, ...payload });
      }
    } catch (_) {
      // no-op: analytics should never break UI
    }

    queueServerEvent(eventName, payload);

    if (eventName === "page_view") {
      hasSentPageView = true;
    }
  }

  function setConsentState(nextState) {
    consentState = nextState;
    try {
      localStorage.setItem(consentStorageKey, nextState);
    } catch (_) {}

    trackEvent(
      "consent_update",
      {
        label: "consent_" + nextState,
        href: window.location.pathname + "#consent",
        path: window.location.pathname
      },
      { force: true }
    );

    if (nextState === "granted" && !hasSentPageView) {
      trackEvent(
        "page_view",
        {
          label: document.title || "page_view",
          href: window.location.href,
          path: window.location.pathname
        },
        { force: true }
      );
    }

    if (nextState === "granted") {
      flushServerEvents(false);
    }
  }

  function setupConsentBanner() {
    if (analyticsCfg.show_consent_banner === false) return;
    if (consentState === "granted" || consentState === "denied") return;

    const bar = document.createElement("div");
    bar.id = "dz-consent-bar";
    bar.style.position = "fixed";
    bar.style.left = "12px";
    bar.style.right = "12px";
    bar.style.bottom = "12px";
    bar.style.zIndex = "100001";
    bar.style.border = "1px solid rgba(255,255,255,.18)";
    bar.style.borderRadius = "12px";
    bar.style.padding = "10px";
    bar.style.background = "rgba(8,12,20,.96)";
    bar.style.color = "#fff";
    bar.style.boxShadow = "0 14px 30px rgba(0,0,0,.45)";
    bar.style.font = "12px/1.4 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif";

    const text = document.createElement("div");
    text.innerHTML = "Uzywam analityki do poprawy strony i mierzenia konwersji. Mozesz zaakceptowac lub odrzucic sledzenie. <a href='privacy.html' style='color:#c9d6ff'>Prywatnosc</a> i <a href='cookies.html' style='color:#c9d6ff'>Cookies</a>.";

    const row = document.createElement("div");
    row.style.marginTop = "8px";
    row.style.display = "flex";
    row.style.gap = "8px";

    const deny = document.createElement("button");
    deny.type = "button";
    deny.textContent = "Odrzuc";
    deny.style.cssText = "border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;border-radius:10px;padding:6px 10px;cursor:pointer";
    deny.addEventListener("click", () => {
      setConsentState("denied");
      bar.remove();
    });

    const allow = document.createElement("button");
    allow.type = "button";
    allow.textContent = "Akceptuj";
    allow.style.cssText = "border:1px solid rgba(125,107,255,.45);background:rgba(125,107,255,.26);color:#fff;border-radius:10px;padding:6px 10px;cursor:pointer";
    allow.addEventListener("click", () => {
      setConsentState("granted");
      bar.remove();
    });

    row.appendChild(deny);
    row.appendChild(allow);
    bar.appendChild(text);
    bar.appendChild(row);
    document.body.appendChild(bar);
  }

  function setupDebugPanel() {
    if (!debugAnalytics || analyticsCfg.debug_panel === false) return;

    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.id = "dz-analytics-launcher";
    launcher.style.position = "fixed";
    launcher.style.right = "12px";
    launcher.style.bottom = "12px";
    launcher.style.zIndex = "100000";
    launcher.style.border = "1px solid rgba(255,255,255,.25)";
    launcher.style.borderRadius = "999px";
    launcher.style.padding = "6px 10px";
    launcher.style.background = "rgba(8,12,20,.94)";
    launcher.style.backdropFilter = "blur(8px)";
    launcher.style.color = "#fff";
    launcher.style.font = "11px/1.2 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif";
    launcher.style.cursor = "pointer";
    launcher.style.boxShadow = "0 14px 28px rgba(0,0,0,.38)";
    launcher.textContent = "A 0";

    const panel = document.createElement("aside");
    panel.id = "dz-analytics-panel";
    panel.style.position = "fixed";
    panel.style.right = "12px";
    panel.style.bottom = "48px";
    panel.style.zIndex = "99999";
    panel.style.width = "min(380px, calc(100vw - 24px))";
    panel.style.maxHeight = "58vh";
    panel.style.overflow = "hidden";
    panel.style.border = "1px solid rgba(255,255,255,.2)";
    panel.style.borderRadius = "12px";
    panel.style.background = "rgba(8,12,20,.94)";
    panel.style.backdropFilter = "blur(8px)";
    panel.style.color = "#f5f7fb";
    panel.style.font = "12px/1.4 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif";
    panel.style.boxShadow = "0 20px 40px rgba(0,0,0,.45)";

    const head = document.createElement("div");
    head.style.display = "flex";
    head.style.alignItems = "center";
    head.style.justifyContent = "space-between";
    head.style.gap = "8px";
    head.style.padding = "8px 10px";
    head.style.borderBottom = "1px solid rgba(255,255,255,.14)";
    head.innerHTML = "<strong style='font-size:12px;letter-spacing:.08em'>ANALYTICS DEBUG</strong>";

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.gap = "6px";

    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.textContent = "Clear";
    clearBtn.style.cssText = "border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;border-radius:8px;padding:2px 8px;cursor:pointer";
    clearBtn.addEventListener("click", () => {
      window.__dzAnalyticsLog = [];
      render();
    });

    const exportBtn = document.createElement("button");
    exportBtn.type = "button";
    exportBtn.textContent = "Export";
    exportBtn.style.cssText = "border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;border-radius:8px;padding:2px 8px;cursor:pointer";
    exportBtn.addEventListener("click", () => exportDebugLogs());

    const hideBtn = document.createElement("button");
    hideBtn.type = "button";
    hideBtn.textContent = "Hide";
    hideBtn.style.cssText = "border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);color:#fff;border-radius:8px;padding:2px 8px;cursor:pointer";
    hideBtn.addEventListener("click", () => {
      panel.style.display = "none";
      launcher.style.display = "inline-flex";
    });

    actions.appendChild(clearBtn);
    actions.appendChild(exportBtn);
    actions.appendChild(hideBtn);
    head.appendChild(actions);

    const body = document.createElement("div");
    body.style.padding = "8px 10px";
    body.style.overflow = "auto";
    body.style.maxHeight = "calc(58vh - 38px)";
    body.innerHTML = "<div>Waiting for events...</div>";

    panel.appendChild(head);
    panel.appendChild(body);
    document.body.appendChild(launcher);
    document.body.appendChild(panel);

    launcher.addEventListener("click", () => {
      const hidden = panel.style.display === "none";
      panel.style.display = hidden ? "block" : "none";
      launcher.style.display = hidden ? "none" : "inline-flex";
    });

    function render() {
      const logs = Array.isArray(window.__dzAnalyticsLog) ? window.__dzAnalyticsLog : [];
      const tail = logs.slice(-12).reverse();
      const counts = {};
      logs.forEach((r) => {
        counts[r.event] = (counts[r.event] || 0) + 1;
      });

      const countRows = Object.keys(counts)
        .sort((a, b) => counts[b] - counts[a])
        .map((k) => `<div style="display:flex;justify-content:space-between;gap:8px"><span>${k}</span><strong>${counts[k]}</strong></div>`)
        .join("");

      const eventRows = tail
        .map(
          (r) =>
            `<div style="border-top:1px dashed rgba(255,255,255,.14);padding-top:6px;margin-top:6px">
              <div><strong>${r.event}</strong> <span style="opacity:.7">${r.label || ""}</span></div>
              <div style="opacity:.7;word-break:break-all">${r.href || r.path || ""}</div>
            </div>`
        )
        .join("");

      body.innerHTML = `
        <div style="opacity:.85;margin-bottom:6px">Events total: <strong>${logs.length}</strong></div>
        <div style="display:grid;gap:4px;margin-bottom:8px">${countRows || "<div style='opacity:.7'>No events yet</div>"}</div>
        <div style="font-size:11px;opacity:.9;letter-spacing:.06em">LAST EVENTS</div>
        <div>${eventRows || "<div style='opacity:.7'>No events yet</div>"}</div>
      `;
      launcher.textContent = "A " + logs.length;
    }

    window.setInterval(render, 700);
    render();
  }

  window.DANIELOZA_ANALYTICS = {
    track(eventName, props) {
      trackEvent(eventName || "custom_event", props || {}, { force: false });
    },
    trackForced(eventName, props) {
      trackEvent(eventName || "custom_event", props || {}, { force: true });
    },
    setSampleRate(rate) {
      const n = Number(rate);
      if (Number.isNaN(n) || n < 0 || n > 1) return false;
      try {
        localStorage.setItem("dz_event_sample", String(n));
        return true;
      } catch (_) {
        return false;
      }
    },
    clearSampleRate() {
      try {
        localStorage.removeItem("dz_event_sample");
        return true;
      } catch (_) {
        return false;
      }
    },
    getSampleRate(eventName) {
      return getSampleRate(eventName || "cta_click");
    },
    getLogs() {
      return Array.isArray(window.__dzAnalyticsLog) ? [...window.__dzAnalyticsLog] : [];
    },
    clearLogs() {
      window.__dzAnalyticsLog = [];
    },
    exportLogs() {
      exportDebugLogs();
    },
    getConsent() {
      return consentState;
    },
    setConsent(nextState) {
      if (nextState !== "granted" && nextState !== "denied") return false;
      setConsentState(nextState);
      return true;
    }
  };

  function metricRating(metric, value) {
    if (metric === "LCP") {
      if (value <= 2500) return "good";
      if (value <= 4000) return "needs_improvement";
      return "poor";
    }
    if (metric === "CLS") {
      if (value <= 0.1) return "good";
      if (value <= 0.25) return "needs_improvement";
      return "poor";
    }
    if (metric === "INP") {
      if (value <= 200) return "good";
      if (value <= 500) return "needs_improvement";
      return "poor";
    }
    return "unknown";
  }

  function setupWebVitals() {
    if (!("PerformanceObserver" in window)) return () => {};

    let lcpValue = 0;
    let clsValue = 0;
    let inpValue = 0;
    let lcpObs;
    let clsObs;
    let inpObs;
    let flushed = false;

    try {
      lcpObs = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last && typeof last.startTime === "number") {
          lcpValue = Math.round(last.startTime);
        }
      });
      lcpObs.observe({ type: "largest-contentful-paint", buffered: true });
    } catch (_) {}

    try {
      clsObs = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          if (!entry.hadRecentInput) clsValue += entry.value || 0;
        });
      });
      clsObs.observe({ type: "layout-shift", buffered: true });
    } catch (_) {}

    try {
      inpObs = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          const d = Math.round(entry.duration || 0);
          if (d > inpValue) inpValue = d;
        });
      });
      inpObs.observe({ type: "event", buffered: true, durationThreshold: 40 });
    } catch (_) {}

    function flushVitals(reason) {
      if (flushed) return;
      flushed = true;

      if (lcpObs) lcpObs.disconnect();
      if (clsObs) clsObs.disconnect();
      if (inpObs) inpObs.disconnect();

      if (lcpValue > 0) {
        trackEvent("web_vital", {
          label: "LCP_" + reason,
          href: window.location.pathname + "#vitals",
          path: window.location.pathname,
          metric: "LCP",
          value: lcpValue,
          rating: metricRating("LCP", lcpValue)
        });
      }
      if (clsValue > 0) {
        const clsRounded = Number(clsValue.toFixed(4));
        trackEvent("web_vital", {
          label: "CLS_" + reason,
          href: window.location.pathname + "#vitals",
          path: window.location.pathname,
          metric: "CLS",
          value: clsRounded,
          rating: metricRating("CLS", clsRounded)
        });
      }
      if (inpValue > 0) {
        trackEvent("web_vital", {
          label: "INP_" + reason,
          href: window.location.pathname + "#vitals",
          path: window.location.pathname,
          metric: "INP",
          value: inpValue,
          rating: metricRating("INP", inpValue)
        });
      }
    }

    return flushVitals;
  }

  const flushVitals = setupWebVitals();

  function sendPageExit(reason) {
    if (exitSent) return;
    exitSent = true;
    flushVitals(reason);
    const seconds = Math.max(1, Math.round((Date.now() - pageStartMs) / 1000));
    trackEvent("page_exit", {
      label: "exit_" + reason,
      href: window.location.pathname + "#exit",
      path: window.location.pathname,
      seconds,
      max_scroll_percent: maxScrollPercent
    });
    flushServerEvents(true);
  }

  function ensureHiddenInput(form, name, value) {
    if (!form || !name) return;
    let input = form.querySelector(`input[name="${name}"]`);
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }
    input.value = value || "";
  }

  function bindAttributionFields() {
    const forms = Array.from(document.querySelectorAll("form[data-track-submit], form[data-lead-form]"));
    forms.forEach((form) => {
      ensureHiddenInput(form, "session_id", sessionId);
      ensureHiddenInput(form, "referrer", document.referrer || "");
      ensureHiddenInput(form, "landing_path", window.location.pathname);
      ensureHiddenInput(form, "utm_source", utm.utm_source || "");
      ensureHiddenInput(form, "utm_medium", utm.utm_medium || "");
      ensureHiddenInput(form, "utm_campaign", utm.utm_campaign || "");
      ensureHiddenInput(form, "utm_term", utm.utm_term || "");
      ensureHiddenInput(form, "utm_content", utm.utm_content || "");
      ensureHiddenInput(form, "website", "");
    });
  }

  function setFormStatus(form, message, ok) {
    let slot = form.querySelector("[data-form-status]");
    if (!slot) {
      slot = document.createElement("div");
      slot.setAttribute("data-form-status", "1");
      slot.style.marginTop = "8px";
      slot.style.fontSize = "13px";
      form.appendChild(slot);
    }
    slot.textContent = message;
    slot.style.opacity = "1";
    slot.style.color = ok ? "#8cffbf" : "#ffb2b2";
  }

  function bindLeadForms() {
    const forms = Array.from(document.querySelectorAll("form[data-lead-form]"));
    forms.forEach((form) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (form.dataset.submitting === "1") return;

        const fd = new FormData(form);
        const honeypot = String(fd.get("website") || "").trim();
        if (honeypot) {
          setFormStatus(form, "Dziekujemy. Odezwiemy sie wkrotce.", true);
          return;
        }

        const fields = {};
        fd.forEach((val, key) => {
          if (["session_id", "referrer", "landing_path", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "website"].includes(key)) {
            return;
          }
          fields[key] = String(val || "").slice(0, 1000);
        });

        const body = {
          form_type: form.getAttribute("data-lead-form") || "generic",
          fields,
          source_path: window.location.pathname,
          session_id: String(fd.get("session_id") || sessionId),
          consent_state: consentState,
          utm_source: String(fd.get("utm_source") || ""),
          utm_medium: String(fd.get("utm_medium") || ""),
          utm_campaign: String(fd.get("utm_campaign") || ""),
          utm_term: String(fd.get("utm_term") || ""),
          utm_content: String(fd.get("utm_content") || ""),
          referrer: String(fd.get("referrer") || document.referrer || ""),
          landing_path: String(fd.get("landing_path") || window.location.pathname),
          website: ""
        };

        form.dataset.submitting = "1";
        try {
          const res = await fetch(leadsUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
          });
          const json = await res.json().catch(() => ({}));
          if (!res.ok || json.ok !== true) {
            throw new Error(json.detail || "Blad zapisu formularza.");
          }

          setFormStatus(form, "Dziekujemy. Formularz wyslany poprawnie.", true);
          form.reset();
          bindAttributionFields();

          trackEvent("lead_submit_success", {
            label: "lead_" + body.form_type,
            href: window.location.pathname + "#lead",
            path: window.location.pathname
          });
        } catch (err) {
          setFormStatus(form, "Nie udalo sie wyslac formularza. Sprobuj ponownie.", false);
          trackEvent("lead_submit_error", {
            label: "lead_error_" + (form.getAttribute("data-lead-form") || "generic"),
            href: window.location.pathname + "#lead",
            path: window.location.pathname
          });
          if (debugAnalytics) {
            console.error(err);
          }
        } finally {
          form.dataset.submitting = "0";
        }
      });
    });
  }

  function setupMobileHeader() {
    const header = document.getElementById("hdr");
    if (!header) return;
    const nav = header.querySelector("nav");
    if (!nav || header.querySelector(".hdr-mobile-toggle")) return;

    const cta = document.createElement("a");
    cta.className = "hdr-mobile-cta";
    cta.href = "audyt.html";
    cta.textContent = "Umow audyt";
    cta.setAttribute("data-track", "cta_click");
    cta.setAttribute("data-track-label", "mobile_header_umow_audyt");

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "hdr-mobile-toggle";
    toggle.setAttribute("aria-label", "Otworz menu");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("data-track", "cta_click");
    toggle.setAttribute("data-track-label", "mobile_header_menu_toggle");
    toggle.textContent = "?";

    const backdrop = document.createElement("div");
    backdrop.className = "hdr-mobile-backdrop";

    const drawer = document.createElement("div");
    drawer.className = "hdr-mobile-drawer";
    const drawerNav = nav.cloneNode(true);
    drawer.appendChild(drawerNav);

    function closeMenu() {
      document.body.classList.remove("mobile-nav-open");
      toggle.setAttribute("aria-expanded", "false");
    }

    function toggleMenu() {
      const isOpen = document.body.classList.toggle("mobile-nav-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    }

    toggle.addEventListener("click", toggleMenu);
    backdrop.addEventListener("click", closeMenu);
    drawer.addEventListener("click", (e) => {
      if (e.target.closest("a")) closeMenu();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeMenu();
    });

    header.appendChild(cta);
    header.appendChild(toggle);
    document.body.appendChild(backdrop);
    document.body.appendChild(drawer);
  }

  function setupHomeHubFilters() {
    const tabs = Array.from(document.querySelectorAll(".homeHubTab[data-filter]"));
    const cards = Array.from(document.querySelectorAll(".homeMini[data-kind]"));
    if (!tabs.length || !cards.length) return;

    function applyFilter(filter) {
      tabs.forEach((tab) => tab.setAttribute("aria-pressed", String(tab.dataset.filter === filter)));
      cards.forEach((card) => {
        const kind = String(card.dataset.kind || "").toLowerCase();
        const favorite = card.dataset.favorite === "1";
        const visible = filter === "all" || kind === filter || (filter === "favorites" && favorite);
        card.hidden = !visible;
      });
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => applyFilter(tab.dataset.filter || "all"));
    });

    const defaultTab = tabs.find((tab) => tab.getAttribute("aria-pressed") === "true");
    applyFilter((defaultTab && defaultTab.dataset.filter) || "all");
  }

  function setupHomeWowPack() {
    if (!document.body.classList.contains("page-home")) return;
    const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const reveals = Array.from(document.querySelectorAll(".wow-reveal"));
    if (reveals.length) {
      if ("IntersectionObserver" in window && !reduceMotion) {
        const revealObserver = new IntersectionObserver(
          (entries, observer) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            });
          },
          { threshold: 0.22 }
        );
        reveals.forEach((el) => revealObserver.observe(el));
      } else {
        reveals.forEach((el) => el.classList.add("is-visible"));
      }
    }

    const counters = Array.from(document.querySelectorAll("[data-count-to]"));
    if (counters.length) {
      const runCounter = (el) => {
        const to = Number(el.getAttribute("data-count-to") || "0");
        if (!Number.isFinite(to) || to <= 0) return;
        const duration = reduceMotion ? 10 : 1200;
        const startedAt = performance.now();

        const tick = (now) => {
          const p = Math.min(1, (now - startedAt) / duration);
          const eased = 1 - Math.pow(1 - p, 3);
          el.textContent = String(Math.round(to * eased));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      };

      if ("IntersectionObserver" in window && !reduceMotion) {
        const counterObs = new IntersectionObserver(
          (entries, observer) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting || entry.target.dataset.counted === "1") return;
              entry.target.dataset.counted = "1";
              runCounter(entry.target);
              observer.unobserve(entry.target);
            });
          },
          { threshold: 0.5 }
        );
        counters.forEach((el) => counterObs.observe(el));
      } else {
        counters.forEach((el) => runCounter(el));
      }
    }

    const compareBox = document.getElementById("compareBox");
    const compareRange = document.getElementById("compareRange");
    if (compareBox && compareRange) {
      const updateSplit = () => {
        const value = Math.max(0, Math.min(100, Number(compareRange.value || 50)));
        compareBox.style.setProperty("--split", value + "%");
      };
      compareRange.addEventListener("input", updateSplit);
      updateSplit();
    }

    const hero = document.getElementById("hero");
    const mesh = hero ? hero.querySelector(".hero-mesh") : null;
    if (hero && mesh && !reduceMotion) {
      hero.addEventListener("pointermove", (e) => {
        const rect = hero.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * 56;
        const y = ((e.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * 42;
        mesh.style.setProperty("--mx", `${x.toFixed(1)}px`);
        mesh.style.setProperty("--my", `${y.toFixed(1)}px`);
      });
      hero.addEventListener("pointerleave", () => {
        mesh.style.setProperty("--mx", "0px");
        mesh.style.setProperty("--my", "0px");
      });
    }

    const finePointer = window.matchMedia && window.matchMedia("(pointer:fine)").matches;
    if (finePointer && !reduceMotion) {
      const halo = document.createElement("div");
      halo.className = "cursor-halo";
      document.body.appendChild(halo);

      window.addEventListener(
        "pointermove",
        (e) => {
          halo.style.transform = `translate(${Math.round(e.clientX)}px, ${Math.round(e.clientY)}px) translate(-50%, -50%)`;
        },
        { passive: true }
      );
    }
  }

  function setupClientWowRollout() {
    const clientPages = [
      "page-oferta",
      "page-portfolio",
      "page-cases",
      "page-kontakt",
      "page-o-mnie",
      "page-audyt",
      "page-faq"
    ];
    const isClientPage = clientPages.some((cls) => document.body.classList.contains(cls));
    if (!isClientPage) return;

    const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.body.classList.add("client-wow");
    const pageVariant = clientPages.find((cls) => document.body.classList.contains(cls)) || "client-default";
    document.body.setAttribute("data-client-variant", pageVariant);

    const revealTargets = Array.from(
      document.querySelectorAll(
        "main section, main article, .panel, .plan, .case-card, .contact-card, .audit-card, .tool-card, .faq-item"
      )
    ).filter((el) => !el.classList.contains("wow-reveal"));
    revealTargets.forEach((el) => el.classList.add("wow-reveal"));
    revealTargets.forEach((el, i) => el.style.setProperty("--wow-delay", `${Math.min(i, 10) * 55}ms`));

    const reveals = Array.from(document.querySelectorAll(".wow-reveal"));
    if (reveals.length) {
      if ("IntersectionObserver" in window && !reduceMotion) {
        const revealObserver = new IntersectionObserver(
          (entries, observer) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            });
          },
          { threshold: 0.16 }
        );
        reveals.forEach((el) => revealObserver.observe(el));
      } else {
        reveals.forEach((el) => el.classList.add("is-visible"));
      }
    }

    const metricNodes = Array.from(document.querySelectorAll(".kpi strong, .kpi-card strong"));
    const runMetric = (el) => {
      if (!el || el.dataset.counted === "1") return;
      const raw = (el.textContent || "").trim();
      const m = raw.match(/^([+-]?\d+(?:[.,]\d+)?)(.*)$/);
      if (!m) return;
      const num = Number(m[1].replace(",", "."));
      if (!Number.isFinite(num)) return;
      const suffix = m[2] || "";
      const decimals = m[1].includes(",") || m[1].includes(".") ? 1 : 0;
      const duration = reduceMotion ? 10 : 950;
      const startedAt = performance.now();
      el.dataset.counted = "1";

      const tick = (now) => {
        const p = Math.min(1, (now - startedAt) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        const value = num * eased;
        const rounded = decimals ? value.toFixed(decimals) : String(Math.round(value));
        el.textContent = rounded.replace(".", ",") + suffix;
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };

    if (metricNodes.length) {
      if ("IntersectionObserver" in window && !reduceMotion) {
        const metricObserver = new IntersectionObserver(
          (entries, observer) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              runMetric(entry.target);
              observer.unobserve(entry.target);
            });
          },
          { threshold: 0.42 }
        );
        metricNodes.forEach((el) => metricObserver.observe(el));
      } else {
        metricNodes.forEach((el) => runMetric(el));
      }
    }

    const flyByPage = {
      "page-oferta": [
        { href: "audyt.html", text: "Zamow audyt", track: "client_fly_oferta_audyt", primary: true },
        { href: "kontakt.html?topic=oferta", text: "Dobierz pakiet", track: "client_fly_oferta_pakiet" }
      ],
      "page-portfolio": [
        { href: "case-studies.html", text: "Zobacz wyniki", track: "client_fly_portfolio_cases", primary: true },
        { href: "kontakt.html?topic=portfolio", text: "Porozmawiajmy", track: "client_fly_portfolio_kontakt" }
      ],
      "page-cases": [
        { href: "audyt.html", text: "Policzmy ROI", track: "client_fly_cases_roi", primary: true },
        { href: "kontakt.html?topic=wdrozenie", text: "Start wdrozenia", track: "client_fly_cases_start" }
      ],
      "page-kontakt": [
        { href: "booking.html", text: "Rezerwuj slot", track: "client_fly_kontakt_slot", primary: true },
        { href: "audyt.html", text: "Szybki audyt", track: "client_fly_kontakt_audyt" }
      ],
      "page-o-mnie": [
        { href: "demo.html", text: "Zobacz demo", track: "client_fly_omnie_demo", primary: true },
        { href: "kontakt.html", text: "Napisz do mnie", track: "client_fly_omnie_kontakt" }
      ],
      "page-audyt": [
        { href: "kontakt.html?topic=audyt", text: "Wyslij brief", track: "client_fly_audyt_brief", primary: true },
        { href: "oferta.html", text: "Zobacz oferte", track: "client_fly_audyt_oferta" }
      ],
      "page-faq": [
        { href: "kontakt.html", text: "Masz pytanie?", track: "client_fly_faq_kontakt", primary: true },
        { href: "audyt.html", text: "Przejdz do audytu", track: "client_fly_faq_audyt" }
      ]
    };
    const flyItems = flyByPage[pageVariant] || [
      { href: "audyt.html", text: "Umow audyt", track: "client_fly_default_audyt", primary: true },
      { href: "kontakt.html", text: "Kontakt", track: "client_fly_default_kontakt" }
    ];

    let fly = document.querySelector(".client-fly-cta");
    if (!fly) {
      fly = document.createElement("div");
      fly.className = "client-fly-cta";
      document.body.appendChild(fly);
    }
    fly.innerHTML = flyItems
      .map(
        (item) =>
          `<a class="client-fly-btn${item.primary ? " primary" : ""}" href="${item.href}" data-track="cta_click" data-track-label="${item.track}">${item.text}</a>`
      )
      .join("");

    const microByPage = {
      "page-oferta": ".plan.best,.pricing-top h1,.billing-toggle",
      "page-portfolio": ".hub-hero,.case-card:first-child .kpi,.case-card:first-child .kpi strong",
      "page-cases": ".rev-hero,.kpi-card,.final-cta",
      "page-kontakt": ".contact-card h2,.contact-actions .btn:first-child",
      "page-o-mnie": "#aboutText,.panel .btn:first-of-type",
      "page-audyt": ".audit-hero h1,.audit-actions .btn:first-child",
      "page-faq": ".faq-item:first-child,.faq-item:nth-child(2),.faq-wrap .btn:first-child"
    };
    const microTargets = Array.from(document.querySelectorAll(microByPage[pageVariant] || ""));
    microTargets.forEach((el, i) => {
      el.classList.add("wow-micro");
      el.style.setProperty("--micro-delay", `${i * 130}ms`);
    });

    if (!reduceMotion) {
      window.addEventListener(
        "pointermove",
        (e) => {
          document.body.style.setProperty("--spot-x", `${e.clientX}px`);
          document.body.style.setProperty("--spot-y", `${e.clientY}px`);
        },
        { passive: true }
      );
    }
  }

  function setupClientCopyBoost() {
    const pageVariant = document.body.getAttribute("data-client-variant") || "";
    if (!pageVariant) return;
    const copyVariant = (new URLSearchParams(window.location.search).get("copy") || "v1").toLowerCase();

    const copyMapV1 = {
      "page-oferta": {
        text: [
          [".pricing-top h1", "Pakiety, ktore zamieniaja content w leady"],
          [".pricing-top p", "Wybierz plan pod tempo wzrostu. Startujesz szybko, testujesz szybko, skalujesz bez chaosu."]
        ],
        cta: [
          [".plan.best .cta", "Uruchom plan PRO"],
          [".plan[data-plan='starter'] .cta", "Startuj od audytu"]
        ]
      },
      "page-portfolio": {
        text: [
          [".hub-hero h1", "Portfolio, ktore pokazuje wynik, nie obietnice"],
          [".hub-hero p", "Kazdy case to konkret: problem, decyzja, wynik i rola. Tak wyglada delivery pod klienta."]
        ],
        cta: [
          ["a[data-track-label='portfolio_case1_umow_audyt']", "Przejdz do audytu"],
          ["a[data-track-label='portfolio_case1_zobacz_demo']", "Otworz demo"]
        ]
      },
      "page-cases": {
        text: [
          [".rev-hero h1", "Case studies, ktore domykaja decyzje"],
          [".rev-hero p", "Pokazujemy jak przejsc od ruchu do zapytan: metryki, plan 30 dni i konkretne nastepne kroki."]
        ],
        cta: [
          ["a[data-track-label='cases_hero_audyt']", "Start: audyt i plan"],
          ["a[data-track-label='cases_hero_roi']", "Policz potencjal ROI"]
        ]
      },
      "page-kontakt": {
        text: [
          [".page-hero h1", "Napisz i dostan plan wdrozenia tego samego dnia"],
          [".page-hero .note", "Jeden brief i od razu decyzja: co robimy teraz, co testujemy i jak mierzymy efekt."]
        ],
        cta: [
          ["button[data-track-label='kontakt_wyslij_brief']", "Wyslij brief teraz"],
          ["a[data-track-label='kontakt_umow_audyt']", "Najpierw audyt"]
        ]
      },
      "page-o-mnie": {
        text: [
          ["main .panel h1", "Buduje content AI, ktory robi wynik"],
          ["#aboutText", "Lacze kreatywe z egzekucja: od strategii i scenariusza po gotowe materialy i iteracje na danych."]
        ],
        cta: [
          ["a.btn[href='demo.html']", "Zobacz jak pracuje"],
          ["a.btn.secondary[href='kontakt.html']", "Porozmawiajmy o projekcie"]
        ]
      },
      "page-audyt": {
        text: [
          [".audit-hero h1", "Audyt, po ktorym od razu wiesz co robic"],
          [".audit-hero p", "Bez ogolnikow. Dostajesz konkretne priorytety, plan 7 dni i sciezke do pierwszych testow."]
        ],
        cta: [
          ["button[data-track-label='audyt_wyslij_zgloszenie']", "Wyslij i odbierz plan"],
          ["a[data-track-label='audyt_zobacz_demo']", "Najpierw zobacz demo"]
        ]
      },
      "page-faq": {
        text: [
          ["main .panel h1", "FAQ przed startem wspolpracy"],
          ["main .panel .note", "Krotko: czas, zakres, proces i to, czego potrzebujemy od Ciebie na start."]
        ],
        cta: [
          ["a.btn[href='demo.html']", "Przejdz do demo"],
          ["a.btn.secondary[href='kontakt.html']", "Skontaktuj sie teraz"]
        ]
      }
    };

    const copyMapV2 = {
      "page-oferta": {
        text: [
          [".pricing-top h1", "Wybierz plan i uruchom kampanie jeszcze dzis"],
          [".pricing-top p", "Bez przeciagania. Dobieramy pakiet pod cel i od razu przechodzimy do produkcji."]
        ],
        cta: [
          [".plan.best .cta", "Biorę plan PRO"],
          [".plan[data-plan='starter'] .cta", "Start od Startera"]
        ]
      },
      "page-portfolio": {
        text: [
          [".hub-hero h1", "Sprawdz jak dowozimy rezultat krok po kroku"],
          [".hub-hero p", "Tu widzisz realne wdrozenia i role. Bez slajdow, tylko konkretne wykonanie."]
        ],
        cta: [
          ["a[data-track-label='portfolio_case1_umow_audyt']", "Przejdzmy do Twojego case"],
          ["a[data-track-label='portfolio_case1_zobacz_demo']", "Uruchom demo live"]
        ]
      },
      "page-cases": {
        text: [
          [".rev-hero h1", "Te case studies odpowiadaja na pytanie: czy to sie zwroci?"],
          [".rev-hero p", "Masz liczby, model ROI i gotowy plan wdrozenia. Mozesz podjac decyzje od razu."]
        ],
        cta: [
          ["a[data-track-label='cases_hero_audyt']", "Zaczynamy od audytu"],
          ["a[data-track-label='cases_hero_roi']", "Sprawdz ROI teraz"]
        ]
      },
      "page-kontakt": {
        text: [
          [".page-hero h1", "Wyslij brief i ruszamy z planem wdrozenia"],
          [".page-hero .note", "Jedna wiadomosc wystarczy, zeby przejsc do konkretnego planu i pierwszych krokow."]
        ],
        cta: [
          ["button[data-track-label='kontakt_wyslij_brief']", "Wyslij brief i start"],
          ["a[data-track-label='kontakt_umow_audyt']", "Umow konsultacje"]
        ]
      },
      "page-o-mnie": {
        text: [
          ["main .panel h1", "Tworze AI content, ktory sprzedaje i buduje marke"],
          ["#aboutText", "Projektuje i wdrazam short-form od pomyslu do wyniku, z naciskiem na szybkie testy i wzrost leadow."]
        ],
        cta: [
          ["a.btn[href='demo.html']", "Pokaz mi demo"],
          ["a.btn.secondary[href='kontakt.html']", "Napisz i dzialamy"]
        ]
      },
      "page-audyt": {
        text: [
          [".audit-hero h1", "Audyt, ktory od razu przeklada sie na dzialanie"],
          [".audit-hero p", "Po audycie wiesz co publikowac, jak testowac i jak domykac zapytania."]
        ],
        cta: [
          ["button[data-track-label='audyt_wyslij_zgloszenie']", "Zamawiam audyt"],
          ["a[data-track-label='audyt_zobacz_demo']", "Najpierw chce demo"]
        ]
      },
      "page-faq": {
        text: [
          ["main .panel h1", "FAQ: wszystko przed startem wspolpracy"],
          ["main .panel .note", "Najwazniejsze odpowiedzi, zebys mogl szybko podjac decyzje i ruszyc."]
        ],
        cta: [
          ["a.btn[href='demo.html']", "Pokaz demo"],
          ["a.btn.secondary[href='kontakt.html']", "Skontaktujmy sie"]
        ]
      }
    };

    const selectedMap = copyVariant === "v2" ? copyMapV2 : copyMapV1;
    document.body.setAttribute("data-copy-variant", copyVariant === "v2" ? "v2" : "v1");
    const cfg = selectedMap[pageVariant] || copyMapV1[pageVariant];
    if (!cfg) return;

    (cfg.text || []).forEach(([selector, value]) => {
      const el = document.querySelector(selector);
      if (!el || !value) return;
      el.textContent = value;
    });
    (cfg.cta || []).forEach(([selector, value]) => {
      const el = document.querySelector(selector);
      if (!el || !value) return;
      el.textContent = value;
    });
  }

  function setupLabLoadingIntro() {
    const isLabPage =
      document.body.classList.contains("studio-page") ||
      document.body.classList.contains("kling-page") ||
      document.body.classList.contains("seedance-page");
    if (!isLabPage) return;
    if (document.getElementById("demoIntro")) return;

    const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const saveData = !!(navigator.connection && navigator.connection.saveData);
    const file = (window.location.pathname.split("/").pop() || "index.html").toLowerCase();

    const titleByFile = {
      "kling.html": "KLING LAB",
      "gemini.html": "GEMINI LAB",
      "seedance-1-5-pro.html": "SEEDANCE LAB",
      "seedream-4-0.html": "SEEDREAM 4.0",
      "seedream-4-5.html": "SEEDREAM 4.5",
      "demo.html": "DEMO LAB"
    };
    const subtitleByFile = {
      "kling.html": "Ladowanie stage, slotow i kolejki generacji.",
      "gemini.html": "Ladowanie panelu chat, modeli i historii.",
      "seedance-1-5-pro.html": "Ladowanie workflow video i kontroli batch.",
      "seedream-4-0.html": "Ladowanie workflow image i presetow stylu.",
      "seedream-4-5.html": "Ladowanie workflow image i panelu wariantow.",
      "demo.html": "Ladowanie narzedzi testowych i promptow."
    };

    const title = titleByFile[file] || "LAB";
    const subtitle = subtitleByFile[file] || "Ladowanie srodowiska kreatywnego.";
    const seenKey = `dz_lab_intro_seen_${file}`;
    let seen = false;
    try {
      seen = localStorage.getItem(seenKey) === "1";
    } catch (_) {}
    const duration = reduceMotion || saveData || seen ? 220 : 1700;

    const intro = document.createElement("div");
    intro.className = "labIntro";
    intro.innerHTML = `
      <div class="labIntroCard">
        <h2 class="labIntroTitle">${title}</h2>
        <p class="labIntroSub">${subtitle}</p>
        <div class="labIntroBar"><div class="labIntroFill"></div></div>
        <button class="labIntroSkip" type="button">Pomin</button>
      </div>
    `;
    document.body.appendChild(intro);
    document.body.classList.add("lab-intro-running");

    const closeIntro = () => {
      intro.classList.add("is-off");
      document.body.classList.remove("lab-intro-running");
      try {
        localStorage.setItem(seenKey, "1");
      } catch (_) {}
      window.setTimeout(() => intro.remove(), 420);
    };

    const skip = intro.querySelector(".labIntroSkip");
    if (skip) skip.addEventListener("click", closeIntro);
    intro.addEventListener("click", (e) => {
      if (e.target === intro) closeIntro();
    });
    window.setTimeout(closeIntro, duration);
  }

  function setupLabThemeSync() {
    const isLabPage =
      document.body.classList.contains("studio-page") ||
      document.body.classList.contains("kling-page") ||
      document.body.classList.contains("seedance-page");
    if (!isLabPage) return;

    document.body.classList.add("lab-theme-sync");
    if (document.body.classList.contains("accent-purple")) document.body.classList.add("lab-tone-purple");
    else if (document.body.classList.contains("accent-teal")) document.body.classList.add("lab-tone-teal");
    else if (document.body.classList.contains("kling-page")) document.body.classList.add("lab-tone-cyan");
    else if (document.body.classList.contains("seedance-page")) document.body.classList.add("lab-tone-violet");
    else document.body.classList.add("lab-tone-cyan");

    const params = new URLSearchParams(window.location.search);
    const fromUrl = (params.get("glow") || "").toLowerCase();
    const allowed = ["low", "mid", "high"];
    let level = allowed.includes(fromUrl) ? fromUrl : "";
    if (!level) {
      try {
        const stored = (localStorage.getItem("dz_lab_glow_level") || "").toLowerCase();
        if (allowed.includes(stored)) level = stored;
      } catch (_) {}
    }
    if (!level) level = "mid";
    try {
      localStorage.setItem("dz_lab_glow_level", level);
    } catch (_) {}

    document.body.classList.remove("lab-glow-low", "lab-glow-mid", "lab-glow-high");
    document.body.classList.add(`lab-glow-${level}`);
    document.body.setAttribute("data-lab-glow", level);
  }

  function setupHardLockLabTopbar() {
    const file = (window.location.pathname.split("/").pop() || "").toLowerCase();
    const targets = new Set([
      "gemini.html",
      "seedream-4-0.html",
      "seedream-4-5.html",
      "seedance-1-5-pro.html",
      "kling.html"
    ]);
    if (!targets.has(file)) return;

    const topbar = document.querySelector(".studioTopbar, .klingTopbar, .geminiTopbar");
    if (!topbar || !topbar.parentElement) return;

    let spacer = topbar.previousElementSibling;
    if (!spacer || !spacer.classList.contains("labTopbarSpacer")) {
      spacer = document.createElement("div");
      spacer.className = "labTopbarSpacer";
      topbar.parentElement.insertBefore(spacer, topbar);
    }

    function readHeaderOffset() {
      const raw = getComputedStyle(document.documentElement).getPropertyValue("--header-h").trim();
      const n = Number.parseFloat(raw.replace("px", ""));
      const header = Number.isFinite(n) ? n : 72;
      return header + 6;
    }

    function clearLock() {
      spacer.style.height = "0px";
      topbar.style.removeProperty("position");
      topbar.style.removeProperty("top");
      topbar.style.removeProperty("left");
      topbar.style.removeProperty("width");
      topbar.style.removeProperty("z-index");
      topbar.style.removeProperty("margin");
    }

    function applyLock() {
      if (window.innerWidth <= 980) {
        clearLock();
        return;
      }
      const rect = spacer.getBoundingClientRect();
      const h = topbar.offsetHeight || 0;
      spacer.style.height = `${h}px`;
      topbar.style.setProperty("position", "fixed", "important");
      topbar.style.setProperty("top", `${readHeaderOffset()}px`, "important");
      topbar.style.setProperty("left", `${Math.round(rect.left)}px`, "important");
      topbar.style.setProperty("width", `${Math.round(rect.width)}px`, "important");
      topbar.style.setProperty("z-index", "60", "important");
      topbar.style.setProperty("margin", "0", "important");
    }

    let resizeTimer = 0;
    function onResize() {
      if (resizeTimer) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(applyLock, 60);
    }

    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", applyLock);
    window.setTimeout(applyLock, 0);
    window.setTimeout(applyLock, 220);
  }

  function sanitizeSocialLinks() {
    document.querySelectorAll('a.socialbtn[href="https://www.facebook.com/"]').forEach((el) => el.remove());
  }
  // year
  const y = document.getElementById("y");
  if (y) y.textContent = new Date().getFullYear();
  bindAttributionFields();
  bindLeadForms();
  setupDebugPanel();
  setupMobileHeader();
  setupHomeHubFilters();
  setupHomeWowPack();
  setupClientWowRollout();
  setupClientCopyBoost();
  setupLabLoadingIntro();
  setupLabThemeSync();
  setupHardLockLabTopbar();
  sanitizeSocialLinks();

  // fade-in
  window.addEventListener("load", () => {
    document.body.classList.add("loaded");
    setupConsentBanner();
  });

  const hdr = document.getElementById("hdr");
  const hero = document.getElementById("hero");

  const onScroll = () => {
    const yPos = window.scrollY;

    if (hdr) {
      if (yPos > 10) hdr.classList.add("show");
      else hdr.classList.remove("show");
    }

    if (hero) {
      const h = hero.offsetHeight * 0.28;
      if (yPos > h) hero.classList.add("shrink");
      else hero.classList.remove("shrink");
    }
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // bg video rotate only when network and device conditions are good
  const v1 = document.getElementById("bg1");
  const v2 = document.getElementById("bg2");
  const saveData = !!(navigator.connection && navigator.connection.saveData);
  const reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const smallScreen = !!(window.matchMedia && window.matchMedia("(max-width: 900px)").matches);

  if (v1 && v2) {
    if (saveData || reduceMotion || smallScreen) {
      v2.remove();
    } else {
      let showFirst = true;
      window.setInterval(() => {
        showFirst = !showFirst;
        if (!showFirst) v2.setAttribute("preload", "metadata");
        v1.style.display = showFirst ? "block" : "none";
        v2.style.display = showFirst ? "none" : "block";
      }, 8000);
    }
  }

  // Page view (manual, to keep payload shape consistent)
  trackEvent("page_view", {
    label: document.title || "page_view",
    href: window.location.href,
    path: window.location.pathname
  });

  // Engagement milestones
  [15, 30, 60].forEach((sec) => {
    window.setTimeout(() => {
      if (document.hidden) return;
      trackEvent("engaged_time", {
        label: "engaged_" + sec,
        href: window.location.pathname + "#engaged",
        path: window.location.pathname,
        seconds: sec,
        max_scroll_percent: maxScrollPercent
      });
    }, sec * 1000);
  });

  function getTextLabel(el) {
    if (!el) return "";
    const aria = el.getAttribute("aria-label") || "";
    const title = el.getAttribute("title") || "";
    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    return (aria || title || text || "").slice(0, 100);
  }

  function getTargetFromElement(el) {
    if (!el) return "";
    const href = el.getAttribute("href");
    if (href) return href;
    const ctaTarget = el.getAttribute("data-cta-target");
    if (ctaTarget) return ctaTarget;

    const onclick = el.getAttribute("onclick") || "";
    const m = onclick.match(/location\.href=['"]([^'"]+)['"]/i);
    return m ? m[1] : "";
  }

  function inferCtaArea(el) {
    if (!el) return "unknown";
    const rules = [
      ["header", "header_nav"],
      [".hero", "hero"],
      [".homeHub", "home_hub"],
      [".mobileCtaBar", "mobile_cta_bar"],
      [".sdSide", "studio_sidebar"],
      ["main", "main_content"],
      ["footer", "footer"]
    ];
    const found = rules.find(([sel]) => el.closest(sel));
    return found ? found[1] : "unknown";
  }

  function inferCtaKind(el) {
    if (!el) return "generic";
    if (el.closest("header nav")) return "nav_link";
    if (el.classList.contains("socialbtn")) return "social_link";
    if (el.matches("button[type='submit'],input[type='submit']")) return "form_submit_control";
    if (el.classList.contains("btn") || el.classList.contains("homeBtn") || el.classList.contains("mobileCtaBarBtn")) {
      return "button_like";
    }
    if (el.tagName === "A") return "link";
    if (el.tagName === "BUTTON") return "button";
    return "generic";
  }

  // CTA tracking (buttons/links with data-track)
  document.addEventListener("click", (e) => {
    const tracked = e.target.closest("[data-track]");
    let target = tracked;

    if (!target) {
      target =
        e.target.closest(".socialbtn") ||
        e.target.closest("header nav a") ||
        e.target.closest(".btn") ||
        e.target.closest(".homeBtn") ||
        e.target.closest(".mobileCtaBarBtn") ||
        e.target.closest("a[href]") ||
        e.target.closest("button") ||
        e.target.closest("[role='button']");
    }
    if (!target) return;
    if (target.matches("button:disabled,[aria-disabled='true']")) return;

    const isSubmitControl = target.matches("button[type='submit'],input[type='submit']");
    if (isSubmitControl && target.closest("form[data-track-submit]")) return;

    const eventName = target.getAttribute("data-track") || "cta_click";
    const textLabel = getTextLabel(target);
    const href = getTargetFromElement(target);
    const label =
      target.getAttribute("data-track-label") ||
      textLabel ||
      href ||
      "cta";

    const ctaArea = inferCtaArea(target);
    const ctaKind = inferCtaKind(target);
    const ctaId = target.id || "";
    const ctaClass = (target.className || "").toString().replace(/\s+/g, " ").trim().slice(0, 120);
    const isAnchor = target.tagName === "A" && !!target.href;
    const isOutbound = isAnchor && target.origin !== window.location.origin;

    trackEvent(eventName, {
      label,
      href,
      path: window.location.pathname,
      page_type: pageType,
      cta_area: ctaArea,
      cta_kind: ctaKind,
      cta_id: ctaId,
      cta_class: ctaClass,
      cta_text: textLabel,
      cta_tag: target.tagName.toLowerCase()
    });

    if (isOutbound) {
      trackEvent("outbound_click", {
        label,
        href: target.href,
        path: window.location.pathname,
        page_type: pageType,
        cta_area: ctaArea,
        cta_kind: ctaKind
      });
    }
  });

  // Form submit tracking (works also for submit via Enter key)
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("form[data-track-submit]");
    if (!form) return;

    const eventName = form.getAttribute("data-track-submit") || "form_submit";
    const label = form.getAttribute("data-track-submit-label") || form.getAttribute("class") || "form_submit";
    const formFields = form.querySelectorAll("input,select,textarea").length;
    const formAction = form.getAttribute("action") || "";
    const formMethod = (form.getAttribute("method") || "get").toLowerCase();
    const formName = form.getAttribute("data-lead-form") || form.getAttribute("name") || form.id || "form";

    trackEvent(eventName, {
      label,
      href: window.location.pathname + "#form",
      path: window.location.pathname,
      page_type: pageType,
      form_name: formName,
      form_method: formMethod,
      form_action: formAction,
      form_field_count: formFields
    });
  });

  // Scroll-depth milestones (once per page)
  const milestones = [25, 50, 75, 90];
  const fired = {};
  function checkScrollDepth() {
    const doc = document.documentElement;
    const max = Math.max(1, doc.scrollHeight - window.innerHeight);
    const pct = Math.round((window.scrollY / max) * 100);
    if (pct > maxScrollPercent) maxScrollPercent = pct;
    milestones.forEach((m) => {
      if (fired[m] || pct < m) return;
      fired[m] = true;
      trackEvent("scroll_depth", {
        label: "scroll_" + m,
        href: window.location.pathname + "#scroll",
        path: window.location.pathname,
        percent: m
      });
    });
  }
  window.addEventListener("scroll", checkScrollDepth, { passive: true });
  checkScrollDepth();

  window.addEventListener("pagehide", () => sendPageExit("pagehide"));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") sendPageExit("hidden");
  });
})();


