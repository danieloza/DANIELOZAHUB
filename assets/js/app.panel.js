(function () {
  "use strict";

  var TOKEN_KEY = "mvp_auth_token";
  var API_BASE_KEY = "mvp_api_base";
  var token = localStorage.getItem(TOKEN_KEY) || "";
  var pollTimer = null;

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
    ledgerBody: document.getElementById("ledgerBody")
  };

  function inferApiBase() {
    var saved = localStorage.getItem(API_BASE_KEY);
    if (saved) return saved;
    if (location.hostname.indexOf("onrender.com") !== -1) {
      return location.origin;
    }
    return "http://127.0.0.1:8000";
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
    clear(el.jobsBody);
    (rows || []).forEach(function (job) {
      var tr = document.createElement("tr");
      tr.appendChild(td(job.id));
      tr.appendChild(td(job.status));
      tr.appendChild(td(job.provider));
      tr.appendChild(td(job.operation));
      tr.appendChild(td(job.credits_cost));
      tr.appendChild(td(job.attempt_count + "/" + job.max_attempts));
      tr.appendChild(td(job.created_at));
      el.jobsBody.appendChild(tr);
    });
  }

  function renderLedger(rows) {
    clear(el.ledgerBody);
    (rows || []).forEach(function (entry) {
      var tr = document.createElement("tr");
      tr.appendChild(td(entry.created_at));
      tr.appendChild(td(entry.entry_type));
      tr.appendChild(td(entry.amount));
      tr.appendChild(td(entry.balance_after));
      tr.appendChild(td(entry.source_type));
      tr.appendChild(td(entry.idempotency_key));
      el.ledgerBody.appendChild(tr);
    });
  }

  function setLoggedInState(loggedIn) {
    el.authBox.style.display = loggedIn ? "none" : "grid";
    el.accountBox.style.display = loggedIn ? "grid" : "none";
    el.logoutBtn.style.display = loggedIn ? "inline-flex" : "none";
    el.refreshBtn.style.display = loggedIn ? "inline-flex" : "none";
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

  async function bootstrapSession() {
    if (!token) {
      setLoggedInState(false);
      setStatus("Zaloguj sie albo zaloz konto.", "info");
      return;
    }
    try {
      setLoggedInState(true);
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
      var out = await apiFetch("/api/billing/checkout-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          credits: credits,
          success_url: location.href,
          cancel_url: location.href,
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
