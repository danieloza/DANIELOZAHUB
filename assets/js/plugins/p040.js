/* p040 — Scroll to top button */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p040"] = {
    register(core){
      try{
        const mgr = core.plugin-manager;
        if(!mgr) return;
        if(document.getElementById("pmTopBtn")) return;

        const b = document.createElement("button");
        b.id="pmTopBtn";
        b.type="button";
        b.className="pm-btn";
        b.textContent="Top";
        mgr.querySelector(".pm-top")?.appendChild(b);
        b.addEventListener("click", ()=>window.scrollTo({top:0, behavior:"smooth"}));
        core.toast("Loaded p040");
      }catch(e){ core.log({plugin:"p040", error:String(e)}); }
    }
  };
})();
