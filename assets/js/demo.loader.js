/* demo.loader.js — loads enabled plugins (SAFE + crash-shield) */
(function(){
  const CORE = window.DANIELOZA_CORE;
  if(!CORE) return;

  function loadScript(src){
    return new Promise((resolve, reject)=>{
      const s = document.createElement("script");
      s.src = src;
      s.defer = true;
      s.onload = resolve;
      s.onerror = () => reject(new Error("load failed: " + src));
      document.head.appendChild(s);
    });
  }

  function getEnabled(){
    const cfg = CORE.loadCfg();
    const enabled = Object.keys(cfg).filter(k => cfg[k] === true);
    return enabled;
  }

  // global registry
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};

  CORE.onReady(async ()=>{
    try{
      const enabled = getEnabled();
      if(!enabled.length){
        CORE.toast("Pluginy: 0 ON (włącz w Plugin Manager)");
        return;
      }
      const all = CORE.listPlugins();
      const map = new Map(all.map(x => [x.key, x]));
      for(const key of enabled){
        const p = map.get(key);
        if(!p) continue;

        try{
          await loadScript(p.file);
          const plugin = window.DANIELOZA_PLUGINS[key];
          if(plugin && typeof plugin.register === "function"){
            try{
              plugin.register(CORE);
            }catch(e){
              CORE.toast(key + " crashed (register)");
              CORE.log({plugin:key, error:String(e)});
            }
          }
        }catch(e){
          CORE.toast(key + " failed to load");
          CORE.log({plugin:key, error:String(e)});
        }
      }
      CORE.toast("Załadowano pluginy: " + enabled.length);
    }catch(e){
      CORE.toast("Loader error");
      CORE.log(String(e));
    }
  });
})();
