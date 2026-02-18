/* p038 — Fill sample values (safe) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p038"] = {
    register(core){
      try{
        function ensureBox(core, key, title){
  const mgr = core.$("plugin-manager");
  if(!mgr) return null;
  let host = core.$("pmExtrasHost");
  if(!host){
    host = document.createElement("div");
    host.id = "pmExtrasHost";
    host.style.marginTop = "12px";
    host.style.display = "grid";
    host.style.gap = "10px";
    mgr.appendChild(host);
  }
  let box = document.getElementById("box-"+key);
  if(box) return box;

  box = document.createElement("div");
  box.id = "box-"+key;
  box.style.border = "1px solid rgba(255,255,255,.10)";
  box.style.borderRadius = "14px";
  box.style.padding = "10px 12px";
  box.style.background = "rgba(255,255,255,.02)";
  box.innerHTML = `<div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
      <strong style="letter-spacing:.10em;text-transform:uppercase;font-size:12px;opacity:.9;">${title}</strong>
      <span style="font-size:12px;opacity:.75;">${key}</span>
    </div>
    <div class="row" style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;"></div>`;
  host.appendChild(box);
  return box;
}
function btn(txt){
  const b = document.createElement("button");
  b.type="button";
  b.className="pm-btn";
  b.textContent=txt;
  return b;
}
function input(ph){
  const i = document.createElement("input");
  i.type="text";
  i.placeholder=ph;
  i.style.height="38px";
  i.style.minWidth="220px";
  i.style.flex="1";
  return i;
}
function select(){
  const s = document.createElement("select");
  s.style.height="38px";
  s.style.minWidth="220px";
  return s;
}
        const box = ensureBox(core, "p038", "Quick fill");
        if(!box) return;
        const row = box.querySelector(".row");
        const b = btn("Fill sample");
        b.addEventListener("click", ()=>{
          const backend = core.backend;
          const url = core.image_url;
          const prompt = core.prompt;
          if(backend && !backend.value) backend.value = "http://127.0.0.1:8000";
          if(url && !url.value) url.value = "https://example.com/image.jpg";
          if(prompt && !prompt.value) prompt.value = "Cinematic product ad, premium lighting, subtle camera move, high detail.";
          backend?.dispatchEvent(new Event("change"));
          url?.dispatchEvent(new Event("change"));
          prompt?.dispatchEvent(new Event("input"));
          prompt?.dispatchEvent(new Event("change"));
          core.toast("Wstawiono sample ✅");
        });
        row.appendChild(b);
        core.toast("Loaded p038");
      }catch(e){ core.log({plugin:"p038", error:String(e)}); }
    }
  };
})();
