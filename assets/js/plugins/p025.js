/* p025 — Prompt templates dropdown */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p025"] = {
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
        const box = ensureBox(core, "p025", "Prompt templates");
        if(!box) return;
        const row = box.querySelector(".row");
        const prompt = core.prompt;
        const sel = select();
        const tpl = [
          {n:"Cinematic ad", t:"Cinematic premium ad, subtle camera move, soft studio lighting, high detail, clean background."},
          {n:"UGC phone", t:"Handheld phone vibe, natural light, authentic UGC look, close-up, realistic motion."},
          {n:"Macro product", t:"Macro close-up, glossy highlights, slow movement, crisp texture, appetizing detail."},
          {n:"Fashion lookbook", t:"Editorial fashion lookbook, smooth dolly in, soft studio light, premium pacing."},
          {n:"Tech futuristic", t:"Futuristic tech aesthetic, neon accents, clean reflections, smooth orbit camera, cinematic."}
        ];
        sel.innerHTML = '<option value="">Wybierz…</option>' + tpl.map((x,i)=><option value="41"></option>).join("");
        sel.addEventListener("change", ()=>{
          const i = parseInt(sel.value,10);
          if(!Number.isFinite(i) || !tpl[i] || !prompt) return;
          prompt.value = tpl[i].t;
          prompt.dispatchEvent(new Event("input")); prompt.dispatchEvent(new Event("change"));
          core.toast("Template: " + tpl[i].n);
        });
        row.appendChild(sel);
        core.toast("Loaded p025");
      }catch(e){ core.log({plugin:"p025", error:String(e)}); }
    }
  };
})();
