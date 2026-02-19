/* p020 — Import state from JSON file */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p020"] = {
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
        const box = ensureBox(core, "p020", "Import");
        if(!box) return;
        const row = box.querySelector(".row");
        const file = document.createElement("input");
        file.type="file"; file.accept="application/json";
        file.style.height="38px";
        const b = btn("Import JSON");
        b.addEventListener("click", ()=>file.click());

        file.addEventListener("change", async ()=>{
          const f = file.files?.[0];
          if(!f) return;
          try{
            const txt = await f.text();
            const obj = JSON.parse(txt);
            const backend = core.backend, url = core.image_url, prompt = core.prompt, style = core.style;
            if(obj.backend && backend){ backend.value=obj.backend; backend.dispatchEvent(new Event("change")); }
            if(obj.image_url && url){ url.value=obj.image_url; url.dispatchEvent(new Event("change")); }
            if(obj.prompt && prompt){ prompt.value=obj.prompt; prompt.dispatchEvent(new Event("input")); prompt.dispatchEvent(new Event("change")); }
            if(obj.style && style){ style.value=obj.style; style.dispatchEvent(new Event("change")); }
            core.toast("Zaimportowano ✅");
          }catch(e){
            core.toast("Import failed");
            core.log(String(e));
          }
        });

        row.appendChild(b);
        row.appendChild(file);
        core.toast("Loaded p020");
      }catch(e){ core.log({plugin:"p020", error:String(e)}); }
    }
  };
})();
