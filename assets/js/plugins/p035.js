/* p035 — Compact mode toggle (adds body class) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p035"] = {
    register(core){
      try{
        const KEY="danieloza_demo_compact_v1";
        const mgr = core.plugin-manager;
        if(!mgr) return;
        if(document.getElementById("pmCompactBtn")) return;

        const style = document.createElement("style");
        style.textContent = 
          body.demo-compact .panel{ padding:12px !important; }
          body.demo-compact .grid{ gap:12px !important; }
        ;
        document.head.appendChild(style);

        const b = document.createElement("button");
        b.id="pmCompactBtn";
        b.type="button";
        b.className="pm-btn";
        b.textContent="Compact";
        mgr.querySelector(".pm-top")?.appendChild(b);

        function apply(){
          const on = localStorage.getItem(KEY)==="1";
          document.body.classList.toggle("demo-compact", on);
          b.textContent = on ? "Compact: ON" : "Compact: OFF";
        }
        b.addEventListener("click", ()=>{
          const on = localStorage.getItem(KEY)==="1";
          localStorage.setItem(KEY, on ? "0":"1");
          apply();
        });
        apply();
        core.toast("Loaded p035");
      }catch(e){ core.log({plugin:"p035", error:String(e)}); }
    }
  };
})();
