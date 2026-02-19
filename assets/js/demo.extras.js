/* demo.extras.js — 12 add-ons (frontend-only safe) */
(function(){
  const $ = (id) => document.getElementById(id);
  const STORE_KEY = "danieloza_demo_state_v2";
  const HISTORY_KEY = "danieloza_demo_history_v1";

  const promptEl = $("prompt");
  const imageUrlEl = $("image_url");
  const backendEl = $("backend");
  const logEl = $("log");
  const statusEl = $("status");

  // UI extras
  const presetSel = $("presetSel");
  const chipRow = $("chipRow");
  const promptCount = $("promptCount");
  const imgPreview = $("imgPreview");
  const btnPasteUrl = $("btnPasteUrl");
  const btnRandPrompt = $("btnRandPrompt");
  const btnExport = $("btnExport");
  const btnImport = $("btnImport");
  const btnClear = $("btnClear");
  const btnHelp = $("btnHelp");
  const toast = $("toast");
  const helpModal = $("helpModal");
  const helpClose = $("helpClose");
  const historyList = $("historyList");

  function loadStore(){
    try{ return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); }catch(_){ return {}; }
  }
  function saveStore(s){
    localStorage.setItem(STORE_KEY, JSON.stringify(s || {}));
  }

  function loadHistory(){
    try{ return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }catch(_){ return []; }
  }
  function saveHistory(arr){
    localStorage.setItem(HISTORY_KEY, JSON.stringify(arr || []));
  }

  function toastMsg(msg){
    if(!toast) return;
    toast.textContent = msg;
    toast.classList.add("on");
    setTimeout(()=>toast.classList.remove("on"), 2200);
  }

  function setStatus(t){
    if(statusEl) statusEl.textContent = t;
  }

  // ---------- 1) Presety promptów + 6) losuj prompt ----------
  const PRESETS = [
    { name:"Cinematic product ad (premium)", text:"Cinematic product ad, premium lighting, slow motion, shallow depth of field, subtle camera move, high detail, clean background." },
    { name:"UGC-style phone vibe", text:"Handheld phone vibe, natural lighting, slight shake, authentic UGC look, close-up, quick punchy motion, realistic." },
    { name:"Fashion / lookbook", text:"Fashion lookbook style, smooth dolly in, soft studio lighting, crisp textures, elegant pacing, premium editorial." },
    { name:"Food / drink macro", text:"Macro close-up, glossy highlights, slow pour, cinematic lighting, sharp detail, appetizing, high contrast." },
    { name:"Tech / futuristic", text:"Futuristic tech aesthetic, neon accents, clean reflections, smooth orbit camera, premium render, cinematic." },
    { name:"Before/after reveal", text:"Before/after reveal, quick transition, clean background, satisfying motion, smooth camera push-in." },
    { name:"Loop 3s", text:"Seamless loop, 3 seconds, subtle motion, satisfying repeat, stable framing." },
    { name:"ASMR slow", text:"ASMR slow, very gentle movements, calming pacing, soft light, close-up textures, minimal camera movement." }
  ];

  function fillPresets(){
    if(!presetSel) return;
    if(presetSel.dataset.filled) return;
    presetSel.innerHTML = '<option value="">Wybierz preset…</option>' + PRESETS.map((p,i)=>`<option value="${i}">${p.name}</option>`).join("");
    presetSel.dataset.filled = "1";
  }

  function setPrompt(text, mode){
    if(!promptEl) return;
    if(mode === "append"){
      const cur = (promptEl.value || "").trim();
      promptEl.value = cur ? (cur + " " + text) : text;
    } else {
      promptEl.value = text;
    }
    promptEl.dispatchEvent(new Event("input"));
    promptEl.dispatchEvent(new Event("change"));
  }

  // ---------- 2) Quick chips ----------
  const CHIPS = [
    "cinematic lighting",
    "handheld",
    "slow zoom in",
    "orbit camera",
    "macro close-up",
    "high contrast",
    "soft studio light",
    "clean background",
    "seamless loop",
    "subtle motion"
  ];

  function renderChips(){
    if(!chipRow) return;
    chipRow.innerHTML = CHIPS.map(c => `<button type="button" class="chip" data-chip="${c}">${c}</button>`).join("");
    chipRow.addEventListener("click", (e)=>{
      const b = e.target.closest("button[data-chip]");
      if(!b) return;
      setPrompt(b.getAttribute("data-chip"), "append");
      toastMsg("Dodano: " + b.getAttribute("data-chip"));
    });
  }

  // ---------- 3) licznik znaków ----------
  function updateCounter(){
    if(!promptEl || !promptCount) return;
    const n = (promptEl.value || "").length;
    promptCount.textContent = n + " znaków";
    promptCount.classList.toggle("warn", n > 420);
  }

  // ---------- 4) podgląd obrazka ----------
  function setPreview(url){
    if(!imgPreview) return;
    const u = (url || "").trim();
    if(!u){
      imgPreview.style.display = "none";
      imgPreview.removeAttribute("src");
      return;
    }
    imgPreview.style.display = "block";
    imgPreview.src = u;
  }

  // ---------- 5) wklej URL ze schowka ----------
  async function pasteUrl(){
    try{
      const txt = await navigator.clipboard.readText();
      if(!txt) return toastMsg("Schowek pusty");
      if(imageUrlEl) imageUrlEl.value = txt.trim();
      imageUrlEl?.dispatchEvent(new Event("change"));
      setPreview(txt.trim());
      toastMsg("Wklejono URL");
    }catch(_){
      toastMsg("Brak dostępu do schowka");
    }
  }

  // ---------- 7) historia jobów ----------
  function addHistory(job_id){
    if(!job_id) return;
    const arr = loadHistory().filter(x => x && x.job_id !== job_id);
    arr.unshift({ job_id, t: Date.now(), backend: (backendEl?.value||"").trim() });
    saveHistory(arr.slice(0, 10));
    renderHistory();
  }

  function fmtTime(ts){
    try{
      const d = new Date(ts);
      return d.toLocaleString();
    }catch(_){ return ""; }
  }

  function renderHistory(){
    if(!historyList) return;
    const arr = loadHistory();
    if(!arr.length){
      historyList.innerHTML = '<div class="note">Brak historii</div>';
      return;
    }
    historyList.innerHTML = arr.map(x => `
      <button class="historyItem" type="button" data-job="${x.job_id}" title="${fmtTime(x.t)}">
        <span class="mono">${x.job_id}</span>
        <span class="muted">${fmtTime(x.t)}</span>
      </button>
    `).join("");
  }

  // ---------- 8) export/import ustawień ----------
  async function exportState(){
    const s = loadStore();
    const payload = {
      backend: (backendEl?.value||s.backend||"").trim(),
      image_url: (imageUrlEl?.value||s.image_url||"").trim(),
      prompt: (promptEl?.value||s.prompt||""),
      style: (document.getElementById("style")?.value||s.style||"premium"),
      last_job_id: (s.last_job_id||"")
    };
    try{
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      toastMsg("Skopiowano JSON do schowka");
    }catch(_){
      toastMsg("Nie mogę skopiować do schowka");
      if(logEl) logEl.textContent = JSON.stringify(payload, null, 2);
    }
  }

  async function importState(){
    try{
      const txt = await navigator.clipboard.readText();
      const obj = JSON.parse(txt);
      if(obj.backend && backendEl) backendEl.value = obj.backend;
      if(obj.image_url && imageUrlEl) imageUrlEl.value = obj.image_url;
      if(obj.prompt && promptEl) promptEl.value = obj.prompt;
      if(obj.style && document.getElementById("style")) document.getElementById("style").value = obj.style;

      const ss = loadStore();
      if(obj.backend) ss.backend = obj.backend;
      if(obj.image_url) ss.image_url = obj.image_url;
      if(obj.prompt) ss.prompt = obj.prompt;
      if(obj.style) ss.style = obj.style;
      saveStore(ss);

      backendEl?.dispatchEvent(new Event("change"));
      imageUrlEl?.dispatchEvent(new Event("change"));
      promptEl?.dispatchEvent(new Event("input"));
      promptEl?.dispatchEvent(new Event("change"));
      setPreview(imageUrlEl?.value||"");
      toastMsg("Wczytano ustawienia");
    }catch(e){
      toastMsg("Import failed");
      if(logEl) logEl.textContent = String(e);
    }
  }

  // ---------- 10) help modal ----------
  function openHelp(){ helpModal?.classList.add("on"); }
  function closeHelp(){ helpModal?.classList.remove("on"); }

  // ---------- 11) auto-resize textarea ----------
  function autoResize(){
    if(!promptEl) return;
    promptEl.style.height = "auto";
    promptEl.style.height = Math.min(260, promptEl.scrollHeight + 6) + "px";
  }

  // ---------- 12) clear state ----------
  function clearState(){
    try{
      localStorage.removeItem(STORE_KEY);
      localStorage.removeItem(HISTORY_KEY);
    }catch(_){}
    toastMsg("Wyczyszczono stan DEMO");
    // reset UI
    if(backendEl) backendEl.value = "";
    if(imageUrlEl) imageUrlEl.value = "";
    if(promptEl) promptEl.value = "";
    document.getElementById("style") && (document.getElementById("style").value = "premium");
    backendEl?.dispatchEvent(new Event("change"));
    imageUrlEl?.dispatchEvent(new Event("change"));
    promptEl?.dispatchEvent(new Event("input"));
    promptEl?.dispatchEvent(new Event("change"));
    setPreview("");
    renderHistory();
    setStatus("Ready.");
  }

  // Hook: gdy demo.app.js zapisze last_job_id, to złapmy to z localStorage co chwilę i dopiszmy do historii
  let lastSeen = "";
  setInterval(()=>{
    const s = loadStore();
    const id = s.last_job_id || "";
    if(id && id !== lastSeen){
      lastSeen = id;
      addHistory(id);
      toastMsg("Zapisano job do historii");
    }
  }, 1200);

  // Klik w historię — kopiuje job i wrzuca do loga
  historyList?.addEventListener("click", async (e)=>{
    const b = e.target.closest("button[data-job]");
    if(!b) return;
    const id = b.getAttribute("data-job");
    try{ await navigator.clipboard.writeText(id); }catch(_){}
    toastMsg("Skopiowano job_id");
    if(logEl) logEl.textContent = JSON.stringify({job_id:id}, null, 2);
  });

  // wiring UI
  fillPresets();
  renderChips();
  renderHistory();
  updateCounter();
  autoResize();
  setPreview(imageUrlEl?.value||"");

  presetSel?.addEventListener("change", ()=>{
    const idx = parseInt(presetSel.value, 10);
    if(Number.isFinite(idx) && PRESETS[idx]){
      setPrompt(PRESETS[idx].text, "set");
      toastMsg("Wstawiono preset");
    }
  });

  promptEl?.addEventListener("input", ()=>{ updateCounter(); autoResize(); });
  promptEl?.addEventListener("change", ()=>{ updateCounter(); autoResize(); });

  imageUrlEl?.addEventListener("input", ()=> setPreview(imageUrlEl.value));
  imageUrlEl?.addEventListener("change", ()=> setPreview(imageUrlEl.value));

  btnPasteUrl?.addEventListener("click", pasteUrl);
  btnRandPrompt?.addEventListener("click", ()=>{
    const p = PRESETS[Math.floor(Math.random()*PRESETS.length)];
    setPrompt(p.text, "set");
    toastMsg("Losowy preset");
  });

  btnExport?.addEventListener("click", exportState);
  btnImport?.addEventListener("click", importState);
  btnClear?.addEventListener("click", clearState);

  btnHelp?.addEventListener("click", openHelp);
  helpClose?.addEventListener("click", closeHelp);
  helpModal?.addEventListener("click", (e)=>{ if(e.target === helpModal) closeHelp(); });

  // shortcut: Shift+? = help
  document.addEventListener("keydown", (e)=>{
    if(e.shiftKey && e.key === "?"){ e.preventDefault(); openHelp(); }
    if(e.key === "Escape"){ closeHelp(); }
  });

  toastMsg("Extras załadowane ✅");
})();
