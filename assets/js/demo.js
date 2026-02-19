(() => {
  const $ = (id) => document.getElementById(id);

  const dropZone = dropZone;
  const fileInput = fileInput;
  const uploadBtn = uploadBtn;
  const uploadNote = uploadNote;

  const imageUrlEl = image_url;
  const promptEl = prompt;
  const styleEl = style;
  const backendEl = backend;

  const generateBtn = generateBtn;
  const stopBtn = stopBtn;
  const statusEl = status;
  const logEl = log;
  const pillEl = pill;

  const videoEl = video;
  const placeholderEl = placeholder;
  const openVideoBtn = openVideoBtn;

  const jobInfoEl = jobInfo;
  const apiDot = apiDot;
  const apiText = apiText;
  const jobMini = jobMini;
  const checkApiBtn = checkApiBtn;
  const copyJobBtn = copyJobBtn;

  let stopFlag = false;
  let currentVideoUrl = "";
  let currentJobId = "";

  const STORE_KEY = "danieloza_demo_state_v3";

  function setStatus(t){ if(statusEl) statusEl.textContent = t; }
  function setPill(t){ if(pillEl) pillEl.textContent = t; }
  function log(obj){
    if(!logEl) return;
    try{
      const txt = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
      logEl.textContent = txt;
    }catch(e){
      logEl.textContent = String(obj);
    }
  }
  function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

  function loadStore(){
    try{ return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); }
    catch(_){ return {}; }
  }
  function saveStore(s){ localStorage.setItem(STORE_KEY, JSON.stringify(s || {})); }

  function showVideo(url){
    currentVideoUrl = url || "";
    if(!videoEl || !placeholderEl || !openVideoBtn) return;

    if(!url){
      videoEl.style.display = "none";
      placeholderEl.style.display = "block";
      openVideoBtn.disabled = true;
      return;
    }
    placeholderEl.style.display = "none";
    videoEl.style.display = "block";
    videoEl.src = url;
    openVideoBtn.disabled = false;
  }

  function setUploadNote(t){ if(uploadNote) uploadNote.textContent = t; }
  function setMiniJob(id){ if(jobMini) jobMini.textContent = "job: " + (id || "—"); }

  // restore state
  const s = loadStore();
  if(backendEl && s.backend) backendEl.value = s.backend;
  if(imageUrlEl && s.image_url) imageUrlEl.value = s.image_url;
  if(promptEl && s.prompt) promptEl.value = s.prompt;
  if(styleEl && s.style) styleEl.value = s.style;

  if(s.last_job_id){
    currentJobId = s.last_job_id;
    setMiniJob(currentJobId);
  }

  backendEl?.addEventListener("change", () => { const ss = loadStore(); ss.backend = backendEl.value.trim(); saveStore(ss); });
  imageUrlEl?.addEventListener("change", () => { const ss = loadStore(); ss.image_url = imageUrlEl.value.trim(); saveStore(ss); });
  promptEl?.addEventListener("change", () => { const ss = loadStore(); ss.prompt = promptEl.value; saveStore(ss); });
  styleEl?.addEventListener("change", () => { const ss = loadStore(); ss.style = styleEl.value; saveStore(ss); });

  openVideoBtn?.addEventListener("click", () => {
    if(currentVideoUrl) window.open(currentVideoUrl, "_blank", "noopener");
  });

  stopBtn?.addEventListener("click", () => {
    stopFlag = true;
    setStatus("Stopped ⛔");
    setPill("stopped");
    if(stopBtn) stopBtn.disabled = true;
    if(generateBtn) generateBtn.disabled = false;
    setTimeout(() => setStatus("Ready."), 900);
  });

  // tmpfiles upload
  async function uploadToTmpfiles(file){
    const fd = new FormData();
    fd.append("file", file, file.name);

    const r = await fetch("https://tmpfiles.org/api/v1/upload", { method:"POST", body: fd });
    const j = await r.json();
    if(!r.ok) throw new Error("Upload failed");

    const pageUrl = j?.data?.url || "";
    if(!pageUrl) throw new Error("No url from tmpfiles");

    const m = pageUrl.match(/tmpfiles\\.org\\/(\\d+)/);
    return m ? https://tmpfiles.org/dl/ : pageUrl;
  }

  async function handleFile(f){
    if(!f) return;
    if(!(f.type.includes("png") || f.type.includes("jpeg"))){
      setUploadNote("Tylko JPG/PNG");
      return;
    }
    setUploadNote("Uploading…");
    setStatus("Uploading…");

    const url = await uploadToTmpfiles(f);
    if(imageUrlEl) imageUrlEl.value = url;

    const ss = loadStore();
    ss.image_url = url;
    saveStore(ss);

    setUploadNote("Uploaded ✅");
    setStatus("Ready.");
  }

  uploadBtn?.addEventListener("click", async () => {
    try{
      const f = fileInput?.files?.[0];
      if(!f){ setUploadNote("Wybierz plik"); return; }
      await handleFile(f);
    }catch(e){
      setUploadNote("Upload failed ❌");
      setStatus("Upload failed ❌");
      log(String(e));
    }
  });

  // drag & drop
  function prevent(e){ e.preventDefault(); e.stopPropagation(); }
  ["dragenter","dragover","dragleave","drop"].forEach(ev => dropZone?.addEventListener(ev, prevent));
  dropZone?.addEventListener("dragover", () => dropZone.style.borderColor = "rgba(125,107,255,.85)");
  dropZone?.addEventListener("dragleave", () => dropZone.style.borderColor = "rgba(255,255,255,.18)");
  dropZone?.addEventListener("drop", async (e) => {
    dropZone.style.borderColor = "rgba(255,255,255,.18)";
    const f = e.dataTransfer?.files?.[0];
    try{ await handleFile(f); } catch(err){ log(String(err)); }
  });

  async function createJob(){
    const base = backendEl?.value.trim().replace(/\\/$/, "");
    const image_url = imageUrlEl?.value.trim();
    const prompt = promptEl?.value || "";
    const style = styleEl?.value || "premium";

    if(!base) throw new Error("Brak backend URL");
    if(!image_url) throw new Error("Brak image_url (wklej link albo zrób upload)");

    const featureCfg = (() => {
  try { return JSON.parse(localStorage.getItem("danieloza_demo_features_v1") || "{}"); } catch(_) { return {}; }
})();
const p = featureCfg.params || {};
const model = featureCfg.model || "kling-o1";
const safe_mode = !!(p.safe_mode);
const params = {
  duration: p.duration ? 5,
  fps: p.fps ? 30,
  aspect: p.aspect ? "9:16",
  seed: (p.seed || "").toString().trim(),
  motion: p.motion ? 55,
  quality: p.quality ? 70,
  camera: p.camera || "slow_push",
  safe_mode
};
const body = { image_url, prompt, style, model, params };
    setStatus("Submitting…");
    setPill("submitting");
    log({ request: ${base}/api/image2video, body });

    const r = await fetch(${base}/api/image2video, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
    });

    const j = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(j?.detail || HTTP );

    const job_id = j.job_id;
    if(!job_id) throw new Error("Brak job_id w odpowiedzi backendu");

    const ss = loadStore();
    ss.last_job_id = job_id;
    saveStore(ss);

    currentJobId = job_id;
    setMiniJob(job_id);

    return { job_id, raw: j };
  }

  async function pollJob(job_id){
    const base = backendEl?.value.trim().replace(/\\/$/, "");
    setStatus("Processing…");
    setPill("processing");
    if(jobInfoEl) jobInfoEl.textContent = job: ;

    for(let i=0; i<90; i++){
      if(stopFlag) throw new Error("Stopped");

      const r = await fetch(${base}/api/jobs/, { cache: "no-store" });
      const j = await r.json().catch(() => ({}));
      if(!r.ok) throw new Error(j?.detail || HTTP );

      const st = j.status || "unknown";
      const video_url = j.video_url || "";

      log(j);

      if(st === "succeed" && video_url){
        setStatus("Done ✅");
        setPill("done");
        showVideo(video_url);
        return { status: st, video_url };
      }
      if(st === "failed"){
        setStatus("Failed ❌");
        setPill("failed");
        throw new Error("Task failed");
      }

      const wait = Math.min(12000, 1800 + i * 170);
      setStatus(Processing… (poll in s));
      await sleep(wait);
    }
    throw new Error("Timeout");
  }

  generateBtn?.addEventListener("click", async () => {
    stopFlag = false;
    if(stopBtn) stopBtn.disabled = false;
    if(generateBtn) generateBtn.disabled = true;
    showVideo("");

    try{
      const { job_id } = await createJob();
      const res = await pollJob(job_id);
      currentVideoUrl = res.video_url || "";
      if(openVideoBtn) openVideoBtn.disabled = !currentVideoUrl;
    }catch(e){
      setStatus(Error: );
      setPill("error");
      if(stopBtn) stopBtn.disabled = true;
      if(generateBtn) generateBtn.disabled = false;
      log(String(e));
    }
  });

  async function checkBackend(){
    try{
      const base = backendEl?.value.trim().replace(/\\/$/, "");
      const r = await fetch(${base}/api/health, { cache: "no-store" });
      if(!r.ok) throw new Error("bad");
      apiDot?.classList.remove("bad"); apiDot?.classList.add("ok");
      if(apiText) apiText.textContent = "backend: ok";
      return true;
    }catch(e){
      apiDot?.classList.remove("ok"); apiDot?.classList.add("bad");
      if(apiText) apiText.textContent = "backend: offline";
      return false;
    }
  }

  checkApiBtn?.addEventListener("click", checkBackend);
  copyJobBtn?.addEventListener("click", async () => {
    const id = (loadStore().last_job_id || currentJobId || "");
    if(!id) return;
    try{ await navigator.clipboard.writeText(id); }catch(_){}
  });

  setInterval(checkBackend, 12000);
  checkBackend();

  document.addEventListener("keydown", (e) => {
    if(e.ctrlKey && e.key === "Enter"){
      e.preventDefault();
      generateBtn?.click();
    }
  });
})();


