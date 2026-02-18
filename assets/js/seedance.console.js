/* seedance.console.js
   UI “konsola” w stylu Kling/ModelArk:
   - filtrowanie All/Images/Videos/Audio
   - Favorites toggle
   - Search
   - Grid/List view
   - Assets drawer
   - Biblioteka w localStorage (bez backendu)
*/

(function(){
  const $ = (s, el=document)=>el.querySelector(s);
  const $$ = (s, el=document)=>Array.from(el.querySelectorAll(s));

  const KEY = "danieloza_assets_v1";

  const state = {
    type: "all",
    favorites: false,
    view: "list",
    q: ""
  };

  function uid(){
    return "a_" + Math.random().toString(16).slice(2) + "_" + Date.now().toString(16);
  }

  function load(){
    try{
      const raw = localStorage.getItem(KEY);
      if(!raw) return seed();
      const data = JSON.parse(raw);
      if(!Array.isArray(data)) return seed();
      return data;
    }catch(e){ return seed(); }
  }

  function save(list){
    localStorage.setItem(KEY, JSON.stringify(list));
  }

  function seed(){
    const demo = [
      {id:uid(), type:"video", title:"Nano Banana — cinematic", tags:["premium","ads"], favorite:true, createdAt:Date.now()-86400000, thumbUrl:"", fileUrl:""},
      {id:uid(), type:"image", title:"Influencer AI — portrait", tags:["ugc","beauty"], favorite:false, createdAt:Date.now()-64000000, thumbUrl:"", fileUrl:""},
      {id:uid(), type:"audio", title:"SFX Hook — punchline", tags:["viral"], favorite:false, createdAt:Date.now()-22000000, thumbUrl:"", fileUrl:""}
    ];
    save(demo);
    return demo;
  }

  let assets = load();

  // ===== UI refs
  const q = $("#q");
  const favToggle = $("#favToggle");
  const favBox = $("#favBox");
  const cards = $("#cards");
  const previewText = $("#previewText");
  const quickTags = $("#quickTags");
  const drawer = $("#drawer");
  const openAssets = $("#openAssets");
  const closeAssets = $("#closeAssets");

  const viewGrid = $("#viewGrid");
  const viewList = $("#viewList");

  const gen = $("#gen");
  const clear = $("#clear");
  const log = $("#log");
  const statePill = $("#state");
  const note = $("#note");

  // ===== helpers
  function fmt(ts){
    const d = new Date(ts);
    return d.toLocaleString();
  }

  function norm(s){
    return (s||"").toString().toLowerCase().trim();
  }

  function matches(a){
    if(state.type !== "all" && a.type !== state.type) return false;
    if(state.favorites && !a.favorite) return false;
    const nq = norm(state.q);
    if(nq){
      const hay = norm(a.title) + " " + (a.tags||[]).map(norm).join(" ");
      if(!hay.includes(nq)) return false;
    }
    return true;
  }

  function renderQuickTags(){
    const tagCount = new Map();
    assets.forEach(a => (a.tags||[]).forEach(t=>{
      const k = norm(t);
      if(!k) return;
      tagCount.set(k, (tagCount.get(k)||0)+1);
    }));
    const top = Array.from(tagCount.entries())
      .sort((a,b)=>b[1]-a[1])
      .slice(0, 10)
      .map(([t,c])=>({t,c}));

    quickTags.innerHTML = top.map(x =>
      `<div class="tag" data-qtag="${x.t}">${x.t} <span style="opacity:.6">(${x.c})</span></div>`
    ).join("");

    $$(".tag[data-qtag]", quickTags).forEach(el=>{
      el.addEventListener("click", ()=>{
        state.q = el.getAttribute("data-qtag");
        q.value = state.q;
        render();
      });
    });
  }

  function render(){
    renderQuickTags();

    const filtered = assets.filter(matches)
      .sort((a,b)=>b.createdAt - a.createdAt);

    // view buttons
    viewGrid.classList.toggle("active", state.view==="grid");
    viewList.classList.toggle("active", state.view==="list");

    // favorites toggle
    favToggle.classList.toggle("on", !!state.favorites);
    favBox.textContent = state.favorites ? "✓" : "";

    if(state.view === "grid"){
      cards.className = "gridcards";
      cards.innerHTML = filtered.map(a => `
        <div class="cardx" data-id="${a.id}">
          <div class="thumb">
            <div class="badge">${a.type.toUpperCase()}</div>
            <div class="fav ${a.favorite?'on':''}" data-fav="${a.id}">${a.favorite?'★':'☆'}</div>
          </div>
          <div class="meta">
            <strong>${escapeHtml(a.title)}</strong>
            <small>${(a.tags||[]).slice(0,4).map(t=>"#"+escapeHtml(t)).join(" ")}<br>${fmt(a.createdAt)}</small>
          </div>
        </div>
      `).join("");
    } else {
      cards.className = "listcards";
      cards.innerHTML = filtered.map(a => `
        <div class="rowcard" data-id="${a.id}">
          <div class="rowthumb">
            <div class="badge" style="top:8px; left:8px">${a.type.toUpperCase()}</div>
            <div class="fav ${a.favorite?'on':''}" data-fav="${a.id}" style="top:8px; right:8px">${a.favorite?'★':'☆'}</div>
          </div>
          <div style="flex:1 1">
            <strong style="font-size:13px">${escapeHtml(a.title)}</strong>
            <div class="muted" style="margin-top:4px">
              ${(a.tags||[]).slice(0,6).map(t=>"#"+escapeHtml(t)).join(" ")}
              <span style="opacity:.5"> • ${fmt(a.createdAt)}</span>
            </div>
          </div>
          <div class="muted" style="padding:0 8px">${a.favorite ? "Favorite" : ""}</div>
        </div>
      `).join("");
    }

    // click handlers
    $$("[data-id]", cards).forEach(el=>{
      el.addEventListener("click", (ev)=>{
        const fav = ev.target && ev.target.getAttribute && ev.target.getAttribute("data-fav");
        if(fav){
          ev.preventDefault();
          toggleFav(fav);
          return;
        }
        const id = el.getAttribute("data-id");
        openPreview(id);
      });
    });
  }

  function openPreview(id){
    const a = assets.find(x=>x.id===id);
    if(!a) return;
    previewText.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
        <div>
          <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.75">${a.type}</div>
          <div style="font-size:16px;margin-top:2px"><b>${escapeHtml(a.title)}</b></div>
          <div class="muted" style="margin-top:6px">${(a.tags||[]).map(t=>"#"+escapeHtml(t)).join(" ")}</div>
          <div class="muted" style="margin-top:6px;opacity:.6">${fmt(a.createdAt)}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btnx" id="pvFav">${a.favorite ? "Unfavorite" : "Favorite"}</button>
          <button class="btnx" id="pvCopy">Copy title</button>
          <button class="btnx" id="pvDel">Delete</button>
        </div>
      </div>
    `;
    $("#pvFav")?.addEventListener("click", ()=>toggleFav(a.id));
    $("#pvCopy")?.addEventListener("click", async ()=>{
      try{ await navigator.clipboard.writeText(a.title); toast("Skopiowano tytuł ✅"); }catch(e){ toast("Nie mogę skopiować (blokada przeglądarki)."); }
    });
    $("#pvDel")?.addEventListener("click", ()=>{
      assets = assets.filter(x=>x.id!==a.id);
      save(assets);
      previewText.textContent = "Usunięto. Wybierz kolejny kafelek.";
      render();
    });
  }

  function toggleFav(id){
    const a = assets.find(x=>x.id===id);
    if(!a) return;
    a.favorite = !a.favorite;
    save(assets);
    render();
    toast(a.favorite ? "Dodano do Favorites ★" : "Usunięto z Favorites ☆");
  }

  function escapeHtml(s){
    return (s||"").replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
    }[c]));
  }

  function toast(msg){
    log.textContent = msg + "\n" + (log.textContent==="—" ? "" : log.textContent);
  }

  // ===== topbar actions
  q.addEventListener("input", ()=>{
    state.q = q.value;
    render();
  });

  $$(".chip[data-type]").forEach(ch=>{
    ch.addEventListener("click", ()=>{
      $$(".chip[data-type]").forEach(x=>x.classList.remove("active"));
      ch.classList.add("active");
      state.type = ch.getAttribute("data-type");
      render();
    });
  });

  favToggle.addEventListener("click", ()=>{
    state.favorites = !state.favorites;
    render();
  });

  viewGrid.addEventListener("click", ()=>{ state.view="grid"; render(); });
  viewList.addEventListener("click", ()=>{ state.view="list"; render(); });

  // drawer
  function setDrawer(on){
    drawer.classList.toggle("open", !!on);
    drawer.setAttribute("aria-hidden", on ? "false" : "true");
  }
  openAssets.addEventListener("click", ()=>setDrawer(true));
  closeAssets.addEventListener("click", ()=>setDrawer(false));
  drawer.addEventListener("click", (e)=>{
    const t = e.target?.getAttribute?.("data-addtag");
    if(!t) return;
    const tags = $("#tags");
    const cur = tags.value ? tags.value.split(",").map(x=>x.trim()).filter(Boolean) : [];
    if(!cur.includes(t)) cur.push(t);
    tags.value = cur.join(", ");
    toast("Dodano tag: " + t);
  });

  // ===== generator (frontend-only)
  async function fakeGenerate(payload){
    // symulacja “job”
    statePill.textContent = "WORKING…";
    note.textContent = "Symuluję job (UI).";
    await new Promise(r=>setTimeout(r, 650));
    statePill.textContent = "DONE";
    note.textContent = "Dodano do biblioteki.";
    return {
      id: uid(),
      type: "video",
      title: payload.prompt ? payload.prompt.slice(0,48) : "Seedance — result",
      tags: payload.tags,
      favorite: false,
      createdAt: Date.now(),
      thumbUrl: "",
      fileUrl: ""
    };
  }

  gen.addEventListener("click", async ()=>{
    const prompt = $("#prompt").value.trim();
    const tags = ($("#tags").value||"").split(",").map(x=>x.trim()).filter(Boolean);
    const style = $("#style").value;
    const imageUrl = $("#imageUrl").value.trim();

    const payload = {prompt, tags, style, imageUrl};
    toast("Generate: " + JSON.stringify(payload, null, 2));

    try{
      const asset = await fakeGenerate(payload);
      assets.unshift(asset);
      save(assets);
      render();
      openPreview(asset.id);
    }catch(e){
      toast("Błąd generate: " + (e?.message || e));
      statePill.textContent = "ERROR";
    }finally{
      setTimeout(()=>{ statePill.textContent="READY"; }, 900);
    }
  });

  clear.addEventListener("click", ()=>{
    $("#prompt").value = "";
    $("#imageUrl").value = "";
    $("#tags").value = "";
    toast("Wyczyszczono pola.");
  });

  // init
  render();
})();
