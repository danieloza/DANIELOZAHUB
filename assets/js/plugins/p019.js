/* p019 — Export state to downloadable JSON file */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p019"] = {
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
        const box = ensureBox(core, "p019", "Export");
        if(!box) return;
        const row = box.querySelector(".row");
        const b = btn("Download state.json");
        b.addEventListener("click", ()=>{
          const payload = {
            backend: (core.backend?.value||"").trim(),
            image_url: (core.image_url?.value||"").trim(),
            prompt: (core.prompt?.value||""),
            style: (core.style?.value||"")
          };
          const blob = new Blob([JSON.stringify(payload,null,2)], {type:"application/json"});
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "demo_state.json";
          a.click();
          setTimeout(()=>URL.revokeObjectURL(a.href), 500);
          core.toast("Pobrano ✅");
        });
        row.appendChild(b);
        core.toast("Loaded p019");
      }catch(e){ core.log({plugin:"p019", error:String(e)}); }
    }
  };
})();
