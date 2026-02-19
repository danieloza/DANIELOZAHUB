/* p039 — Intro overlay failsafe (remove if stuck) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p039"] = {
    register(core){
      try{
        setTimeout(()=>{
          const el = document.getElementById("site-intro");
          if(el){
            el.remove();
            core.toast("Intro removed (failsafe)");
          }
        }, 3500);
        core.toast("Loaded p039");
      }catch(e){ core.log({plugin:"p039", error:String(e)}); }
    }
  };
})();
