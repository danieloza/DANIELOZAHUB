/* demo.extras3.js — OPS/QA add-ons (safe, no backend changes) */
(function(){
  const $ = (id) => document.getElementById(id);
  const STORE_KEY = "danieloza_demo_state_v2";
  const OPS_KEY = "danieloza_demo_ops_v1";
  const REQ_KEY = "danieloza_demo_reqlog_v1";

  const promptEl = $("prompt");
  const imageUrlEl = $("image_url");
  const backendEl = $("backend");
  const logEl = $("log");
  const statusEl = $("status");
  const videoEl = $("video");
  const toast = $("toast");

  const opsAutoScroll = $("opsAutoScroll");
  const opsAutoCopyVideo = $("opsAutoCopyVideo");
  const opsRestoreVideo = $("opsRestoreVideo");
  const opsRetryLast = $("opsRetryLast");
  const opsPoll = $("opsPoll");
  const opsMax = $("opsMax");
  const opsNet = $("opsNet");
  const opsCors = $("opsCors");
  const opsPreflight = $("opsPreflight");
  const opsExportLogs = $("opsExportLogs");
  const opsClearLogs = $("opsClearLogs");
  const opsCleanPrompt = $("opsCleanPrompt");
  const opsLintPrompt = $("opsLintPrompt");
  const opsSanUrl = $("opsSanUrl");
  const opsFocus = $("opsFocus");
  const opsCompact = $("opsCompact");
  const opsTimer = $("opsTimer");

  function toastMsg(msg){
    if(!toast) return;
    toast.textContent = msg;
    toast.classList.add("on");
    setTimeout(()=>toast.classList.remove("on"), 2200);
  }

  function safeLog(x){
    try{
      if(!logEl) return;
      logEl.textContent = (typeof x === "string") ? x : JSON.stringify(x, null, 2);
    }catch(_){}
  }

  function loadStore(){
    try{ return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); }catch(_){ return {}; }
  }
  function loadOps(){
    try{ return JSON.parse(localStorage.getItem(OPS_KEY) || "{}"); }catch(_){ return {}; }
  }
  function saveOps(x){
    localStorage.setItem(OPS_KEY, JSON.stringify(x || {}));
  }
  function loadReq(){
    try{ return JSON.parse(localStorage.getItem(REQ_KEY) || "[]"); }catch(_){ return []; }
  }
  function saveReq(arr){
    localStorage.setItem(REQ_KEY, JSON.stringify(arr || []));
  }

  // (20) Crash shield
  window.addEventListener("error", (e)=>{
    toastMsg("JS error (zapisano w LOG)");
    safeLog({error: String(e.message||e.error||"unknown"), file: e.filename, line: e.lineno});
  });
  window.addEventListener("unhandledrejection", (e)=>{
    toastMsg("Promise error (LOG)");
    safeLog({rejection: String(e.reason||"unknown")});
  });

  // (7) network status
  function setNet(){
    if(!opsNet) return;
    opsNet.textContent = navigator.onLine ? "online" : "offline";
    opsNet.classList.toggle("bad", !navigator.onLine);
  }
  window.addEventListener("online", ()=>{ setNet(); toastMsg("Online ✅"); });
  window.addEventListener("offline", ()=>{ setNet(); toastMsg("Offline ❌"); });
  setNet();

  // (19) session timer
  const t0 = Date.now();
  setInterval(()=>{
    if(!opsTimer) return;
    const s = Math.floor((Date.now()-t0)/1000);
    const mm = String(Math.floor(s/60)).padStart(2,"0");
    const ss = String(s%60).padStart(2,"0");
    opsTimer.textContent = mm + ":" + ss;
  }, 500);

  // Intercept fetch for (10) request logger (best-effort)
  const _fetch = window.fetch;
  window.fetch = async function(url, opts){
    try{
      const arr = loadReq();
      arr.unshift({t: Date.now(), url: String(url), method: (opts?.method||"GET"), hasBody: !!opts?.body});
      saveReq(arr.slice(0, 30));
    }catch(_){}
    return _fetch.apply(this, arguments);
  };

  // (1)(2)(3) video hooks via polling src changes
  let lastVideo = "";
  function checkVideo(){
    const url = (videoEl && videoEl.src) ? videoEl.src : "";
    if(url && url !== lastVideo){
      lastVideo = url;
      // store
      const o = loadOps(); o.lastVideo = url; saveOps(o);

      if(opsAutoScroll?.checked){
        try{ videoEl.scrollIntoView({behavior:"smooth", block:"center"}); }catch(_){}
      }
      if(opsAutoCopyVideo?.checked){
        navigator.clipboard?.writeText(url).then(()=>toastMsg("Video URL skopiowany")).catch(()=>{});
      }
    }
  }
  setInterval(checkVideo, 900);

  // restore last video
  function restoreVideo(){
    const o = loadOps();
    if(o.lastVideo && videoEl && opsRestoreVideo?.checked){
      try{
        videoEl.style.display = "block";
        videoEl.src = o.lastVideo;
        toastMsg("Przywrócono ostatnie video");
      }catch(_){}
    }
  }

  // (4) retry last job quick check
  async function retryLastJob(){
    const s = loadStore();
    const id = s.last_job_id || "";
    if(!id) return toastMsg("Brak last_job_id");
    const base = (backendEl?.value||"").trim().replace(/\/$/,"");
    if(!base) return toastMsg("Brak backend URL");
    try{
      const r = await fetch(`${base}/api/jobs/${encodeURIComponent(id)}`, {cache:"no-store"});
      const j = await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(j?.detail || ("HTTP "+r.status));
      safeLog(j);
      toastMsg("Sprawdzono last job ✅");
    }catch(e){
      toastMsg("Retry failed");
      safeLog(String(e));
    }
  }

  // (8) CORS helper / health
  async function corsCheck(){
    const base = (backendEl?.value||"").trim().replace(/\/$/,"");
    if(!base) return toastMsg("Brak backend URL");
    try{
      const r = await fetch(`${base}/api/health`, {cache:"no-store"});
      const txt = await r.text();
      const info = {ok:r.ok, status:r.status, body: txt.slice(0,200)};
      safeLog(info);
      toastMsg(r.ok ? "CORS/health OK" : "Health error");
    }catch(e){
      toastMsg("CORS/health failed");
      safeLog(String(e));
    }
  }

  // (9) preflight tester (GET/POST no job)
  async function preflight(){
    const base = (backendEl?.value||"").trim().replace(/\/$/,"");
    if(!base) return toastMsg("Brak backend URL");
    try{
      const a = await fetch(`${base}/api/health`, {cache:"no-store"});
      const ms = Math.round(performance.now());
      const b = await fetch(`${base}/api/health`, {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"}).catch(()=>null);
      safeLog({get_ok:a.ok, get_status:a.status, post_supported: !!b, note:"POST może zwrócić 405 i to jest OK"});
      toastMsg("Preflight zrobiony");
    }catch(e){
      toastMsg("Preflight failed");
      safeLog(String(e));
    }
  }

  // (11) export logs
  async function exportLogs(){
    const req = loadReq();
    const payload = {
      time: new Date().toISOString(),
      store: loadStore(),
      ops: loadOps(),
      reqlog: req,
      ui: {
        backend: (backendEl?.value||"").trim(),
        image_url: (imageUrlEl?.value||"").trim(),
        prompt: (promptEl?.value||"")
      }
    };
    try{
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      toastMsg("Logi skopiowane ✅");
    }catch(_){
      toastMsg("Nie mogę skopiować — wrzucam do LOG");
      safeLog(payload);
    }
  }

  // (12) clear logs
  function clearLogs(){
    try{ localStorage.removeItem(REQ_KEY); }catch(_){}
    toastMsg("Wyczyszczono request log");
  }

  // (13) smart prompt cleaner
  function cleanPrompt(){
    if(!promptEl) return;
    let t = promptEl.value || "";
    t = t.replace(/\s+/g, " ").trim();
    t = t.replace(/(\.\s*){2,}/g, ". ");
    t = t.replace(/,\s*,+/g, ", ");
    promptEl.value = t;
    promptEl.dispatchEvent(new Event("input"));
    promptEl.dispatchEvent(new Event("change"));
    toastMsg("Prompt oczyszczony");
  }

  // (14) prompt lint
  function lintPrompt(){
    const t = (promptEl?.value||"").toLowerCase();
    if(!t) return toastMsg("Prompt pusty");
    const words = t.split(/\s+/).filter(Boolean);
    const dup = [];
    for(let i=1;i<words.length;i++){
      if(words[i] === words[i-1]) dup.push(words[i]);
    }
    if(dup.length){
      toastMsg("Powtórzenia: " + dup.slice(0,6).join(", "));
    } else {
      toastMsg("Prompt OK ✅");
    }
  }

  // (15) image_url sanitizer
  function sanitizeUrl(){
    if(!imageUrlEl) return;
    let u = (imageUrlEl.value||"").trim();
    u = u.replace(/\s+/g,"");
    // opcjonalnie: http -> https
    if(u.startsWith("http://")) u = "https://" + u.slice(7);
    imageUrlEl.value = u;
    imageUrlEl.dispatchEvent(new Event("change"));
    toastMsg("URL poprawiony");
  }

  // (16) shortcuts map
  document.addEventListener("keydown", (e)=>{
    if(e.ctrlKey && e.key.toLowerCase() === "k"){
      e.preventDefault(); promptEl?.focus(); toastMsg("Focus: prompt");
    }
    if(e.ctrlKey && e.key.toLowerCase() === "u"){
      e.preventDefault(); imageUrlEl?.focus(); toastMsg("Focus: image_url");
    }
    if(e.ctrlKey && e.key.toLowerCase() === "l"){
      e.preventDefault();
      if(logEl){ logEl.classList.toggle("collapsed"); toastMsg("Toggle log"); }
    }
  });

  // (17) focus mode (hide extra panels)
  function toggleFocus(){
    document.body.classList.toggle("focus-mode");
    toastMsg(document.body.classList.contains("focus-mode") ? "Focus mode ON" : "Focus mode OFF");
  }

  // (18) compact mode
  function toggleCompact(){
    document.body.classList.toggle("compact-mode");
    toastMsg(document.body.classList.contains("compact-mode") ? "Compact ON" : "Compact OFF");
  }

  // (5)(6) poll interval + max retries values stored (frontend-only)
  function saveOpsSettings(){
    const o = loadOps();
    if(opsPoll) o.poll = parseInt(opsPoll.value||"12000", 10);
    if(opsMax) o.max = parseInt(opsMax.value||"80", 10);
    o.autoScroll = !!opsAutoScroll?.checked;
    o.autoCopyVideo = !!opsAutoCopyVideo?.checked;
    o.restoreVideo = !!opsRestoreVideo?.checked;
    saveOps(o);
  }
  function restoreOpsSettings(){
    const o = loadOps();
    if(opsPoll && o.poll) opsPoll.value = String(o.poll);
    if(opsMax && o.max) opsMax.value = String(o.max);
    if(opsAutoScroll) opsAutoScroll.checked = !!o.autoScroll;
    if(opsAutoCopyVideo) opsAutoCopyVideo.checked = !!o.autoCopyVideo;
    if(opsRestoreVideo) opsRestoreVideo.checked = !!o.restoreVideo;
  }

  // wire if panel exists
  if(opsExportLogs){
    restoreOpsSettings();
    restoreVideo();

    opsAutoScroll?.addEventListener("change", saveOpsSettings);
    opsAutoCopyVideo?.addEventListener("change", saveOpsSettings);
    opsRestoreVideo?.addEventListener("change", saveOpsSettings);
    opsPoll?.addEventListener("change", saveOpsSettings);
    opsMax?.addEventListener("change", saveOpsSettings);

    opsRetryLast?.addEventListener("click", retryLastJob);
    opsCors?.addEventListener("click", corsCheck);
    opsPreflight?.addEventListener("click", preflight);
    opsExportLogs?.addEventListener("click", exportLogs);
    opsClearLogs?.addEventListener("click", clearLogs);
    opsCleanPrompt?.addEventListener("click", cleanPrompt);
    opsLintPrompt?.addEventListener("click", lintPrompt);
    opsSanUrl?.addEventListener("click", sanitizeUrl);
    opsFocus?.addEventListener("click", toggleFocus);
    opsCompact?.addEventListener("click", toggleCompact);

    setInterval(setNet, 5000);
    toastMsg("OPS/QA extras ✅");
  }
})();
