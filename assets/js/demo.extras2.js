/* demo.extras2.js — 20 PRO add-ons (fail-safe, no backend changes) */
(function(){
  const $ = (id) => document.getElementById(id);
  const STORE_KEY = "danieloza_demo_state_v2";
  const FAV_KEY = "danieloza_demo_favs_v1";
  const PRO_KEY = "danieloza_demo_pro_v1";

  // base elements (may or may not exist)
  const promptEl = $("prompt");
  const imageUrlEl = $("image_url");
  const backendEl = $("backend");
  const styleEl = $("style");
  const logEl = $("log");
  const statusEl = $("status");
  const videoEl = $("video");
  const toast = $("toast");

  // pro UI
  const proTemplates = $("proTemplates");
  const proSuffix = $("proSuffix");
  const btnCopyPrompt = $("btnCopyPrompt");
  const btnClearPrompt = $("btnClearPrompt");
  const btnCopyUrl = $("btnCopyUrl");
  const btnValidateUrl = $("btnValidateUrl");
  const favName = $("favName");
  const btnFavSave = $("btnFavSave");
  const favSelect = $("favSelect");
  const btnFavLoad = $("btnFavLoad");
  const btnFavDel = $("btnFavDel");
  const manualJob = $("manualJob");
  const btnJobCheck = $("btnJobCheck");
  const btnCopyJob = $("btnCopyJob");
  const latency = $("latency");
  const btnPing = $("btnPing");
  const btnShare = $("btnShare");
  const btnCopyVideo = $("btnCopyVideo");
  const btnDownload = $("btnDownload");
  const btnTheme = $("btnTheme");
  const saveDot = $("saveDot");
  const btnConsole = $("btnConsole");
  const btnProReset = $("btnProReset");
  const proNotice = $("proNotice");

  function toastMsg(msg){
    if(!toast){ return; }
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
  function saveStore(s){
    localStorage.setItem(STORE_KEY, JSON.stringify(s || {}));
  }

  function loadFavs(){
    try{ return JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); }catch(_){ return []; }
  }
  function saveFavs(arr){
    localStorage.setItem(FAV_KEY, JSON.stringify(arr || []));
  }

  function loadPro(){
    try{ return JSON.parse(localStorage.getItem(PRO_KEY) || "{}"); }catch(_){ return {}; }
  }
  function savePro(x){
    localStorage.setItem(PRO_KEY, JSON.stringify(x || {}));
  }

  // (18) autosave indicator
  let saveTimer = null;
  function markSaved(){
    if(!saveDot) return;
    saveDot.textContent = "Saved ✓";
    saveDot.classList.add("on");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(()=>saveDot.classList.remove("on"), 1400);
  }

  function onAnyChange(){
    markSaved();
  }

  // (8) templates + (9) suffix
  const TEMPLATES = [
    {name:"Ad — premium cinematic", text:"Cinematic premium ad, subtle camera move, clean background, high detail, polished lighting."},
    {name:"UGC — handheld phone", text:"Handheld phone vibe, natural lighting, authentic UGC, slight shake, close-up, realistic."},
    {name:"Macro — product detail", text:"Macro close-up, glossy highlights, slow movement, crisp textures, appetizing detail."},
    {name:"Fashion — editorial", text:"Editorial fashion lookbook, smooth dolly in, soft studio light, premium pacing, clean composition."},
    {name:"Tech — futuristic", text:"Futuristic tech aesthetic, neon accents, clean reflections, smooth orbit camera, cinematic."}
  ];
  const SUFFIX = [
    "seamless loop",
    "high detail",
    "soft studio light",
    "high contrast",
    "slow zoom in",
    "macro close-up",
    "clean background",
    "subtle motion"
  ];

  function fillSelect(sel, arr, first){
    if(!sel) return;
    if(sel.dataset.filled) return;
    sel.innerHTML = `<option value="">${first||"Wybierz…"}</option>` + arr.map((x,i)=>`<option value="${i}">${x.name||x}</option>`).join("");
    sel.dataset.filled = "1";
  }

  function setPrompt(txt, mode){
    if(!promptEl) return;
    const cur = (promptEl.value || "").trim();
    if(mode === "append"){
      promptEl.value = cur ? (cur + " " + txt) : txt;
    } else {
      promptEl.value = txt;
    }
    promptEl.dispatchEvent(new Event("input"));
    promptEl.dispatchEvent(new Event("change"));
  }

  // (1) copy prompt
  async function copyText(t, okMsg){
    try{
      await navigator.clipboard.writeText(t||"");
      toastMsg(okMsg || "Skopiowano ✅");
    }catch(_){
      toastMsg("Brak dostępu do schowka");
    }
  }

  // (4) validate URL
  function looksLikeUrl(u){
    try{
      const x = new URL(u);
      return x.protocol === "http:" || x.protocol === "https:";
    }catch(_){ return false; }
  }

  // (10) manual job check
  async function checkJob(id){
    const base = (backendEl?.value||"").trim().replace(/\/$/,"");
    if(!base){ toastMsg("Brak backend URL"); return; }
    if(!id){ toastMsg("Brak job_id"); return; }
    try{
      const r = await fetch(`${base}/api/jobs/${encodeURIComponent(id)}`, {cache:"no-store"});
      const j = await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(j?.detail || ("HTTP "+r.status));
      safeLog(j);
      toastMsg("Job status OK");
    }catch(e){
      toastMsg("Job check failed");
      safeLog(String(e));
    }
  }

  // (12) latency ping
  async function ping(){
    const base = (backendEl?.value||"").trim().replace(/\/$/,"");
    if(!base){ toastMsg("Brak backend URL"); return; }
    const t0 = performance.now();
    try{
      const r = await fetch(`${base}/api/health`, {cache:"no-store"});
      const ms = Math.round(performance.now() - t0);
      if(!r.ok) throw new Error("bad");
      if(latency) latency.textContent = ms + " ms";
      toastMsg("Ping OK");
    }catch(_){
      if(latency) latency.textContent = "offline";
      toastMsg("Backend offline");
    }
  }

  // (13)(14) share link + load from link
  function buildShareUrl(){
    const u = new URL(window.location.href);
    u.searchParams.set("backend", (backendEl?.value||"").trim());
    u.searchParams.set("image_url", (imageUrlEl?.value||"").trim());
    u.searchParams.set("style", (styleEl?.value||"").trim());
    u.searchParams.set("prompt", (promptEl?.value||""));
    return u.toString();
  }

  function loadFromQuery(){
    const u = new URL(window.location.href);
    const backend = u.searchParams.get("backend");
    const image_url = u.searchParams.get("image_url");
    const style = u.searchParams.get("style");
    const prompt = u.searchParams.get("prompt");

    let changed = false;
    if(backend && backendEl){ backendEl.value = backend; backendEl.dispatchEvent(new Event("change")); changed=true; }
    if(image_url && imageUrlEl){ imageUrlEl.value = image_url; imageUrlEl.dispatchEvent(new Event("change")); changed=true; }
    if(style && styleEl){ styleEl.value = style; styleEl.dispatchEvent(new Event("change")); changed=true; }
    if(prompt && promptEl){ promptEl.value = prompt; promptEl.dispatchEvent(new Event("input")); promptEl.dispatchEvent(new Event("change")); changed=true; }

    if(changed) toastMsg("Wczytano ustawienia z linku");
  }

  // (15)(16) video url + download
  function getVideoUrl(){
    const url = (videoEl && videoEl.src) ? videoEl.src : "";
    return url || "";
  }

  function downloadVideo(){
    const url = getVideoUrl();
    if(!url){ toastMsg("Brak video"); return; }
    const a = document.createElement("a");
    a.href = url;
    a.download = "danieloza_demo_video.mp4";
    document.body.appendChild(a);
    a.click();
    a.remove();
    toastMsg("Download started");
  }

  // (17) theme toggle
  function toggleTheme(){
    const b = document.body;
    const on = b.classList.toggle("theme-contrast");
    const p = loadPro();
    p.theme = on ? "contrast" : "normal";
    savePro(p);
    toastMsg(on ? "Theme: contrast" : "Theme: normal");
  }
  function applyTheme(){
    const p = loadPro();
    if(p.theme === "contrast"){ document.body.classList.add("theme-contrast"); }
  }

  // (19) mini console toggle
  function toggleConsole(){
    if(!logEl) return;
    const on = logEl.classList.toggle("collapsed");
    toastMsg(on ? "Log ukryty" : "Log pokazany");
    const p = loadPro();
    p.console = on ? "off" : "on";
    savePro(p);
  }
  function applyConsole(){
    const p = loadPro();
    if(p.console === "off"){ logEl?.classList.add("collapsed"); }
  }

  // (5)(6)(7) favorites
  function renderFavs(){
    if(!favSelect) return;
    const arr = loadFavs();
    favSelect.innerHTML = '<option value="">Ulubione…</option>' + arr.map((x,i)=>`<option value="${i}">${x.name}</option>`).join("");
  }

  function saveFav(){
    const name = (favName?.value||"").trim() || ("fav " + new Date().toLocaleString());
    const text = (promptEl?.value||"").trim();
    if(!text){ toastMsg("Prompt pusty"); return; }
    const arr = loadFavs().filter(x => x && x.name !== name);
    arr.unshift({name, text, t:Date.now()});
    saveFavs(arr.slice(0, 30));
    renderFavs();
    toastMsg("Zapisano do ulubionych");
    favName && (favName.value = "");
  }

  function loadFav(){
    const i = parseInt(favSelect?.value||"", 10);
    const arr = loadFavs();
    if(!Number.isFinite(i) || !arr[i]) return;
    setPrompt(arr[i].text, "set");
    toastMsg("Wczytano ulubiony");
  }

  function delFav(){
    const i = parseInt(favSelect?.value||"", 10);
    const arr = loadFavs();
    if(!Number.isFinite(i) || !arr[i]) return;
    const name = arr[i].name;
    arr.splice(i,1);
    saveFavs(arr);
    renderFavs();
    toastMsg("Usunięto: " + name);
  }

  // (20) reset PRO only
  function resetPro(){
    try{
      localStorage.removeItem(FAV_KEY);
      localStorage.removeItem(PRO_KEY);
    }catch(_){}
    renderFavs();
    document.body.classList.remove("theme-contrast");
    logEl?.classList.remove("collapsed");
    if(latency) latency.textContent = "—";
    toastMsg("PRO reset ✅");
  }

  // wiring: only if panel exists
  if(proNotice){
    fillSelect(proTemplates, TEMPLATES, "Templates…");
    fillSelect(proSuffix, SUFFIX, "Quick suffix…");
    renderFavs();
    applyTheme();
    applyConsole();
    loadFromQuery(); // (14)

    // autosave indicator: attach changes
    backendEl?.addEventListener("change", onAnyChange);
    imageUrlEl?.addEventListener("change", onAnyChange);
    promptEl?.addEventListener("change", onAnyChange);
    styleEl?.addEventListener("change", onAnyChange);

    btnCopyPrompt?.addEventListener("click", ()=>copyText(promptEl?.value||"", "Prompt skopiowany"));
    btnClearPrompt?.addEventListener("click", ()=>{ if(promptEl){ promptEl.value=""; promptEl.dispatchEvent(new Event("input")); promptEl.dispatchEvent(new Event("change")); } toastMsg("Prompt wyczyszczony"); });
    btnCopyUrl?.addEventListener("click", ()=>copyText(imageUrlEl?.value||"", "URL skopiowany"));
    btnValidateUrl?.addEventListener("click", ()=>{
      const u = (imageUrlEl?.value||"").trim();
      if(!u) return toastMsg("Brak URL");
      toastMsg(looksLikeUrl(u) ? "URL wygląda OK ✅" : "To nie wygląda jak URL ❌");
    });

    btnFavSave?.addEventListener("click", saveFav);
    btnFavLoad?.addEventListener("click", loadFav);
    btnFavDel?.addEventListener("click", delFav);

    proTemplates?.addEventListener("change", ()=>{
      const i = parseInt(proTemplates.value, 10);
      if(Number.isFinite(i) && TEMPLATES[i]){ setPrompt(TEMPLATES[i].text, "set"); toastMsg("Template wstawiony"); }
    });

    proSuffix?.addEventListener("change", ()=>{
      const i = parseInt(proSuffix.value, 10);
      if(Number.isFinite(i) && SUFFIX[i]){ setPrompt(SUFFIX[i], "append"); toastMsg("Suffix dodany"); }
      proSuffix.value = "";
    });

    btnJobCheck?.addEventListener("click", ()=>checkJob((manualJob?.value||"").trim()));
    btnCopyJob?.addEventListener("click", ()=>{
      const s = loadStore();
      const id = s.last_job_id || "";
      if(!id) return toastMsg("Brak last_job_id");
      copyText(id, "job_id skopiowany");
    });

    btnPing?.addEventListener("click", ping);
    btnShare?.addEventListener("click", ()=>copyText(buildShareUrl(), "Link skopiowany"));
    btnCopyVideo?.addEventListener("click", ()=>{
      const url = getVideoUrl();
      if(!url) return toastMsg("Brak video");
      copyText(url, "Video URL skopiowany");
    });
    btnDownload?.addEventListener("click", downloadVideo);
    btnTheme?.addEventListener("click", toggleTheme);
    btnConsole?.addEventListener("click", toggleConsole);
    btnProReset?.addEventListener("click", resetPro);

    toastMsg("PRO Extras załadowane ✅");
  }
})();
