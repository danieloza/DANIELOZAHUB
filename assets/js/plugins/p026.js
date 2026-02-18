/* p026 — Ctrl+Enter triggers Generate (if #generateBtn exists) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p026"] = {
    register(core){
      try{
        const gen = core.generateBtn;
        document.addEventListener("keydown", (e)=>{
          if(e.ctrlKey && e.key === "Enter"){
            e.preventDefault();
            gen?.click();
            core.toast("Generate (Ctrl+Enter)");
          }
        });
        core.toast("Loaded p026");
      }catch(e){ core.log({plugin:"p026", error:String(e)}); }
    }
  };
})();
