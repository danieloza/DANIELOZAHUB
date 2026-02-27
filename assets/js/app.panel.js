(function () {
  "use strict";

  var TOKEN_KEY = "mvp_auth_token";
  var API_BASE_KEY = "mvp_api_base";
  var SESSION_ID_KEY = "mvp_session_id";
  var ONBOARDING_KEY = "mvp_onboarding_state";
  var SUCCEEDED_JOB_IDS_KEY = "mvp_succeeded_job_ids";
  var token = localStorage.getItem(TOKEN_KEY) || "";
  var pollTimer = null;
  var sessionId = localStorage.getItem(SESSION_ID_KEY) || ("sid-" + Math.random().toString(36).slice(2) + Date.now());
  var onboarding = loadOnboardingState();
  var seenSucceededJobIds = loadSucceededJobIds();
  var lastJobsRows = [];
  var lastLedgerRows = [];
  var checkoutSuccessTracked = false;
  localStorage.setItem(SESSION_ID_KEY, sessionId);

  var el = {
    status: document.getElementById("status"),
    apiBase: document.getElementById("apiBase"),
    saveApiBase: document.getElementById("saveApiBase"),
    registerForm: document.getElementById("registerForm"),
    loginForm: document.getElementById("loginForm"),
    logoutBtn: document.getElementById("logoutBtn"),
    refreshBtn: document.getElementById("refreshBtn"),
    accountBox: document.getElementById("accountBox"),
    authBox: document.getElementById("authBox"),
    meEmail: document.getElementById("meEmail"),
    meUserId: document.getElementById("meUserId"),
    balance: document.getElementById("balance"),
    topupForm: document.getElementById("topupForm"),
    createJobForm: document.getElementById("createJobForm"),
    jobsBody: document.getElementById("jobsBody"),
    ledgerBody: document.getElementById("ledgerBody"),
    onboardingBox: document.getElementById("onboardingBox"),
    onboardingNote: document.getElementById("onboardingNote"),
    obRegistered: document.getElementById("obRegistered"),
    obCheckoutStarted: document.getElementById("obCheckoutStarted"),
    obCheckoutSuccess: document.getElementById("obCheckoutSuccess"),
    obJobCreated: document.getElementById("obJobCreated"),
    obJobSucceeded: document.getElementById("obJobSucceeded")
  };

  function inferApiBase() {
    var saved = localStorage.getItem(API_BASE_KEY);
    if (saved) return saved;
    if (location.hostname.indexOf("onrender.com") !== -1) {
      return location.origin;
    }
    return "http://127.0.0.1:8000";
  }

  function defaultOnboardingState() {
    return {
      registered: false,
      checkout_started: false,
      checkout_success: false,
      first_job_created: false,
      first_job_succeeded: false
    };
  }

  function loadOnboardingState() {
    try {
      var raw = localStorage.getItem(ONBOARDING_KEY);
      if (!raw) return defaultOnboardingState();
      var parsed = JSON.parse(raw);
      return Object.assign(defaultOnboardingState(), parsed || {});
    } catch (err) {
      return defaultOnboardingState();
    }
  }

  function saveOnboardingState() {
    localStorage.setItem(ONBOARDING_KEY, JSON.stringify(onboarding));
  }

  function loadSucceededJobIds() {
    try {
      var raw = localStorage.getItem(SUCCEEDED_JOB_IDS_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function saveSucceededJobIds() {
    var keys = Object.keys(seenSucceededJobIds || {});
    if (keys.length > 200) {
      keys.slice(0, keys.length - 200).forEach(function (k) { delete seenSucceededJobIds[k]; });
    }
    localStorage.setItem(SUCCEEDED_JOB_IDS_KEY, JSON.stringify(seenSucceededJobIds));
  }

  function setStatus(text, kind) {
    el.status.textContent = text;
    el.status.className = "status " + (kind || "info");
  }

  function setToken(next) {
    token = next || "";
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  function getApiBase() {
    return (el.apiBase.value || "").trim().replace(/\/+$/, "");
  }

  function markOnboarding(key, done) {
    if (!onboarding || !Object.prototype.hasOwnProperty.call(onboarding, key)) return;
    onboarding[key] = Boolean(done);
    saveOnboardingState();
    renderOnboarding();
  }

  function renderOnboarding() {
    if (!el.onboardingBox) return;
    var loggedIn = Boolean(token);
    el.onboardingBox.style.display = loggedIn ? "block" : "none";
    if (!loggedIn) return;

    function paint(node, done) {
      if (!node) return;
      node.className = "onboarding-item " + (done ? "done" : "pending");
    }

    paint(el.obRegistered, onboarding.registered);
    paint(el.obCheckoutStarted, onboarding.checkout_started);
    paint(el.obCheckoutSuccess, onboarding.checkout_success);
    paint(el.obJobCreated, onboarding.first_job_created);
    paint(el.obJobSucceeded, onboarding.first_job_succeeded);

    var doneCount = 0;
    ["registered", "checkout_started", "checkout_success", "first_job_created", "first_job_succeeded"].forEach(function (k) {
      if (onboarding[k]) doneCount += 1;
    });
    el.onboardingNote.textContent = "Postep onboardingu: " + doneCount + "/5";
  }

  function detectOnboardingFromData() {
    if (!token) return;
    markOnboarding("registered", true);
    if ((lastLedgerRows || []).some(function (row) { return row && row.entry_type === "topup"; })) {
      markOnboarding("checkout_started", true);
      markOnboarding("checkout_success", true);
    }
    if ((lastJobsRows || []).length > 0) {
      markOnboarding("first_job_created", true);
    }
    if ((lastJobsRows || []).some(function (row) { return row && row.status === "succeeded"; })) {
      markOnboarding("first_job_succeeded", true);
    }
  }

  async function trackEvent(eventName, label, payload) {
    try {
      var base = getApiBase();
      if (!base) return;
      await Promise.race([
        fetch(base + "/api/analytics/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            events: [{
              event_name: eventName,
              label: label || "app_panel",
              path: location.pathname,
              href: location.href,
              session_id: sessionId,
              consent_state: "unknown",
              payload: Object.assign({ source: "app_panel" }, payload || {})
            }]
          })
        }),
        new Promise(function (resolve) { setTimeout(resolve, 1200); })
      ]);
    } catch (err) {
      /* do not fail UX if analytics call fails */
    }
  }

  async function apiFetch(path, options) {
    var url = getApiBase() + path;
    var opts = options || {};
    opts.headers = opts.headers || {};
    if (token) {
      opts.headers.Authorization = "Bearer " + token;
    }
    var res = await fetch(url, opts);
    var bodyText = await res.text();
    var json = null;
    if (bodyText) {
      try {
        json = JSON.parse(bodyText);
      } catch (err) {
        json = null;
      }
    }
    if (!res.ok) {
      var detail = (json && (json.detail || json.error || json.message)) || bodyText || ("HTTP " + res.status);
      throw new Error(detail);
    }
    return json || {};
  }

  function td(text) {
    var node = document.createElement("td");
    node.textContent = text == null ? "" : String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderJobs(rows) {
    lastJobsRows = rows || [];
    clear(el.jobsBody);
    (lastJobsRows || []).forEach(function (job) {
      var tr = document.createElement("tr");
      tr.appendChild(td(job.id));
      tr.appendChild(td(job.status));
      tr.appendChild(td(job.provider));
      tr.appendChild(td(job.operation));
      tr.appendChild(td(job.credits_cost));
      tr.appendChild(td(job.attempt_count + "/" + job.max_attempts));
      tr.appendChild(td(job.created_at));
      el.jobsBody.appendChild(tr);
      if (job && job.id && job.status === "succeeded" && !seenSucceededJobIds[job.id]) {
        seenSucceededJobIds[job.id] = true;
        saveSucceededJobIds();
        trackEvent("job_succeeded", "app_panel", {
          job_id: job.id,
          provider: job.provider || "",
          operation: job.operation || ""
        });
      }
    });
    detectOnboardingFromData();
  }

  function renderLedger(rows) {
    lastLedgerRows = rows || [];
    clear(el.ledgerBody);
    (lastLedgerRows || []).forEach(function (entry) {
      var tr = document.createElement("tr");
      tr.appendChild(td(entry.created_at));
      tr.appendChild(td(entry.entry_type));
      tr.appendChild(td(entry.amount));
      tr.appendChild(td(entry.balance_after));
      tr.appendChild(td(entry.source_type));
      tr.appendChild(td(entry.idempotency_key));
      el.ledgerBody.appendChild(tr);
    });
    detectOnboardingFromData();
  }

  function setLoggedInState(loggedIn) {
    el.authBox.style.display = loggedIn ? "none" : "grid";
    el.accountBox.style.display = loggedIn ? "grid" : "none";
    el.logoutBtn.style.display = loggedIn ? "inline-flex" : "none";
    el.refreshBtn.style.display = loggedIn ? "inline-flex" : "none";
    renderOnboarding();
  }

  async function refreshMe() {
    var me = await apiFetch("/api/auth/me");
    el.meEmail.textContent = me.user.email || "-";
    el.meUserId.textContent = me.user.id || "-";
  }

  async function refreshBalanceAndLedger() {
    var bal = await apiFetch("/api/credits/balance");
    el.balance.textContent = String(bal.balance);
    var ledger = await apiFetch("/api/credits/ledger?limit=20");
    renderLedger(ledger.rows);
  }

  async function refreshJobs() {
    var jobs = await apiFetch("/api/jobs?limit=30");
    renderJobs(jobs.jobs);
  }

  async function refreshAll() {
    await refreshMe();
    await refreshBalanceAndLedger();
    await refreshJobs();
  }

  async function handleCheckoutQueryState() {
    if (checkoutSuccessTracked) return;
    var params = new URLSearchParams(location.search);
    var checkoutState = (params.get("checkout") || "").trim().toLowerCase();
    if (!checkoutState) return;

    if (checkoutState === "success") {
      markOnboarding("checkout_started", true);
      markOnboarding("checkout_success", true);
      await trackEvent("checkout_success", "app_panel", { source_state: "query" });
      setStatus("Platnosc zakonczona sukcesem. Odswiezam saldo.", "ok");
      checkoutSuccessTracked = true;
    } else if (checkoutState === "cancel") {
      setStatus("Checkout anulowany.", "warn");
    }

    params.delete("checkout");
    var cleanUrl = location.pathname + (params.toString() ? ("?" + params.toString()) : "") + location.hash;
    history.replaceState({}, "", cleanUrl);
  }

  async function bootstrapSession() {
    if (!token) {
      setLoggedInState(false);
      setStatus("Zaloguj sie albo zaloz konto.", "info");
      return;
    }
    try {
      setLoggedInState(true);
      markOnboarding("registered", true);
      await handleCheckoutQueryState();
      await refreshAll();
      setStatus("Sesja aktywna.", "ok");
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(function () {
        refreshJobs().catch(function () {});
      }, 6000);
    } catch (err) {
      setToken("");
      setLoggedInState(false);
      setStatus("Sesja wygasla. Zaloguj ponownie.", "warn");
    }
  }

  el.saveApiBase.addEventListener("click", function () {
    var base = getApiBase();
    if (!base) return;
    localStorage.setItem(API_BASE_KEY, base);
    setStatus("Zapisano API base: " + base, "ok");
    bootstrapSession().catch(function (err) {
      setStatus(err.message, "err");
    });
  });

  el.registerForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    var email = document.getElementById("registerEmail").value.trim();
    var password = document.getElementById("registerPassword").value;
    try {
      setStatus("Rejestracja...", "info");
      var out = await apiFetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, password: password })
      });
      setToken(out.token || "");
      markOnboarding("registered", true);
      await trackEvent("signup", "app_panel", {
        user_id: (out.user && out.user.id) || "",
        email_domain: String(email.split("@")[1] || "").toLowerCase()
      });
      await bootstrapSession();
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  el.loginForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    var email = document.getElementById("loginEmail").value.trim();
    var password = document.getElementById("loginPassword").value;
    try {
      setStatus("Logowanie...", "info");
      var out = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, password: password })
      });
      setToken(out.token || "");
      markOnboarding("registered", true);
      await bootstrapSession();
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  el.logoutBtn.addEventListener("click", async function () {
    try {
      if (token) {
        await apiFetch("/api/auth/logout", { method: "POST" });
      }
    } catch (err) {
      /* no-op */
    }
    setToken("");
    setLoggedInState(false);
    setStatus("Wylogowano.", "ok");
    if (pollTimer) clearInterval(pollTimer);
  });

  el.refreshBtn.addEventListener("click", async function () {
    try {
      await refreshAll();
      setStatus("Odswiezono dane.", "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  el.topupForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    try {
      var credits = Number(document.getElementById("topupCredits").value || "0");
      if (!credits || credits < 1) throw new Error("Podaj liczbe kredytow >= 1");
      setStatus("Tworze sesje Stripe Checkout...", "info");
      markOnboarding("checkout_started", true);
      await trackEvent("checkout_started", "app_panel", { credits: credits });
      var successUrl = location.origin + location.pathname + "?checkout=success";
      var cancelUrl = location.origin + location.pathname + "?checkout=cancel";
      var out = await apiFetch("/api/billing/checkout-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          credits: credits,
          success_url: successUrl,
          cancel_url: cancelUrl,
          currency: "usd"
        })
      });
      if (out.url) {
        location.href = out.url;
      } else {
        setStatus("Brak URL checkoutu.", "err");
      }
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  el.createJobForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    try {
      var provider = document.getElementById("jobProvider").value;
      var prompt = document.getElementById("jobPrompt").value.trim();
      var creditsCost = Number(document.getElementById("jobCreditsCost").value || "1");
      if (!prompt) throw new Error("Prompt jest wymagany");
      setStatus("Tworze job...", "info");
      await apiFetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider,
          operation: "image.generate",
          credits_cost: creditsCost,
          input: { prompt: prompt }
        })
      });
      markOnboarding("first_job_created", true);
      await trackEvent("job_created", "app_panel", {
        provider: provider,
        operation: "image.generate",
        credits_cost: creditsCost
      });
      await refreshAll();
      setStatus("Job dodany.", "ok");
      document.getElementById("jobPrompt").value = "";
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  el.apiBase.value = inferApiBase();
  setLoggedInState(Boolean(token));
  bootstrapSession().catch(function (err) {
    setStatus(err.message, "err");
  });
})();
