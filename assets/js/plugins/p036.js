/* p036 — Focus mode (hides extra panels if present) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p036"] = {
    register(core){
      try{
        const KEY="danieloza_demo_focus_v1";
        const mgr = core.plugin-manager;
        if(!mgr) return;
        if(document.getElementById("pmFocusBtn")) return;

        const style = document.createElement("style");
        style.textContent = 
          body.demo-focus #pmExtrasHost{ display:none !important; }
        ;
        document.head.appendChild(style);

        const b = document.createElement("button");
        b.id="pmFocusBtn";
        b.type="button";
        b.className="pm-btn";
        b.textContent="Focus";
        mgr.querySelector(".pm-top")?.appendChild(b);

        function apply(){
          const on = localStorage.getItem(KEY)==="1";
          document.body.classList.toggle("demo-focus", on);
          b.textContent = on ? "Focus: ON" : "Focus: OFF";
        }
        b.addEventListener("click", ()=>{
          const on = localStorage.getItem(KEY)==="1";
          localStorage.setItem(KEY, on ? "0":"1");
          apply();
        });
        apply();
        core.toast("Loaded p036");
      }catch(e){ core.log({plugin:"p036", error:String(e)}); }
    }
  };
})();
