/* p034 — Network status pill inside Plugin Manager */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p034"] = {
    register(core){
      try{
        const mgr = core.plugin-manager;
        if(!mgr) return;
        if(document.getElementById("pmNetPill")) return;
        const pill = document.createElement("span");
        pill.id="pmNetPill";
        pill.style.fontSize="12px";
        pill.style.opacity=".8";
        pill.style.marginLeft="8px";
        const top = mgr.querySelector(".pm-top");
        top?.appendChild(pill);

        function upd(){
          const ok = navigator.onLine;
          pill.textContent = ok ? "net: online" : "net: offline";
          pill.style.color = ok ? "" : "#ffb3b3";
        }
        window.addEventListener("online", ()=>{ upd(); core.toast("Online ✅"); });
        window.addEventListener("offline", ()=>{ upd(); core.toast("Offline ❌"); });
        upd();
        core.toast("Loaded p034");
      }catch(e){ core.log({plugin:"p034", error:String(e)}); }
    }
  };
})();
