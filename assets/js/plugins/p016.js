/* p016 — Favorites (save/load prompt) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p016"] = {
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
        const KEY = "danieloza_demo_favs_simple_v1";
        const box = ensureBox(core, "p016", "Favorites");
        if(!box) return;
        const row = box.querySelector(".row");
        const prompt = core.prompt;
        const name = input("Nazwa (opcjonalnie)");
        const sel = select();
        const bSave = btn("Save");
        const bLoad = btn("Load");
        const bDel  = btn("Delete");
        row.appendChild(name); row.appendChild(bSave); row.appendChild(sel); row.appendChild(bLoad); row.appendChild(bDel);

        function load(){ try{ return JSON.parse(localStorage.getItem(KEY)||"[]"); }catch(_){ return []; } }
        function save(arr){ localStorage.setItem(KEY, JSON.stringify(arr||[])); }
        function render(){
          const arr = load();
          sel.innerHTML = '<option value="">Ulubione…</option>' + arr.map((x,i)=><option value="41"></option>).join("");
        }
        bSave.addEventListener("click", ()=>{
          const text = (prompt?.value||"").trim();
          if(!text) return core.toast("Prompt pusty");
          const arr = load();
          const nm = (name.value||"").trim() || ("fav " + new Date().toLocaleString());
          const next = [{name:nm, text, t:Date.now()}].concat(arr.filter(x=>x.name!==nm)).slice(0,30);
          save(next); render(); name.value=""; core.toast("Saved ✅");
        });
        bLoad.addEventListener("click", ()=>{
          const i = parseInt(sel.value, 10);
          const arr = load();
          if(!Number.isFinite(i) || !arr[i]) return;
          if(prompt){ prompt.value = arr[i].text; prompt.dispatchEvent(new Event("input")); prompt.dispatchEvent(new Event("change")); }
          core.toast("Loaded ✅");
        });
        bDel.addEventListener("click", ()=>{
          const i = parseInt(sel.value, 10);
          const arr = load();
          if(!Number.isFinite(i) || !arr[i]) return;
          const nm = arr[i].name;
          arr.splice(i,1); save(arr); render(); core.toast("Deleted: " + nm);
        });
        render();
        core.toast("Loaded p016");
      }catch(e){ core.log({plugin:"p016", error:String(e)}); }
    }
  };
})();