;(() => {
  // FEATURE_PACK_V1
  const $ = (id) => document.getElementById(id);

  const promptEl = prompt;
  const backendEl = backend;
  const logEl = log;

  const presetList = presetList;
  const promptHistory = promptHistory;
  const jobQueue = jobQueue;

  const btnFillPreset = btnFillPreset;
  const autoSaveToggle = autoSaveToggle;
  const resetStateBtn = resetStateBtn;

  const safeModeToggle = safeModeToggle;
  const demoModeToggle = demoModeToggle;

  const p_duration = p_duration;
  const p_fps = p_fps;
  const p_aspect = p_aspect;
  const p_seed = p_seed;
  const p_motion = p_motion;
  const p_quality = p_quality;
  const p_camera = p_camera;

  const clearQueueBtn = clearQueueBtn;
  const copyLogBtn = copyLogBtn;
  const wideToggle = wideToggle;
  const compactToggle = compactToggle;

  // toast
  function toast(msg){
    let t = document.getElementById("demoToast");
    if(!t){
      t = document.createElement("div");
      t.id = "demoToast";
      t.style.position = "fixed";
      t.style.right = "14px";
      t.style.bottom = "14px";
      t.style.zIndex = "9999";
      t.style.padding = "10px 12px";
      t.style.borderRadius = "12px";
      t.style.border = "1px solid rgba(255,255,255,.12)";
      t.style.background = "rgba(0,0,0,.55)";
      t.style.backdropFilter = "blur(10px)";
      t.style.color = "rgba(255,255,255,.92)";
      t.style.fontSize = "12px";
      t.style.maxWidth = "320px";
      t.style.boxShadow = "0 10px 24px rgba(0,0,0,.35)";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = "1";
    clearTimeout(window.__demoToastT);
    window.__demoToastT = setTimeout(()=>{ t.style.opacity = "0"; }, 1400);
  }

  const STORE2 = "danieloza_demo_features_v1";
  const STORE_STATE = "danieloza_demo_state_v3";

  function load(k){ try{ return JSON.parse(localStorage.getItem(k)||"{}"); }catch(_){ return {}; } }
  function save(k,v){ localStorage.setItem(k, JSON.stringify(v||{})); }

  const presets = [
    "Cinematic slow push-in, soft neon rim light, subtle smoke, high-end commercial look.",
    "Handheld street vibe, fast cuts feeling, camera shake minimal, realistic motion blur.",
    "Luxury product reveal, rotating light sweep, premium glossy reflections, clean background.",
    "Anime-inspired motion, smooth parallax, dreamy bokeh, soft bloom, vibrant highlights.",
    "Hyper-real UGC vibe: natural camera, slight imperfections, phone-like lens, good exposure.",
    "Fashion editorial: model turn, cloth simulation gentle, glossy shadows, minimal set.",
    "Action beat: rapid forward motion, dynamic zoom, strong contrast, punchy energy."
  ];

  function renderPresets(){
    if(!presetList) return;
    presetList.innerHTML = presets.map((p,i)=><div class="demoPresetItem" data-i="41">C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site\assets\js\plugins\p040.js</div>).join("");
    presetList.querySelectorAll(".demoPresetItem").forEach(el=>{
      el.addEventListener("click", ()=>{
        if(!promptEl) return;
        promptEl.value = el.textContent.trim();
        promptEl.dispatchEvent(new Event("change"));
        toast("Preset wstawiony do prompt ✅");
        pushHistory(promptEl.value);
      });
    });
  }

  function pushHistory(text){
    const cfg = load(STORE2);
    const hist = cfg.history || [];
    const t = (text||"").trim();
    if(!t) return;
    const next = [t, ...hist.filter(x=>x!==t)].slice(0, 12);
    cfg.history = next;
    save(STORE2, cfg);
    renderHistory();
  }

  function renderHistory(){
    if(!promptHistory) return;
    const cfg = load(STORE2);
    const hist = cfg.history || [];
    if(!hist.length){
      promptHistory.innerHTML = <div class="demoHistItem" style="opacity:.7; cursor:default;">Brak historii — wpisz prompt i kliknij Generate.</div>;
      return;
    }
    promptHistory.innerHTML = hist.map((p)=><div class="demoHistItem">C:\Users\syfsy\OneDrive\Desktop\DANIELOZA_AI_site\assets\js\plugins\p040.js</div>).join("");
    promptHistory.querySelectorAll(".demoHistItem").forEach(el=>{
      el.addEventListener("click", ()=>{
        if(!promptEl) return;
        promptEl.value = el.textContent.trim();
        promptEl.dispatchEvent(new Event("change"));
        toast("Wstawiono z historii ✅");
      });
    });
  }

  // queue (UI)
  function qLoad(){ return load(STORE2).queue || []; }
  function qSave(arr){ const cfg = load(STORE2); cfg.queue = arr; save(STORE2, cfg); }
  function qAdd(item){
    const q = qLoad();
    q.unshift(item);
    qSave(q.slice(0, 20));
    renderQueue();
  }
  function renderQueue(){
    if(!jobQueue) return;
    const q = qLoad();
    if(!q.length){
      jobQueue.innerHTML = <div class="demoQueueItem" style="opacity:.7; cursor:default;">Kolejka pusta.</div>;
      return;
    }
    jobQueue.innerHTML = q.map(x=><div class="demoQueueItem" data-id="">
      <div style="display:flex;justify-content:space-between;gap:10px;">
        <b></b>
        <span style="opacity:.75"></span>
      </div>
      <div style="opacity:.8;font-size:12px; margin-top:4px;"></div>
    </div>).join("");

    jobQueue.querySelectorAll(".demoQueueItem").forEach(el=>{
      el.addEventListener("click", async ()=>{
        const id = el.getAttribute("data-id");
        if(!id) return;
        try{
          await navigator.clipboard.writeText(id);
          toast("Skopiowano job_id ✅");
        }catch(_){}
      });
    });
  }

  // extra params attach: store in localStorage so main demo.js can read it
  function readParams(){
    return {
      duration: Number(p_duration?.value||5),
      fps: Number(p_fps?.value||30),
      aspect: String(p_aspect?.value||"9:16"),
      seed: String(p_seed?.value||"").trim(),
      motion: Number(p_motion?.value||55),
      quality: Number(p_quality?.value||70),
      camera: String(p_camera?.value||"slow_push"),
      safe_mode: !!safeModeToggle?.checked
    };
  }
  function saveParams(){
    const cfg = load(STORE2);
    cfg.params = readParams();
    cfg.demo_mode = !!demoModeToggle?.checked;
    cfg.auto_save = (autoSaveToggle ? !!autoSaveToggle.checked : true);
    save(STORE2, cfg);
  }
  function loadParams(){
    const cfg = load(STORE2);
    const p = cfg.params || {};
    if(p_duration && p.duration!=null) p_duration.value = p.duration;
    if(p_fps && p.fps!=null) p_fps.value = String(p.fps);
    if(p_aspect && p.aspect) p_aspect.value = p.aspect;
    if(p_seed) p_seed.value = p.seed || "";
    if(p_motion && p.motion!=null) p_motion.value = p.motion;
    if(p_quality && p.quality!=null) p_quality.value = p.quality;
    if(p_camera && p.camera) p_camera.value = p.camera;
    if(safeModeToggle) safeModeToggle.checked = !!p.safe_mode;

    if(demoModeToggle) demoModeToggle.checked = !!cfg.demo_mode;
    if(autoSaveToggle) autoSaveToggle.checked = (cfg.auto_save !== false);
  }

  // live log append helper (monkey patch if main sets logEl.textContent)
  function appendLog(line){
    if(!logEl) return;
    const prev = logEl.textContent || "";
    const next = (prev && prev !== "—") ? (prev + "\n\n" + line) : line;
    logEl.textContent = next.slice(-8000);
  }

  // clipboard paste image
  document.addEventListener("paste", async (e)=>{
    const items = e.clipboardData?.items || [];
    const img = Array.from(items).find(it => it.type && it.type.startsWith("image/"));
    if(!img) return;
    const f = img.getAsFile();
    if(!f) return;
    toast("Wklejony obraz — upload…");
    // call the same upload API as main demo (tmpfiles) without duplicating code:
    try{
      const fd = new FormData();
      fd.append("file", f, "clipboard.png");
      const r = await fetch("https://tmpfiles.org/api/v1/upload", { method:"POST", body: fd });
      const j = await r.json();
      if(!r.ok) throw new Error("upload failed");
      const pageUrl = j?.data?.url || "";
      const m = pageUrl.match(/tmpfiles\\.org\\/(\\d+)/);
      const direct = m ? https://tmpfiles.org/dl/ : pageUrl;
      const imageUrlEl = document.getElementById("image_url");
      if(imageUrlEl){
        imageUrlEl.value = direct;
        imageUrlEl.dispatchEvent(new Event("change"));
      }
      toast("Upload z clipboard ✅");
    }catch(err){
      toast("Upload z clipboard ❌");
    }
  });

  // UI toggles: wide / compact
  function applyModes(){
    document.body.classList.toggle("demo-wide", !!wideToggle?.checked);
    document.body.classList.toggle("demo-compact", !!compactToggle?.checked);
    const cfg = load(STORE2);
    cfg.ui_wide = !!wideToggle?.checked;
    cfg.ui_compact = !!compactToggle?.checked;
    save(STORE2, cfg);
  }

  // hook Generate button: store params + history + queue item stub
  const generateBtn = document.getElementById("generateBtn");
  generateBtn?.addEventListener("click", ()=>{
    saveParams();
    if(promptEl && (load(STORE2).auto_save !== false)) pushHistory(promptEl.value);

    const cfg = load(STORE2);
    const qItem = {
      job_id: (load(STORE_STATE).last_job_id || "queued_" + Date.now()),
      status: "queued",
      prompt: (promptEl?.value||"").trim()
    };
    qAdd(qItem);

    // offline demo mode: fake success if backend offline
    if(cfg.demo_mode){
      appendLog("[DEMO MODE] Fake backend: generating…");
      setTimeout(()=>{
        appendLog("[DEMO MODE] Done ✅ (fake)");
        toast("Demo mode: Done ✅");
      }, 900);
    }
  }, true);

  btnFillPreset?.addEventListener("click", ()=>{
    const p = presets[Math.floor(Math.random()*presets.length)];
    if(promptEl){
      promptEl.value = p;
      promptEl.dispatchEvent(new Event("change"));
      pushHistory(p);
      toast("Wstawiono losowy preset ✅");
    }
  });

  resetStateBtn?.addEventListener("click", ()=>{
    localStorage.removeItem(STORE2);
    toast("Zresetowano pluginy ✅");
    loadParams();
    renderHistory();
    renderQueue();
  });

  clearQueueBtn?.addEventListener("click", ()=>{
    const cfg = load(STORE2);
    cfg.queue = [];
    save(STORE2, cfg);
    renderQueue();
    toast("Kolejka wyczyszczona ✅");
  });

  copyLogBtn?.addEventListener("click", async ()=>{
    try{
      const t = (logEl?.textContent || "").trim();
      if(!t) return;
      await navigator.clipboard.writeText(t);
      toast("Log skopiowany ✅");
    }catch(_){}
  });

  [p_duration,p_fps,p_aspect,p_seed,p_motion,p_quality,p_camera,safeModeToggle,demoModeToggle,autoSaveToggle].forEach(el=>{
    el?.addEventListener("change", saveParams);
    el?.addEventListener("input", saveParams);
  });

  wideToggle?.addEventListener("change", applyModes);
  compactToggle?.addEventListener("change", applyModes);

  // init
  renderPresets();
  loadParams();
  renderHistory();
  renderQueue();

  // restore UI mode
  const cfg = load(STORE2);
  if(wideToggle) wideToggle.checked = !!cfg.ui_wide;
  if(compactToggle) compactToggle.checked = !!cfg.ui_compact;
  applyModes();

  // small hint if backend empty
  if(backendEl && !backendEl.value.trim()){
    toast("Wpisz BACKEND URL (np. http://127.0.0.1:8000)");
  }
})();


;(() => {
  // ALLFEATURES_V1
  const $ = (id) => document.getElementById(id);

  const STORE = "danieloza_demo_features_v1";
  function load(){ try{ return JSON.parse(localStorage.getItem(STORE)||"{}"); }catch(_){ return {}; } }
  function save(v){ localStorage.setItem(STORE, JSON.stringify(v||{})); }

  const imageUrlEl = image_url;
  const promptEl = prompt;
  const styleEl = style;

  const imgPreview = imgPreview;
  const imgPreviewImg = imgPreviewImg;
  const imgPreviewNote = imgPreviewNote;
  const btnUseSelectedAsset = btnUseSelectedAsset;
  const btnClearImage = btnClearImage;

  const assetsInput = assetsInput;
  const assetsList = assetsList;
  const assetsClearBtn = assetsClearBtn;
  const assetsUrlImport = assetsUrlImport;
  const assetsImportBtn = assetsImportBtn;
  const assetsCopySelectedBtn = assetsCopySelectedBtn;
  const assetsUseSelectedBtn = assetsUseSelectedBtn;

  const profileSelect = profileSelect;
  const modelSelect = modelSelect;
  const applyProfileBtn = applyProfileBtn;

  const estimateCredits = estimateCredits;
  const estimateNote = estimateNote;

  const p_duration = p_duration;
  const p_fps = p_fps;
  const p_aspect = p_aspect;
  const p_seed = p_seed;
  const p_motion = p_motion;
  const p_quality = p_quality;
  const p_camera = p_camera;
  const safeModeToggle = safeModeToggle;

  const btnDemoPresetPrompt = btnDemoPresetPrompt;
  const btnScrollTop = btnScrollTop;
  const btnPasteHint = btnPasteHint;

  function toast(msg){
    let t = document.getElementById("demoToast");
    if(!t){
      t = document.createElement("div");
      t.id = "demoToast";
      t.style.position = "fixed";
      t.style.right = "14px";
      t.style.bottom = "14px";
      t.style.zIndex = "9999";
      t.style.padding = "10px 12px";
      t.style.borderRadius = "12px";
      t.style.border = "1px solid rgba(255,255,255,.12)";
      t.style.background = "rgba(0,0,0,.55)";
      t.style.backdropFilter = "blur(10px)";
      t.style.color = "rgba(255,255,255,.92)";
      t.style.fontSize = "12px";
      t.style.maxWidth = "320px";
      t.style.boxShadow = "0 10px 24px rgba(0,0,0,.35)";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = "1";
    clearTimeout(window.__demoToastT);
    window.__demoToastT = setTimeout(()=>{ t.style.opacity = "0"; }, 1400);
  }

  // ---------- Assets (local list + URL import). Safe: no IndexedDB (simple) ----------
  function getAssets(){
    const cfg = load();
    return Array.isArray(cfg.assets) ? cfg.assets : [];
  }
  function setAssets(arr){
    const cfg = load();
    cfg.assets = arr.slice(0, 120);
    save(cfg);
  }
  function setSelected(id){
    const cfg = load();
    cfg.selected_asset_id = id || "";
    save(cfg);
  }
  function getSelected(){
    const cfg = load();
    return cfg.selected_asset_id || "";
  }

  function guessType(url){
    const u = (url||"").toLowerCase();
    if(u.match(/\\.(mp4|webm|mov|m4v)(\\?|$)/)) return "video";
    if(u.match(/\\.(png|jpg|jpeg|webp|gif)(\\?|$)/)) return "image";
    return "url";
  }

  function renderAssets(){
    if(!assetsList) return;
    const assets = getAssets();
    const sel = getSelected();

    if(!assets.length){
      assetsList.innerHTML = '<div class="assetItem" style="opacity:.7; cursor:default;">Brak assets — dodaj pliki lub importuj URL.</div>';
      return;
    }

    assetsList.innerHTML = assets.map(a => {
      const isSel = (a.id === sel);
      const thumb = (a.type === "image") ? <img class="assetThumb" src="\" alt="" />
                   : (a.type === "video") ? <div class="assetThumb" style="display:grid;place-items:center;">🎬</div>
                   : <div class="assetThumb" style="display:grid;place-items:center;">🔗</div>;
      return 
        <div class="assetItem \" data-id="\">
          \
          <div class="assetMeta">
            <div class="assetName">\</div>
            <div class="assetSub">\</div>
          </div>
        </div>
      ;
    }).join("");

    assetsList.querySelectorAll(".assetItem").forEach(el => {
      el.addEventListener("click", () => {
        const id = el.getAttribute("data-id");
        setSelected(id);
        renderAssets();
        syncPreviewFromSelected();
      });
      el.addEventListener("dblclick", () => {
        useSelectedAsset();
      });
    });
  }

  function addAssetFromUrl(url, name){
    const u = (url||"").trim();
    if(!u) return;
    const type = guessType(u);
    const id = "a_" + Math.random().toString(16).slice(2) + "_" + Date.now();
    const item = { id, url: u, type, name: (name || type) };
    const assets = getAssets();
    assets.unshift(item);
    setAssets(assets);
    setSelected(id);
  }

  // local file add: objectURL (session) + also store name/type
  function addFiles(fileList){
    const files = Array.from(fileList || []);
    if(!files.length) return;
    const assets = getAssets();
    let firstId = "";
    files.forEach(f => {
      const url = URL.createObjectURL(f);
      const type = (f.type||"").startsWith("video/") ? "video" : "image";
      const id = "f_" + Math.random().toString(16).slice(2) + "_" + Date.now();
      if(!firstId) firstId = id;
      assets.unshift({ id, url, type, name: f.name, local: true });
    });
    setAssets(assets);
    setSelected(firstId);
    toast(files.length > 1 ? Dodano assets: \ : "Dodano asset ✅");
  }

  assetsInput?.addEventListener("change", () => {
    addFiles(assetsInput.files);
    renderAssets();
    syncPreviewFromSelected();
  });

  assetsClearBtn?.addEventListener("click", () => {
    const cfg = load();
    cfg.assets = [];
    cfg.selected_asset_id = "";
    save(cfg);
    renderAssets();
    syncPreviewFromUrl("");
    toast("Assets wyczyszczone ✅");
  });

  assetsImportBtn?.addEventListener("click", () => {
    const lines = (assetsUrlImport?.value || "").split(/\\r?\\n/).map(x=>x.trim()).filter(Boolean);
    if(!lines.length){ toast("Brak URL do importu"); return; }
    lines.slice(0, 80).forEach(u => addAssetFromUrl(u, "import"));
    if(assetsUrlImport) assetsUrlImport.value = "";
    renderAssets();
    syncPreviewFromSelected();
    toast(Zaimportowano: \ ✅);
  });

  async function copySelectedAssetUrl(){
    const sel = getSelected();
    const a = getAssets().find(x => x.id === sel);
    if(!a){ toast("Nie wybrano asset"); return; }
    try{ await navigator.clipboard.writeText(a.url); toast("Skopiowano URL ✅"); }catch(_){}
  }
  assetsCopySelectedBtn?.addEventListener("click", copySelectedAssetUrl);

  function useSelectedAsset(){
    const sel = getSelected();
    const a = getAssets().find(x => x.id === sel);
    if(!a){ toast("Nie wybrano asset"); return; }
    if(imageUrlEl){
      imageUrlEl.value = a.url;
      imageUrlEl.dispatchEvent(new Event("change"));
    }
    toast("Użyto asset w IMAGE_URL ✅");
    syncPreviewFromUrl(a.url);
  }
  assetsUseSelectedBtn?.addEventListener("click", useSelectedAsset);
  btnUseSelectedAsset?.addEventListener("click", useSelectedAsset);

  // ---------- Preview binding ----------
  function syncPreviewFromUrl(url){
    const u = (url||"").trim();
    if(!imgPreviewImg || !imgPreviewNote) return;

    if(!u){
      imgPreviewImg.removeAttribute("src");
      imgPreviewImg.style.display = "none";
      imgPreviewNote.textContent = "Brak obrazu — wklej image_url lub dodaj asset";
      return;
    }

    const t = guessType(u);
    if(t !== "image"){
      imgPreviewImg.removeAttribute("src");
      imgPreviewImg.style.display = "none";
      imgPreviewNote.textContent = "Podgląd działa dla obrazów (JPG/PNG/WebP).";
      return;
    }

    imgPreviewImg.style.display = "block";
    imgPreviewImg.src = u;
    imgPreviewNote.textContent = u.length > 80 ? (u.slice(0,80) + "…") : u;
  }

  function syncPreviewFromSelected(){
    const sel = getSelected();
    const a = getAssets().find(x => x.id === sel);
    syncPreviewFromUrl(a?.url || (imageUrlEl?.value || ""));
  }

  imageUrlEl?.addEventListener("change", () => syncPreviewFromUrl(imageUrlEl.value));
  btnClearImage?.addEventListener("click", () => {
    if(imageUrlEl){
      imageUrlEl.value = "";
      imageUrlEl.dispatchEvent(new Event("change"));
    }
    toast("Wyczyszczono IMAGE_URL ✅");
  });

  // ---------- Profiles ----------
  const profiles = {
    ugc:      { style:"fast",      motion: 55, quality: 55, camera:"handheld",  prompt:"Natural UGC phone vibe, realistic lighting, subtle camera shake, authentic feel." },
    cinematic:{ style:"cinematic", motion: 45, quality: 80, camera:"slow_push",  prompt:"Cinematic premium, soft neon rim light, clean background, subtle smoke, high-end commercial look." },
    product:  { style:"premium",   motion: 35, quality: 85, camera:"static",     prompt:"Luxury product reveal, glossy reflections, light sweep, minimal set, premium polish." },
    anime:    { style:"premium",   motion: 60, quality: 70, camera:"pan",        prompt:"Anime-inspired motion, dreamy bokeh, soft bloom, vibrant highlights, smooth parallax." },
    fast:     { style:"fast",      motion: 75, quality: 60, camera:"handheld",   prompt:"Fast viral energy, punchy tempo, dynamic movement, strong contrast, crisp subject." },
    safe:     { style:"premium",   motion: 35, quality: 65, camera:"static",     prompt:"Conservative safe result, stable camera, minimal motion, clear subject, no risky content." }
  };

  function applyProfile(key){
    const p = profiles[key] || profiles.cinematic;

    // prompt
    if(promptEl){
      promptEl.value = p.prompt;
      promptEl.dispatchEvent(new Event("change"));
    }
    // style
    if(styleEl){
      styleEl.value = p.style;
      styleEl.dispatchEvent(new Event("change"));
    }

    // params (inputs)
    if(p_motion)  p_motion.value  = p.motion;
    if(p_quality) p_quality.value = p.quality;
    if(p_camera)  p_camera.value  = p.camera;

    // safe mode
    if(safeModeToggle) safeModeToggle.checked = (key === "safe");

    // persist
    const cfg = load();
    cfg.params = cfg.params || {};
    cfg.params.motion = Number(p_motion?.value||55);
    cfg.params.quality = Number(p_quality?.value||70);
    cfg.params.camera = String(p_camera?.value||"slow_push");
    cfg.params.safe_mode = !!safeModeToggle?.checked;
    cfg.profile = key;
    save(cfg);

    updateEstimate();
    toast("Profil zastosowany ✅");
  }

  applyProfileBtn?.addEventListener("click", () => applyProfile(profileSelect?.value || "cinematic"));
  profileSelect?.addEventListener("change", () => {
    const cfg = load(); cfg.profile = profileSelect.value; save(cfg);
  });

  // model persist
  modelSelect?.addEventListener("change", () => {
    const cfg = load(); cfg.model = modelSelect.value; save(cfg);
    updateEstimate();
  });

  // ---------- Estimate ----------
  function updateEstimate(){
    const dur = Number(p_duration?.value || 5);
    const fps = Number(p_fps?.value || 30);
    const q   = Number(p_quality?.value || 70);
    const motion = Number(p_motion?.value || 55);
    const aspect = String(p_aspect?.value || "9:16");
    const model  = (modelSelect?.value || "kling-o1");
    const safe   = !!safeModeToggle?.checked;

    const modelMult = model === "kling-o2" ? 1.25 : (model === "kling-turbo" ? 0.85 : 1.0);
    const fpsMult   = fps >= 60 ? 1.25 : (fps >= 30 ? 1.0 : 0.9);
    const qMult     = 0.75 + (q/100) * 0.9;        // 0.75..1.65
    const mMult     = 0.85 + (motion/100) * 0.5;   // 0.85..1.35
    const aMult     = aspect === "16:9" ? 1.05 : (aspect === "1:1" ? 0.98 : 1.0);
    const safeMult  = safe ? 0.95 : 1.0;

    // credits: przybliżenie (UI). Nie zależy od backendu.
    const credits = Math.max(1, Math.round(dur * 6 * modelMult * fpsMult * qMult * mMult * aMult * safeMult));
    if(estimateCredits) estimateCredits.textContent = credits.toString();
    if(estimateNote) estimateNote.textContent = model=, s, fps, q=, motion=, ; 
  }

  [p_duration,p_fps,p_quality,p_motion,p_aspect,p_camera,safeModeToggle].forEach(el=>{
    el?.addEventListener("input", updateEstimate);
    el?.addEventListener("change", updateEstimate);
  });

  // ---------- Persist params into STORE for main createJob patch ----------
  function persistParams(){
    const cfg = load();
    cfg.params = cfg.params || {};
    cfg.params.duration = Number(p_duration?.value||5);
    cfg.params.fps = Number(p_fps?.value||30);
    cfg.params.aspect = String(p_aspect?.value||"9:16");
    cfg.params.seed = String(p_seed?.value||"").trim();
    cfg.params.motion = Number(p_motion?.value||55);
    cfg.params.quality = Number(p_quality?.value||70);
    cfg.params.camera = String(p_camera?.value||"slow_push");
    cfg.params.safe_mode = !!safeModeToggle?.checked;
    cfg.model = modelSelect?.value || cfg.model || "kling-o1";
    save(cfg);
  }
  [p_duration,p_fps,p_aspect,p_seed,p_motion,p_quality,p_camera,safeModeToggle].forEach(el=>{
    el?.addEventListener("input", persistParams);
    el?.addEventListener("change", persistParams);
  });

  // quick buttons
  btnScrollTop?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  btnPasteHint?.addEventListener("click", () => toast("Wklej obraz: CTRL+V (clipboard)"));

  btnDemoPresetPrompt?.addEventListener("click", () => {
    const extra = [
      "Add subtle film grain, premium lighting, crisp subject, clean background.",
      "Make it feel like a real phone camera, natural exposure, authentic vibe.",
      "Slow cinematic push-in, glossy highlights, elegant shadows, minimal set."
    ];
    const pick = extra[Math.floor(Math.random()*extra.length)];
    if(promptEl){
      const base = (promptEl.value||"").trim();
      promptEl.value = base ? (base + "\n" + pick) : pick;
      promptEl.dispatchEvent(new Event("change"));
      toast("Dopisano PROMPT+ ✅");
    }
  });

  // init restore
  const cfg = load();
  if(profileSelect && cfg.profile) profileSelect.value = cfg.profile;
  if(modelSelect && cfg.model) modelSelect.value = cfg.model;

  // preview init
  renderAssets();
  syncPreviewFromSelected();
  updateEstimate();
  persistParams();

  // if no assets but there is image_url -> show preview
  if(imageUrlEl && imageUrlEl.value) syncPreviewFromUrl(imageUrlEl.value);

})();


;(() => {
  // ASSETS_INDEXEDDB_V1
  const \$ = (id) => document.getElementById(id);

  // existing controls (from your demo)
  const imageUrlEl = \image_url;
  const imgPreviewImg = \imgPreviewImg;
  const imgPreviewNote = \imgPreviewNote;

  // assets UI
  const assetsInput = \assetsInput;
  const assetsClearBtn = \assetsClearBtn;
  const assetsUrlImport = \assetsUrlImport;
  const assetsImportBtn = \assetsImportBtn;
  const assetsCopySelectedBtn = \assetsCopySelectedBtn;
  const assetsUseSelectedBtn = \assetsUseSelectedBtn;
  const assetsList = \assetsList;

  const tabAll = \tabAll;
  const tabImages = \tabImages;
  const tabVideos = \tabVideos;
  const tabFav = \tabFav;
  const assetsSearchInput = \assetsSearchInput;
  const assetsTagsInput = \assetsTagsInput;
  const assetsMetaLine = \assetsMetaLine;

  if(!assetsList) return; // not on demo page

  function toast(msg){
    let t = document.getElementById("demoToast");
    if(!t){
      t = document.createElement("div");
      t.id = "demoToast";
      t.style.position = "fixed";
      t.style.right = "14px";
      t.style.bottom = "14px";
      t.style.zIndex = "9999";
      t.style.padding = "10px 12px";
      t.style.borderRadius = "12px";
      t.style.border = "1px solid rgba(255,255,255,.12)";
      t.style.background = "rgba(0,0,0,.55)";
      t.style.backdropFilter = "blur(10px)";
      t.style.color = "rgba(255,255,255,.92)";
      t.style.fontSize = "12px";
      t.style.maxWidth = "320px";
      t.style.boxShadow = "0 10px 24px rgba(0,0,0,.35)";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = "1";
    clearTimeout(window.__demoToastT);
    window.__demoToastT = setTimeout(()=>{ t.style.opacity = "0"; }, 1400);
  }

  // ---------- IndexedDB ----------
  const DB_NAME = "danieloza_assets_db";
  const DB_VER = 1;
  const STORE = "assets";

  function openDB(){
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = (e) => {
        const db = req.result;
        if(!db.objectStoreNames.contains(STORE)){
          const os = db.createObjectStore(STORE, { keyPath: "id" });
          os.createIndex("type", "type", { unique:false });
          os.createIndex("fav", "fav", { unique:false });
          os.createIndex("name", "name", { unique:false });
          os.createIndex("ts", "ts", { unique:false });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function txStore(db, mode="readonly"){
    const tx = db.transaction(STORE, mode);
    return tx.objectStore(STORE);
  }

  async function dbPut(asset){
    const db = await openDB();
    return new Promise((res, rej) => {
      const os = txStore(db, "readwrite");
      const r = os.put(asset);
      r.onsuccess = () => res(true);
      r.onerror = () => rej(r.error);
    });
  }
  async function dbGet(id){
    const db = await openDB();
    return new Promise((res, rej) => {
      const os = txStore(db);
      const r = os.get(id);
      r.onsuccess = () => res(r.result || null);
      r.onerror = () => rej(r.error);
    });
  }
  async function dbDel(id){
    const db = await openDB();
    return new Promise((res, rej) => {
      const os = txStore(db, "readwrite");
      const r = os.delete(id);
      r.onsuccess = () => res(true);
      r.onerror = () => rej(r.error);
    });
  }
  async function dbClear(){
    const db = await openDB();
    return new Promise((res, rej) => {
      const os = txStore(db, "readwrite");
      const r = os.clear();
      r.onsuccess = () => res(true);
      r.onerror = () => rej(r.error);
    });
  }

  async function dbAll(){
    const db = await openDB();
    return new Promise((res, rej) => {
      const os = txStore(db);
      const r = os.getAll();
      r.onsuccess = () => res(r.result || []);
      r.onerror = () => rej(r.error);
    });
  }

  // ---------- helpers ----------
  function uid(prefix="a"){
    return prefix + "_" + Math.random().toString(16).slice(2) + "_" + Date.now();
  }
  function guessTypeByName(name){
    const n = (name||"").toLowerCase();
    if(n.match(/\\.(mp4|webm|mov|m4v)$/)) return "video";
    if(n.match(/\\.(png|jpg|jpeg|webp|gif)$/)) return "image";
    return "url";
  }
  function guessTypeByUrl(url){
    const u = (url||"").toLowerCase();
    if(u.match(/\\.(mp4|webm|mov|m4v)(\\?|$)/)) return "video";
    if(u.match(/\\.(png|jpg|jpeg|webp|gif)(\\?|$)/)) return "image";
    return "url";
  }
  function short(s, n=64){
    s = String(s||"");
    return s.length>n ? s.slice(0,n)+"…" : s;
  }
  function fileToDataUrl(file){
    return new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result);
      fr.onerror = () => rej(fr.error);
      fr.readAsDataURL(file);
    });
  }

  // ---------- state ----------
  const STATE_KEY = "danieloza_assets_state_v1";
  function loadState(){ try{ return JSON.parse(localStorage.getItem(STATE_KEY)||"{}"); }catch(_){ return {}; } }
  function saveState(v){ localStorage.setItem(STATE_KEY, JSON.stringify(v||{})); }

  let state = loadState();
  let activeTab = state.tab || "all";
  let query = state.q || "";
  let selectedId = state.selected || "";

  function setTab(tab){
    activeTab = tab;
    state.tab = tab;
    saveState(state);
    [tabAll,tabImages,tabVideos,tabFav].forEach(b=>{
      if(!b) return;
      b.setAttribute("aria-pressed", String(b.dataset.tab===tab));
    });
    render();
  }

  tabAll?.addEventListener("click", ()=>setTab("all"));
  tabImages?.addEventListener("click", ()=>setTab("image"));
  tabVideos?.addEventListener("click", ()=>setTab("video"));
  tabFav?.addEventListener("click", ()=>setTab("fav"));

  if(assetsSearchInput){
    assetsSearchInput.value = query;
    assetsSearchInput.addEventListener("input", () => {
      query = assetsSearchInput.value.trim().toLowerCase();
      state.q = query;
      saveState(state);
      render();
    });
  }

  function syncPreview(url){
    if(!imgPreviewImg || !imgPreviewNote) return;
    const t = guessTypeByUrl(url);
    if(t !== "image"){
      imgPreviewImg.style.display = "none";
      imgPreviewImg.removeAttribute("src");
      imgPreviewNote.textContent = t==="video" ? "Selected: video (preview wideo w panelu po prawej to kolejny krok)" : "Selected: URL";
      return;
    }
    imgPreviewImg.style.display = "block";
    imgPreviewImg.src = url;
    imgPreviewNote.textContent = short(url, 80);
  }

  async function useSelected(){
    if(!selectedId){ toast("Nie wybrano asset"); return; }
    const a = await dbGet(selectedId);
    if(!a){ toast("Asset nie istnieje"); return; }
    if(imageUrlEl){
      imageUrlEl.value = a.url;
      imageUrlEl.dispatchEvent(new Event("change"));
    }
    syncPreview(a.url);
    toast("Użyto asset w IMAGE_URL ✅");
  }

  async function copySelected(){
    if(!selectedId){ toast("Nie wybrano asset"); return; }
    const a = await dbGet(selectedId);
    if(!a){ toast("Asset nie istnieje"); return; }
    try{ await navigator.clipboard.writeText(a.url); toast("Skopiowano URL ✅"); }catch(_){}
  }

  assetsUseSelectedBtn?.addEventListener("click", useSelected);
  assetsCopySelectedBtn?.addEventListener("click", copySelected);

  // ---------- add from URL ----------
  async function addFromUrl(url){
    const u = String(url||"").trim();
    if(!u) return;
    const type = guessTypeByUrl(u);
    const id = uid("u");
    const asset = {
      id, type,
      name: "import",
      url: u,
      fav: false,
      tags: [],
      ts: Date.now()
    };
    await dbPut(asset);
    selectedId = id;
    state.selected = id; saveState(state);
  }

  assetsImportBtn?.addEventListener("click", async () => {
    const lines = (assetsUrlImport?.value || "").split(/\\r?\\n/).map(x=>x.trim()).filter(Boolean);
    if(!lines.length){ toast("Brak URL do importu"); return; }
    for(const u of lines.slice(0, 80)) await addFromUrl(u);
    if(assetsUrlImport) assetsUrlImport.value = "";
    toast("Zaimportowano ✅");
    render();
  });

  // ---------- add from files (stored as dataURL, stable) ----------
  assetsInput?.addEventListener("change", async () => {
    const files = Array.from(assetsInput.files || []);
    if(!files.length) return;
    toast("Zapisuję do biblioteki…");
    for(const f of files.slice(0, 60)){
      const dataUrl = await fileToDataUrl(f);
      const type = (f.type||"").startsWith("video/") ? "video" : "image";
      const id = uid("f");
      // For videos we still keep dataUrl (can be big). You can limit later.
      await dbPut({
        id, type,
        name: f.name || type,
        url: dataUrl,
        fav: false,
        tags: [],
        ts: Date.now()
      });
      selectedId = id;
      state.selected = id; saveState(state);
    }
    toast("Dodano pliki ✅");
    render();
  });

  // ---------- clear library ----------
  assetsClearBtn?.addEventListener("click", async () => {
    const ok = confirm("Wyczyścić CAŁĄ bibliotekę assets (IndexedDB)?");
    if(!ok) return;
    await dbClear();
    selectedId = "";
    state.selected = ""; saveState(state);
    toast("Biblioteka wyczyszczona ✅");
    render();
  });

  // ---------- tagging ----------
  assetsTagsInput?.addEventListener("keydown", async (e) => {
    if(e.key !== "Enter") return;
    e.preventDefault();
    const t = assetsTagsInput.value.trim();
    if(!t) return;
    if(!selectedId){ toast("Najpierw wybierz asset"); return; }

    const a = await dbGet(selectedId);
    if(!a) return;
    const tag = t.toLowerCase();
    a.tags = Array.isArray(a.tags) ? a.tags : [];
    if(!a.tags.includes(tag)) a.tags.push(tag);
    await dbPut(a);
    assetsTagsInput.value = "";
    toast("Dodano tag ✅");
    render();
  });

  // ---------- render ----------
  function starSvg(){
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>';
  }

  function matches(a){
    if(activeTab === "image" && a.type !== "image") return false;
    if(activeTab === "video" && a.type !== "video") return false;
    if(activeTab === "fav" && !a.fav) return false;

    if(!query) return true;
    const hay = [
      a.name || "",
      a.type || "",
      a.url || "",
      (a.tags || []).join(" ")
    ].join(" ").toLowerCase();
    return hay.includes(query);
  }

  async function toggleFav(id){
    const a = await dbGet(id);
    if(!a) return;
    a.fav = !a.fav;
    await dbPut(a);
    render();
  }

  async function removeAsset(id){
    const ok = confirm("Usunąć asset z biblioteki?");
    if(!ok) return;
    await dbDel(id);
    if(selectedId === id){
      selectedId = "";
      state.selected = ""; saveState(state);
    }
    render();
  }

  function setSelected(id){
    selectedId = id;
    state.selected = id; saveState(state);
  }

  async function render(){
    // set tabs pressed
    [tabAll,tabImages,tabVideos,tabFav].forEach(b=>{
      if(!b) return;
      b.setAttribute("aria-pressed", String(b.dataset.tab===activeTab));
    });

    const all = (await dbAll()).sort((a,b)=> (b.ts||0)-(a.ts||0));
    const list = all.filter(matches);

    if(assetsMetaLine){
      const total = all.length;
      const shown = list.length;
      assetsMetaLine.textContent = "Assets: " + shown + " / " + total;
    }

    if(!list.length){
      assetsList.innerHTML = '<div class="assetsEmptyState">Brak wyników. Dodaj plik lub importuj URL.</div>';
      return;
    }

    assetsList.innerHTML = list.map(a => {
      const isSel = (a.id === selectedId);
      const thumb = a.type==="image"
        ? <img class="assetThumb" src="\" alt="">
        : <div class="assetThumb" style="display:grid;place-items:center;">🎬</div>;

      const tags = (a.tags||[]).slice(0,6).map(t => <span class="assetTag">\</span>).join("");
      const favClass = a.fav ? "is-on" : "";

      return 
        <div class="assetItem \" data-id="\">
          \
          <div class="assetMeta">
            <div class="assetName">\</div>
            <div class="assetSub">\</div>
            <div class="assetTags">\</div>
          </div>
          <div class="assetActionsInline">
            <button class="assetFav \" title="Favorite" data-fav="\">\</button>
            <button class="assetsSmallBtn" title="Use" data-use="\">Use</button>
            <button class="assetsSmallBtn assetsDanger" title="Delete" data-del="\">Del</button>
          </div>
        </div>
      ;
    }).join("");

    assetsList.querySelectorAll(".assetItem").forEach(el => {
      el.addEventListener("click", async () => {
        const id = el.getAttribute("data-id");
        setSelected(id);
        const a = await dbGet(id);
        if(a) syncPreview(a.url);
        render();
      });
      el.addEventListener("dblclick", async () => {
        const id = el.getAttribute("data-id");
        setSelected(id);
        await useSelected();
      });
    });

    assetsList.querySelectorAll("[data-fav]").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleFav(btn.getAttribute("data-fav"));
      });
    });

    assetsList.querySelectorAll("[data-use]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        setSelected(btn.getAttribute("data-use"));
        await useSelected();
      });
    });

    assetsList.querySelectorAll("[data-del]").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeAsset(btn.getAttribute("data-del"));
      });
    });
  }

  // init
  if(assetsSearchInput) assetsSearchInput.value = query;
  setTab(activeTab);
  if(selectedId){
    dbGet(selectedId).then(a => { if(a) syncPreview(a.url); });
  }
  render();

})();
