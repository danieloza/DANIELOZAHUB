/* p029 — Video meta info (duration + size if possible) */
(function(){
  window.DANIELOZA_PLUGINS = window.DANIELOZA_PLUGINS || {};
  window.DANIELOZA_PLUGINS["p029"] = {
    register(core){
      try{
        function ensureBox(core, key, title){
  const mgr = core.$("plugin-manager");
  if(!mgr) return null;
  let host = core.$("pmExtrasHost");
  if(!host){
    host = document.createElement("div");
    host.id = "pmExtrasHost";
    host.style.marginTop = "12px";
    host.style.display = "grid";
    host.style.gap = "10px";
    mgr.appendChild(host);
  }
  let box = document.getElementById("box-"+key);
  if(box) return box;

  box = document.createElement("div");
  box.id = "box-"+key;
  box.style.border = "1px solid rgba(255,255,255,.10)";
  box.style.borderRadius = "14px";
  box.style.padding = "10px 12px";
  box.style.background = "rgba(255,255,255,.02)";
  box.innerHTML = `<div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
      <strong style="letter-spacing:.10em;text-transform:uppercase;font-size:12px;opacity:.9;">${title}</strong>
      <span style="font-size:12px;opacity:.75;">${key}</span>
    </div>
    <div class="row" style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;"></div>`;
  host.appendChild(box);
  return box;
}
function btn(txt){
  const b = document.createElement("button");
  b.type="button";
  b.className="pm-btn";
  b.textContent=txt;
  return b;
}
function input(ph){
  const i = document.createElement("input");
  i.type="text";
  i.placeholder=ph;
  i.style.height="38px";
  i.style.minWidth="220px";
  i.style.flex="1";
  return i;
}
function select(){
  const s = document.createElement("select");
  s.style.height="38px";
  s.style.minWidth="220px";
  return s;
}
        const box = ensureBox(core, "p029", "Video info");
        if(!box) return;
        const row = box.querySelector(".row");
        const v = core.video;
        const pill = document.createElement("span");
        pill.style.fontSize="12px"; pill.style.opacity=".85";
        row.appendChild(pill);

        function upd(){
          if(!v || !v.src) { pill.textContent="—"; return; }
          const d = isFinite(v.duration) ? v.duration.toFixed(2)+"s" : "…";
          const w = v.videoWidth ? v.videoWidth+"px" : "—";
          const h = v.videoHeight ? v.videoHeight+"px" : "—";
          pill.textContent = duration:  | ×    <!doctype html>
    <html lang="pl">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width,initial-scale=1" />
      <title>Portfolio â€” DANIELOZA.AI</title>
      <meta name="description" content="Portfolio DANIELOZA.AI">
      <link rel="stylesheet" href="assets/css/style.css" />

      <script src="assets/js/main.js" defer></script>
    </head>
    <body class="has-intro">
  



<header id="hdr">
  <a class="brand-mini" href="index.html">
    <img src="assets/img/logotype.png" alt="DANIELOZA.AI" />
    <strong>DANIELOZA.AI</strong>
  </a>
  <nav>
    <a href="oferta.html">OFERTA</a>
    <a href="demo.html">DEMO</a>
    <a href="audyt.html">AUDYT</a>
    <a href="portfolio.html">PORTFOLIO</a>
    <a href="kontakt.html">KONTAKT</a>
</nav>
</header>
<div id="site-intro" class="site-intro" aria-hidden="true">
  <div class="site-intro__inner">
    <div class="site-intro__logo">Portfolio</div>
  </div>
</div>
<script>
/* SITE INTRO SCRIPT */
(function(){
  const el = document.getElementById('site-intro');
  if(!el) return;
  requestAnimationFrame(() => el.classList.add('is-on'));
  setTimeout(() => {
    el.classList.add('is-off');
    setTimeout(() => el.remove(), 420);
  }, 1100);
})();
</script>
<div id="site-intro" class="site-intro" aria-hidden="true">
  <div class="site-intro__inner">
    <div class="site-intro__logo">Portfolio</div>
  </div>
</div></div>
  </div>
</div>
  </div>


      <main>
  <section class="page-hero">
    <div class="container">
      <div class="kicker">PORTFOLIO</div>
      <h1>Case studies</h1>
      <p class="note">Zamiast placeholderĂłw: miniatura + 1 zdanie + metryka.</p>
    </div>
  </section>

  <section>
    <h2>TOP 3</h2>
    <div class="grid">
      <div class="card"><strong>CASE #1</strong><br><br>Opis 1 zdanie.<br><br><span style="opacity:.8">np. 100k views</span></div>
      <div class="card"><strong>CASE #2</strong><br><br>Opis 1 zdanie.<br><br><span style="opacity:.8">np. 48h viral</span></div>
      <div class="card"><strong>CASE #3</strong><br><br>Opis 1 zdanie.<br><br><span style="opacity:.8">np. CTR â†‘</span></div>
    </div>
  </section>
</main>

      <footer>
  <div>Â© <span id="y"></span> DANIELOZA.AI</div>

  <div class="socialbar" aria-label="Social links">
    <a class="socialbtn" href="https://www.tiktok.com/@DANIELOZA.AI" target="_blank" rel="noreferrer" aria-label="TikTok">
      <img src="assets/img/tiktok.png" alt="">
    </a>
    <a class="socialbtn" href="https://www.instagram.com/DANIELOZA.AI" target="_blank" rel="noreferrer" aria-label="Instagram">
      <img src="assets/img/instagram.png" alt="">
    </a>
    <a class="socialbtn" href="https://www.facebook.com/" target="_blank" rel="noreferrer" aria-label="Facebook">
      <img src="assets/img/facebook.png" alt="">
    </a>
    <a class="socialbtn" href="https://www.youtube.com/@DANIELOZA.AI" target="_blank" rel="noreferrer" aria-label="YouTube">
      <img src="assets/img/youtube_play.png" alt="">
    </a>
  </div>
</footer></body>
    </html>






;
        }
        v?.addEventListener("loadedmetadata", upd);
        v?.addEventListener("durationchange", upd);
        setInterval(upd, 1500);
        core.toast("Loaded p029");
      }catch(e){ core.log({plugin:"p029", error:String(e)}); }
    }
  };
})();
