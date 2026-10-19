(function () {
  "use strict";
  const pages = ["create", "process", "work", "evidence"];
  let mode = "structured";
  let toastTimer;

  function navigate(page, focus = true) {
    if (!pages.includes(page)) page = "create";
    pages.forEach(name => {
      UI.$(`page-${name}`).hidden = name !== page;
      const button = UI.$(`tab-${name}`);
      button.setAttribute("aria-selected", String(name === page));
      button.tabIndex = name === page ? 0 : -1;
    });
    history.replaceState(null, "", `#${page}`);
    if (focus) UI.$(`page-${page}`).focus({ preventScroll: true });
  }
  function setMode(next) {
    mode = next === "sentence" ? "sentence" : "structured";
    document.querySelectorAll("[data-input-mode]").forEach(button => {
      const active = button.dataset.inputMode === mode;
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    UI.$("structured-fields").hidden = mode !== "structured";
    UI.$("sentence-fields").hidden = mode !== "sentence";
    UI.$("form-error").hidden = true;
  }
  function syncPlatform() {
    document.querySelectorAll("[data-platform]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.platform === UI.$("platform").value)));
  }
  function syncOptions() {
    const constraints = UI.$("constraints").value.trim();
    const speed = UI.$("speed").value === "fast" ? "快速创作" : "质量优先";
    UI.$("open-options").title = `${constraints || "不限内容"} · ${speed}`;
  }
  function toast(message) {
    clearTimeout(toastTimer);
    UI.$("toast").textContent = message;
    UI.$("toast").hidden = false;
    toastTimer = setTimeout(() => { UI.$("toast").hidden = true; }, 2400);
  }
  function init() {
    const welcome = UI.$("welcome");
    const surfaces = [document.querySelector(".site-header"), UI.$("workspace")];
    let welcomed = false;
    try { welcomed = sessionStorage.getItem("studio-welcomed") === "1" || !!sessionStorage.getItem("studio-active-job"); } catch { /* Storage can be disabled by the browser. */ }
    function enter() {
      if (welcome.hidden || welcome.classList.contains("is-leaving")) return;
      try { sessionStorage.setItem("studio-welcomed", "1"); } catch { /* Welcome still works without storage. */ }
      welcome.classList.add("is-leaving");
      surfaces.forEach(surface => { surface.inert = false; });
      const finish = () => { welcome.hidden = true; UI.$("page-create").focus({preventScroll: true}); };
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) finish();
      else setTimeout(finish, 350);
    }
    welcome.hidden = welcomed;
    surfaces.forEach(surface => { surface.inert = !welcomed; });
    UI.$("enter-studio").addEventListener("click", enter);
    document.querySelectorAll("[data-page]").forEach(button => button.addEventListener("click", () => navigate(button.dataset.page, false)));
    document.querySelectorAll("[data-nav]").forEach(button => button.addEventListener("click", () => navigate(button.dataset.nav)));
    window.addEventListener("hashchange", () => navigate(location.hash.slice(1)));
    document.querySelectorAll("[data-input-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.inputMode)));
    document.querySelectorAll("[data-platform]").forEach(button => button.addEventListener("click", () => { UI.$("platform").value = button.dataset.platform; syncPlatform(); }));
    document.querySelectorAll("[data-insight]").forEach(button => button.addEventListener("click", () => {
      document.querySelectorAll("[data-insight]").forEach(tab => {
        const active = tab === button;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
        UI.$(`insight-${tab.dataset.insight}`).hidden = !active;
      });
    }));
    document.querySelectorAll('[role="tablist"]').forEach(list => list.addEventListener("keydown", event => {
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
      const tabs = Array.from(list.querySelectorAll('[role="tab"]'));
      const index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].click();
      tabs[next].focus({ preventScroll: true });
    }));
    UI.$("open-presets").addEventListener("click", () => UI.$("presets-dialog").showModal());
    UI.$("open-options").addEventListener("click", () => UI.$("options-dialog").showModal());
    UI.$("save-options").addEventListener("click", () => { syncOptions(); UI.$("options-dialog").close(); });
    document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
    document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    }));
    UI.$("options-dialog").addEventListener("close", syncOptions);
    UI.$("instr").addEventListener("keydown", event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); UI.$("redo").click(); } });
    UI.$("flow").appendChild(window.buildFlow([], false));
    navigate(location.hash.slice(1) || "create", false);
  }
  function startRun() {
    UI.$("work-empty").hidden = false;
    UI.$("evidence-empty").hidden = false;
    UI.$("insights").hidden = true;
    UI.$("view-result").hidden = true;
    UI.$("process-title").textContent = "好内容，正在成形。";
    document.querySelector(".nav-indicator").hidden = false;
    navigate("process");
  }
  function stopRun() { document.querySelector(".nav-indicator").hidden = true; }
  function finishRun(result) {
    stopRun();
    UI.$("step-dialog").close();
    UI.$("process-title").textContent = "作品已就绪。";
    UI.$("work-empty").hidden = true;
    UI.$("evidence-empty").hidden = true;
    UI.$("insights").hidden = false;
    UI.$("view-result").hidden = false;
    UI.$("result-platform").textContent = result.platform_spec?.platform_name || "图文作品";
    UI.$("result-model").textContent = result.model?.name || "";
    UI.$("instr").value = "";
    navigate("work");
  }
  window.Studio = { init, navigate, setMode, getMode: () => mode, syncPlatform, syncOptions, toast, startRun, stopRun, finishRun };
})();
