(() => {
  // year
  const y = document.getElementById("y");
  if (y) y.textContent = new Date().getFullYear();

  // fade-in
  window.addEventListener("load", () => document.body.classList.add("loaded"));

  const hdr = document.getElementById("hdr");
  const hero = document.getElementById("hero");

  const onScroll = () => {
    const yPos = window.scrollY;

    if (hdr) {
      if (yPos > 10) hdr.classList.add("show");
      else hdr.classList.remove("show");
    }

    if (hero) {
      const h = hero.offsetHeight * 0.28;
      if (yPos > h) hero.classList.add("shrink");
      else hero.classList.remove("shrink");
    }
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // bg video rotate only if present
  const v1 = document.getElementById("bg1");
  const v2 = document.getElementById("bg2");
  if (v1 && v2) {
    let showFirst = true;
    setInterval(() => {
      showFirst = !showFirst;
      v1.style.display = showFirst ? "block" : "none";
      v2.style.display = showFirst ? "none" : "block";
    }, 8000);
  }
})();
