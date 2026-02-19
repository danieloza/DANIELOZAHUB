/* p077 — STUB plugin (safe no-op) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p077"] = {
    register(core){
      // Intentionally minimal: does NOT touch layout
      // You can later replace this file with a real feature.
      core.log({plugin:"p077", status:"ready"});
    }
  };
})();
