/* p014 — Backend health check button */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p014"] = {
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
        const box = ensureBox(core, "p014", "Backend health");
        if(!box) return;
        const row = box.querySelector(".row");
        const backend = core.backend;
        const b = btn("Check /api/health");
        const pill = document.createElement("span");
        pill.style.fontSize="12px"; pill.style.opacity=".85";
        row.appendChild(b);
        row.appendChild(pill);

        b.addEventListener("click", async ()=>{
          const base = (backend?.value||"").trim().replace(/\/$/,"");
          if(!base) return core.toast("Brak backend URL");
          const t0 = performance.now();
          try{
            const r = await fetch(${base}/api/health, {cache:"no-store"});
            const ms = Math.round(performance.now()-t0);
            pill.textContent = r.ok ? ok (ms) : error ();
            core.toast(r.ok ? "Backend OK ✅" : "Backend error");
          }catch(e){
            pill.textContent = "offline";
            core.toast("Backend offline ❌");
            core.log(String(e));
          }
        });

        core.toast("Loaded p014");
      }catch(e){ core.log({plugin:"p014", error:String(e)}); }
    }
  };
})();
