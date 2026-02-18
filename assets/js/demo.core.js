/* demo.core.js — plugin core (SAFE) */
(function(){
  const CORE_KEY = "danieloza_demo_plugins_cfg_v1";

  function $(id){ return document.getElementById(id); }

  function safeJsonParse(s, fallback){
    try{ return JSON.parse(s); }catch(_){ return fallback; }
  }
  function loadCfg(){
    return safeJsonParse(localStorage.getItem(CORE_KEY) || "{}", {});
  }
  function saveCfg(cfg){
    localStorage.setItem(CORE_KEY, JSON.stringify(cfg || {}));
  }

  function toast(msg){
    const el = $("toast") || $("pluginToast");
    if(!el) return;
    el.textContent = msg;
    el.classList.add("on");
    setTimeout(()=>el.classList.remove("on"), 2200);
  }

  function log(obj){
    const el = $("log");
    if(!el) return;
    try{
      el.textContent = (typeof obj === "string") ? obj : JSON.stringify(obj, null, 2);
    }catch(e){
      el.textContent = String(obj);
    }
  }

  function onReady(fn){
    if(document.readyState === "complete" || document.readyState === "interactive"){
      setTimeout(fn, 0);
    } else {
      document.addEventListener("DOMContentLoaded", fn, {once:true});
    }
  }

  function ensureManagerUI(){
    if($("plugin-manager")) return;

    const style = document.createElement("style");
    style.textContent = `
      /* PLUGIN_MANAGER_PATCH */
      .pm-wrap{ margin-top:14px; }
      .pm-panel{ border:1px solid rgba(255,255,255,.10); border-radius:18px; padding:14px; background: rgba(255,255,255,.03); }
      .pm-top{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
      .pm-top strong{ letter-spacing:.12em; text-transform:uppercase; font-size:12px; opacity:.9; }
      .pm-top input{ height:38px; flex:1; min-width:220px; }
      .pm-btn{ height:38px; padding:0 12px; border-radius:12px; border:1px solid rgba(255,255,255,.14); background: rgba(255,255,255,.04); color:#fff; cursor:pointer; }
      .pm-btn:hover{ border-color: rgba(125,107,255,.55); }
      .pm-grid{ display:grid; gap:8px; margin-top:12px; max-height: 340px; overflow:auto; padding-right:6px; }
      .pm-item{ display:flex; justify-content:space-between; gap:10px; align-items:center; padding:10px 12px;
                border-radius:14px; border:1px solid rgba(255,255,255,.10); background: rgba(255,255,255,.02); }
      .pm-item small{ opacity:.75; }
      .pm-item code{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size:12px; opacity:.85; }
      .pm-pill{ font-size:12px; opacity:.8; }
      .pm-switch{ display:flex; align-items:center; gap:8px; }
      .pm-switch input{ transform: scale(1.1); }
      #pluginToast{ position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); padding:10px 14px; border-radius:999px;
        border:1px solid rgba(255,255,255,.14); background: rgba(10,10,12,.92); opacity:0; pointer-events:none; transition: opacity .2s ease; z-index: 9999; }
      #pluginToast.on{ opacity: 1; }
    `;
    document.head.appendChild(style);

    const toastEl = document.createElement("div");
    toastEl.id = "pluginToast";
    toastEl.textContent = "—";
    document.body.appendChild(toastEl);

    const host = document.querySelector("main") || document.body;
    const wrap = document.createElement("div");
    wrap.className = "pm-wrap";
    wrap.innerHTML = `
      <div id="plugin-manager" class="pm-panel">
        <div class="pm-top">
          <strong>PLUGIN MANAGER</strong>
          <span class="pm-pill">150 dodatków (safe)</span>
          <input id="pmSearch" type="text" placeholder="Szukaj pluginu… (np. p042)" />
          <button class="pm-btn" id="pmAllOff" type="button">All OFF</button>
          <button class="pm-btn" id="pmSafeOn" type="button">Safe ON</button>
          <button class="pm-btn" id="pmReload" type="button">Reload</button>
        </div>
        <div id="pmList" class="pm-grid"></div>
        <div class="pm-pill" style="margin-top:10px;">
          Tip: włączaj po kilka naraz. Jak coś padnie — system odetnie tylko ten plugin.
        </div>
      </div>
    `;
    host.appendChild(wrap);
  }

  function listPlugins(){
    // p001..p150
    const arr = [];
    for(let i=1;i<=150;i++){
      const id = String(i).padStart(3,"0");
      arr.push({
        key: `p${id}`,
        title: `Plugin ${id}`,
        file: `assets/js/plugins/p${id}.js`
      });
    }
    return arr;
  }

  function renderManager(){
    ensureManagerUI();
    const cfg = loadCfg();
    const list = listPlugins();
    const q = ($("pmSearch")?.value||"").toLowerCase().trim();
    const box = $("pmList");
    if(!box) return;

    const filtered = !q ? list : list.filter(x => (x.key+x.title).toLowerCase().includes(q));
    box.innerHTML = filtered.map(p => {
      const on = !!cfg[p.key];
      const state = on ? "ON" : "OFF";
      return `
        <div class="pm-item">
          <div>
            <div><code>${p.key}</code> — ${p.title}</div>
            <small>${p.file}</small>
          </div>
          <div class="pm-switch">
            <span class="pm-pill">${state}</span>
            <input type="checkbox" data-plug="${p.key}" ${on ? "checked":""} />
          </div>
        </div>
      `;
    }).join("");

    box.querySelectorAll('input[type="checkbox"][data-plug]').forEach(cb=>{
      cb.addEventListener("change", ()=>{
        const k = cb.getAttribute("data-plug");
        const c = loadCfg();
        c[k] = cb.checked;
        saveCfg(c);
        toast(`Zapisano: ${k} = ${cb.checked ? "ON":"OFF"}`);
        renderManager();
      });
    });
  }

  function wireManagerButtons(){
    ensureManagerUI();
    $("pmSearch")?.addEventListener("input", renderManager);

    $("pmAllOff")?.addEventListener("click", ()=>{
      const cfg = loadCfg();
      Object.keys(cfg).forEach(k => cfg[k] = false);
      saveCfg(cfg);
      toast("All OFF");
      renderManager();
    });

    $("pmSafeOn")?.addEventListener("click", ()=>{
      // Safe ON: włączamy tylko 10 bezpiecznych (p001..p010)
      const cfg = loadCfg();
      for(let i=1;i<=150;i++){
        const id = String(i).padStart(3,"0");
        cfg[`p${id}`] = (i <= 10);
      }
      saveCfg(cfg);
      toast("Safe ON (p001..p010)");
      renderManager();
    });

    $("pmReload")?.addEventListener("click", ()=>location.reload());
  }

  // Expose Core
  window.DANIELOZA_CORE = {
    $,
    toast,
    log,
    onReady,
    loadCfg,
    saveCfg,
    listPlugins,
    renderManager
  };

  onReady(()=>{
    renderManager();
    wireManagerButtons();
  });
})();
