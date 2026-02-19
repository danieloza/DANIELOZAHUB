/* p150 — STUB plugin (safe no-op) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p150"] = {
    register(core){
      // Intentionally minimal: does NOT touch layout
      // You can later replace this file with a real feature.
      core.log({plugin:"p150", status:"ready"});
    }
  };
})();
