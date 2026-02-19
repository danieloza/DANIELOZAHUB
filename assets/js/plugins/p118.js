/* p118 — STUB plugin (safe no-op) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p118"] = {
    register(core){
      // Intentionally minimal: does NOT touch layout
      // You can later replace this file with a real feature.
      core.log({plugin:"p118", status:"ready"});
    }
  };
})();
