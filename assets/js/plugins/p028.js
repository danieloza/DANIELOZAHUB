/* p028 — Collapse/expand Plugin Manager list */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p028"] = {
    register(core){
      try{
        const mgr = core.plugin-manager;
        const list = core.pmList;
        if(!mgr || !list) return;
        if(document.getElementById("pmCollapseBtn")) return;

        const btn = document.createElement("button");
        btn.id="pmCollapseBtn";
        btn.type="button";
        btn.className="pm-btn";
        btn.textContent="Collapse";
        const top = mgr.querySelector(".pm-top");
        top?.appendChild(btn);

        const KEY = "danieloza_pm_collapsed_v1";
        function apply(){
          const on = localStorage.getItem(KEY) === "1";
          list.style.display = on ? "none" : "grid";
          btn.textContent = on ? "Expand" : "Collapse";
        }
        btn.addEventListener("click", ()=>{
          const on = localStorage.getItem(KEY) === "1";
          localStorage.setItem(KEY, on ? "0" : "1");
          apply();
        });
        apply();
        core.toast("Loaded p028");
      }catch(e){ core.log({plugin:"p028", error:String(e)}); }
    }
  };
})();
