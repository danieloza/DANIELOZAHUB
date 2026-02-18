/* p004 — SAFE utility plugin */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p004"] = {
    register(core){
      // tiny features that won't break anything
      const prompt = core.prompt;
      const url = core.image_url;

      if("p004" === "p001"){
        // Ctrl+K focus prompt
        document.addEventListener("keydown", (e)=>{
          if(e.ctrlKey && e.key.toLowerCase()==="k"){ e.preventDefault(); prompt?.focus(); core.toast("Focus: prompt"); }
        });
      }
      if("p004" === "p002"){
        // Ctrl+U focus url
        document.addEventListener("keydown", (e)=>{
          if(e.ctrlKey && e.key.toLowerCase()==="u"){ e.preventDefault(); url?.focus(); core.toast("Focus: image_url"); }
        });
      }
      if("p004" === "p003"){
        // Clean spaces in prompt button injected near prompt (if exists)
        if(prompt){
          const btn = document.createElement("button");
          btn.type="button";
          btn.className="pm-btn";
          btn.textContent="Clean prompt";
          btn.style.marginTop="8px";
          btn.addEventListener("click", ()=>{
            prompt.value = (prompt.value||"").replace(/\s+/g," ").trim();
            prompt.dispatchEvent(new Event("input"));
            prompt.dispatchEvent(new Event("change"));
            core.toast("Prompt cleaned");
          });
          prompt.parentElement?.appendChild(btn);
        }
      }
      if("p004" === "p004"){
        // Show chars count in toast on change
        prompt?.addEventListener("input", ()=> core.toast("Chars: " + (prompt.value||"").length));
      }
      if("p004" === "p005"){
        // Sanitize URL (trim spaces)
        url?.addEventListener("change", ()=>{ url.value=(url.value||"").trim(); });
      }
      if("p004" === "p006"){
        // Online/offline toast
        window.addEventListener("online", ()=>core.toast("Online ✅"));
        window.addEventListener("offline", ()=>core.toast("Offline ❌"));
      }
      if("p004" === "p007"){
        // Copy prompt by Ctrl+Shift+C
        document.addEventListener("keydown", async (e)=>{
          if(e.ctrlKey && e.shiftKey && e.key.toLowerCase()==="c"){
            e.preventDefault();
            try{ await navigator.clipboard.writeText(prompt?.value||""); core.toast("Prompt copied"); }catch(_){ core.toast("Clipboard blocked"); }
          }
        });
      }
      if("p004" === "p008"){
        // Auto-resize prompt
        function resize(){
          if(!prompt) return;
          prompt.style.height="auto";
          prompt.style.height=Math.min(260, prompt.scrollHeight+6)+"px";
        }
        prompt?.addEventListener("input", resize);
        resize();
      }
      if("p004" === "p009"){
        // Soft reminder if no backend set
        const backend = core.backend;
        setInterval(()=>{
          const b = (backend?.value||"").trim();
          if(!b) core.toast("Ustaw backend URL (opcjonalnie)");
        }, 60000);
      }
      if("p004" === "p010"){
        // Add "Open FAQ" shortcut Ctrl+/
        document.addEventListener("keydown", (e)=>{
          if(e.ctrlKey && e.key === "/"){ e.preventDefault(); window.location.href="faq.html"; }
        });
      }

      core.toast("Loaded p004");
    }
  };
})();
