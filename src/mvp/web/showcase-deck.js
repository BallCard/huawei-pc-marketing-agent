(function () {
  "use strict";
  const slides = Array.from(document.querySelectorAll(".deck-slide"));
  const prev = document.getElementById("deck-prev");
  const next = document.getElementById("deck-next");
  const dots = document.querySelector(".deck-dots");
  const label = document.getElementById("deck-section-label");
  const footer = document.getElementById("deck-footer-progress");
  let current = 0;
  slides.forEach((slide, index) => {
    const dot = document.createElement("button");
    dot.type = "button"; dot.className = "deck-dot"; dot.setAttribute("role", "tab");
    dot.setAttribute("aria-label", `第 ${index + 1} 页`); dot.addEventListener("click", () => show(index));
    dots.appendChild(dot);
  });
  function clamp(value) { return Math.max(0, Math.min(slides.length - 1, value)); }
  function show(index, updateHash = true) {
    current = clamp(index);
    slides.forEach((slide, item) => slide.classList.toggle("is-active", item === current));
    dots.querySelectorAll(".deck-dot").forEach((dot, item) => { const active = item === current; dot.classList.toggle("is-active", active); dot.setAttribute("aria-selected", String(active)); });
    const active = slides[current]; label.textContent = `${active.dataset.label} / ${String(current + 1).padStart(2, "0")}`; footer.textContent = `${String(current + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
    if (updateHash) history.replaceState(null, "", `#slide=${current + 1}`);
  }
  function go(step) { show(current + step); }
  prev.addEventListener("click", () => go(-1)); next.addEventListener("click", () => go(1));
  document.querySelectorAll("[data-next]").forEach((button) => button.addEventListener("click", () => go(1)));
  document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => show(Number(button.dataset.go) - 1)));
  document.addEventListener("keydown", (event) => { if (["ArrowRight", "PageDown", " "].includes(event.key)) { event.preventDefault(); go(1); } if (["ArrowLeft", "PageUp"].includes(event.key)) { event.preventDefault(); go(-1); } if (event.key === "Home") { event.preventDefault(); show(0); } if (event.key === "End") { event.preventDefault(); show(slides.length - 1); } });
  window.addEventListener("hashchange", () => { const match = location.hash.match(/slide=(\d+)/); if (match) show(Number(match[1]) - 1, false); });
  const initial = location.hash.match(/slide=(\d+)/); show(initial ? Number(initial[1]) - 1 : 0, false);
}());
