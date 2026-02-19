/* p081 — STUB plugin (safe no-op) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p081"] = {
    register(core){
      // Intentionally minimal: does NOT touch layout
      // You can later replace this file with a real feature.
      core.log({plugin:"p081", status:"ready"});
    }
  };
})();
