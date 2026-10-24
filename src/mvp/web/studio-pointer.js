(function () {
  "use strict";
  if (!window.matchMedia("(pointer: fine)").matches) return;
  const pointer = document.querySelector(".studio-pointer-spotlight");
  if (!pointer) return;
  let pointerMoved = false;
  document.addEventListener("pointermove", (event) => {
    pointerMoved = true;
    pointer.style.setProperty("--pointer-x", `${event.clientX}px`);
    pointer.style.setProperty("--pointer-y", `${event.clientY}px`);
    pointer.classList.add("is-visible");
  }, { passive: true });
  document.addEventListener("pointerleave", () => pointer.classList.remove("is-visible"));
  document.addEventListener("pointerdown", () => {
    if (!pointerMoved) return;
    pointer.classList.remove("is-clicking");
    void pointer.offsetWidth;
    pointer.classList.add("is-clicking");
  }, { passive: true });
}());
