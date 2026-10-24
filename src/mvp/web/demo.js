(function () {
  "use strict";
  const caseTabs = [...document.querySelectorAll(".case-tab")];
  const casePanels = [...document.querySelectorAll(".case-panel")];
  caseTabs.forEach((tab) => tab.addEventListener("click", () => {
    const key = tab.dataset.case;
    caseTabs.forEach((item) => {
      const active = item === tab;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
    });
    casePanels.forEach((panel) => {
      const active = panel.dataset.casePanel === key;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  }));
  document.querySelectorAll(".case-panel").forEach((panel) => {
    const tabs = [...panel.querySelectorAll(".flow-tab")];
    const panels = [...panel.querySelectorAll(".flow-panel")];
    tabs.forEach((tab) => tab.addEventListener("click", () => {
      const key = tab.dataset.flow;
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
      });
      panels.forEach((item) => {
        const active = item.dataset.flowPanel === key;
        item.classList.toggle("is-active", active);
        item.hidden = !active;
      });
    }));
  });

  const requestedCase = new URLSearchParams(window.location.search).get("case");
  if (requestedCase) {
    const requestedTab = document.querySelector(`.case-tab[data-case="${CSS.escape(requestedCase)}"]`);
    if (requestedTab) requestedTab.click();
  }
}());
