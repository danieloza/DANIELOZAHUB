const $ = (id) => document.getElementById(id);

  // UI
  const dropZone = $("dropZone");
  const fileInput = $("fileInput");
  const uploadBtn = $("uploadBtn");
  const uploadNote = $("uploadNote");

  const imageUrlEl = $("image_url");
  const promptEl = $("prompt");
  const styleEl = $("style");
  const backendEl = $("backend");

  const generateBtn = $("generateBtn");
  const stopBtn = $("stopBtn");

  const statusEl = $("status");
  const logEl = $("log");

  const pillEl = $("pill");
  const videoEl = $("video");
  const placeholderEl = $("placeholder");
  const openVideoBtn = $("openVideoBtn");
  const jobInfoEl = $("jobInfo");

  const apiDot = $("apiDot");
  const apiText = $("apiText");
  const jobMini = $("jobMini");
  const checkApiBtn = $("checkApiBtn");
  const copyJobBtn = $("copyJobBtn");

  let stopFlag = false;
  let currentVideoUrl = "";
  let currentJobId = "";

  const STORE_KEY = "danieloza_demo_state_v2";

  function setStatus(t){ statusEl.textContent = t; }
  function setPill(t){ pillEl.textContent = t; }
  function log(obj){
    try{
      const txt = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
      logEl.textContent = txt;
    }catch(e){
      logEl.textContent = String(obj);
    }
  }
  function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

  function loadStore(){
    try{ return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); }catch(_){ return {}; }
  }
  function saveStore(s){
    localStorage.setItem(STORE_KEY, JSON.stringify(s || {}));
  }

  function showVideo(url){
    currentVideoUrl = url || "";
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

  function setUploadNote(t){ uploadNote.textContent = t; }
  function setMiniJob(id){ jobMini.textContent = "job: " + (id || "—"); }

  // restore state
  const s = loadStore();
  if(s.backend) backendEl.value = s.backend;
  if(s.image_url) imageUrlEl.value = s.image_url;
  if(s.prompt) promptEl.value = s.prompt;
  if(s.style) styleEl.value = s.style;
  if(s.last_job_id) { currentJobId = s.last_job_id; setMiniJob(currentJobId); }

  backendEl.addEventListener("change", () => { const ss = loadStore(); ss.backend = backendEl.value.trim(); saveStore(ss); });
  imageUrlEl.addEventListener("change", () => { const ss = loadStore(); ss.image_url = imageUrlEl.value.trim(); saveStore(ss); });
  promptEl.addEventListener("change", () => { const ss = loadStore(); ss.prompt = promptEl.value; saveStore(ss); });
  styleEl.addEventListener("change", () => { const ss = loadStore(); ss.style = styleEl.value; saveStore(ss); });

  openVideoBtn.addEventListener("click", () => {
    if(currentVideoUrl) window.open(currentVideoUrl, "_blank", "noopener");
  });

  stopBtn.addEventListener("click", () => {
    stopFlag = true;
    setStatus("Stopped ⛔");
    setPill("stopped");
    stopBtn.disabled = true;
    generateBtn.disabled = false;
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
    return m ? `https://tmpfiles.org/dl/${m[1]}` : pageUrl;
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
    imageUrlEl.value = url;
    const ss = loadStore(); ss.image_url = url; saveStore(ss);
    setUploadNote("Uploaded ✅");
    setStatus("Ready.");
  }

  uploadBtn.addEventListener("click", async () => {
    try{
      const f = fileInput.files?.[0];
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
  ["dragenter","dragover","dragleave","drop"].forEach(ev => dropZone.addEventListener(ev, prevent));
  dropZone.addEventListener("dragover", () => dropZone.style.borderColor = "rgba(125,107,255,.85)");
  dropZone.addEventListener("dragleave", () => dropZone.style.borderColor = "rgba(255,255,255,.18)");
  dropZone.addEventListener("drop", async (e) => {
    dropZone.style.borderColor = "rgba(255,255,255,.18)";
    const f = e.dataTransfer?.files?.[0];
    try{ await handleFile(f); }catch(err){ log(String(err)); }
  });

  async function createJob(){
    const base = backendEl.value.trim().replace(/\\/$/, "");
    const image_url = imageUrlEl.value.trim();
    const prompt = promptEl.value || "";
    const style = styleEl.value || "premium";

    if(!base) throw new Error("Brak backend URL");
    if(!image_url) throw new Error("Brak image_url (wklej link albo zrób upload)");

    const body = { image_url, prompt, style };

    setStatus("Submitting…");
    setPill("submitting");
    log({request: `${base}/api/image2video`, body});

    const r = await fetch(`${base}/api/image2video`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
    });

    const j = await r.json().catch(() => ({}));
    if(!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);

    const job_id = j.job_id;
    if(!job_id) throw new Error("Brak job_id w odpowiedzi backendu");

    // save last job
    const ss = loadStore();
    ss.last_job_id = job_id;
    saveStore(ss);

    currentJobId = job_id;
    setMiniJob(job_id);

    return { job_id, raw: j };
  }

  async function pollJob(job_id){
    const base = backendEl.value.trim().replace(/\\/$/, "");
    setStatus("Processing…");
    setPill("processing");
    jobInfoEl.textContent = `job: ${job_id}`;

    for(let i=0; i<80; i++){
      if(stopFlag) throw new Error("Stopped");

      const r = await fetch(`${base}/api/jobs/${encodeURIComponent(job_id)}`, { cache: "no-store" });
      const j = await r.json().catch(() => ({}));
      if(!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);

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

      const wait = Math.min(12000, 2000 + i * 180); // backoff
      setStatus(`Processing… (poll in ${Math.round(wait/1000)}s)`);
      await sleep(wait);
    }
    throw new Error("Timeout");
  }

  generateBtn.addEventListener("click", async () => {
    stopFlag = false;
    stopBtn.disabled = false;
    generateBtn.disabled = true;
    showVideo("");

    try{
      const { job_id } = await createJob();
      const res = await pollJob(job_id);
      currentVideoUrl = res.video_url || "";
      openVideoBtn.disabled = !currentVideoUrl;
    }catch(e){
      setStatus(`Error: ${String(e.message || e)}`);
      setPill("error");
      stopBtn.disabled = true;
      generateBtn.disabled = false;
      log(String(e));
    }
  });

  // health ping
  async function checkBackend(){
    try{
      const base = backendEl.value.trim().replace(/\\/$/, "");
      const r = await fetch(`${base}/api/health`, { cache: "no-store" });
      if(!r.ok) throw new Error("bad");
      apiDot.classList.remove("bad"); apiDot.classList.add("ok");
      apiText.textContent = "backend: ok";
      return true;
    }catch(e){
      apiDot.classList.remove("ok"); apiDot.classList.add("bad");
      apiText.textContent = "backend: offline";
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

  // shortcuts
  document.addEventListener("keydown", (e) => {
    if(e.ctrlKey && e.key === "Enter"){
      e.preventDefault();
      generateBtn?.click();
    }
  });
})();
</script>
