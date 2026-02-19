/* p037 — Prompt history (last 5) + dropdown load */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p037"] = {
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
        const KEY="danieloza_demo_prompt_hist_v1";
        const box = ensureBox(core, "p037", "Prompt history");
        if(!box) return;
        const row = box.querySelector(".row");
        const prompt = core.prompt;
        const sel = select();
        const bLoad = btn("Load");
        row.appendChild(sel); row.appendChild(bLoad);

        function load(){ try{ return JSON.parse(localStorage.getItem(KEY)||"[]"); }catch(_){ return []; } }
        function save(a){ localStorage.setItem(KEY, JSON.stringify(a||[])); }
        function render(){
          const arr = load();
          sel.innerHTML = '<option value="">Ostatnie…</option>' + arr.map((x,i)=><option value="41"></option>).join("");
        }
        function push(){
          const t = (prompt?.value||"").trim();
          if(!t) return;
          const arr = load().filter(x=>x!==t);
          arr.unshift(t);
          save(arr.slice(0,5));
          render();
        }
        prompt?.addEventListener("change", push);
        bLoad.addEventListener("click", ()=>{
          const i = parseInt(sel.value,10);
          const arr = load();
          if(!Number.isFinite(i) || !arr[i] || !prompt) return;
          prompt.value = arr[i];
          prompt.dispatchEvent(new Event("input")); prompt.dispatchEvent(new Event("change"));
          core.toast("Loaded ✅");
        });
        render();
        core.toast("Loaded p037");
      }catch(e){ core.log({plugin:"p037", error:String(e)}); }
    }
  };
})();
