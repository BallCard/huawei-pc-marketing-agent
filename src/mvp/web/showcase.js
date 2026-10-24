(function () {
  "use strict";
  const filterButtons = [...document.querySelectorAll(".map-filter")];
  const steps = [...document.querySelectorAll(".map-step")];
  filterButtons.forEach((button) => button.addEventListener("click", () => {
    const filter = button.dataset.filter;
    filterButtons.forEach((item) => item.classList.toggle("is-active", item === button));
    steps.forEach((step) => {
      const themes = (step.dataset.themes || "").split(" ");
      step.hidden = filter !== "all" && !themes.includes(filter);
    });
  }));
}());
