(function () {
  "use strict";
  const pages = ["create", "process", "work", "evidence"];
  let mode = "structured";
  let toastTimer;
  let previewResult = null;
  let previewDevice = null;
  const previewMedia = window.matchMedia("(max-width: 600px)");
  const refineInstructions = {
    tone: "语气更自然、更生活化，像与朋友分享，开头直接一点。保持原有产品事实，不编造亲身使用经历。",
    benefits: "优先突出与当前人群、使用场景最相关的产品卖点，把优势说得更清楚。保持原有事实依据，不新增未经核验的参数或承诺。"
  };

  function selectRefinement(preset) {
    document.querySelectorAll("[data-refine-preset]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.refinePreset === preset));
    });
  }

  function setPlatformMark(platform) {
    const mark = UI.$("work-platform-mark");
    mark.dataset.platform = platform;
    if (platform === "xiaohongshu") {
      mark.replaceChildren(UI.el("span", { className: "work-xhs-wordmark" }, "小红书"));
    } else if (platform === "wechat_article" || platform === "moments") {
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.setAttribute("viewBox", "0 0 64 64");
      const bubbles = document.createElementNS(ns, "path");
      bubbles.setAttribute("d", "M28 10C15.8 10 6 18 6 27.8c0 5.4 3 10.2 7.8 13.5l-2 7.2 8.1-4.2c2.6.9 5.3 1.3 8.1 1.3 12.2 0 22-8 22-17.8S40.2 10 28 10Z");
      bubbles.setAttribute("fill", "currentColor");
      svg.appendChild(bubbles);
      const foreground = document.createElementNS(ns, "path");
      foreground.setAttribute("d", "M60 39c0-8.2-8-14.9-18-14.9S24 30.8 24 39s8 14.9 18 14.9c2.4 0 4.7-.4 6.8-1.1l6.6 3.4-1.6-6C57.6 47.5 60 43.5 60 39Z");
      foreground.setAttribute("fill", "currentColor");
      foreground.setAttribute("stroke", "#2e9a67");
      foreground.setAttribute("stroke-width", "2.8");
      svg.appendChild(foreground);
      [[20,24],[35,24],[36,36],[49,36]].forEach(([cx,cy]) => {
        const eye = document.createElementNS(ns, "circle");
        eye.setAttribute("cx", String(cx)); eye.setAttribute("cy", String(cy));
        eye.setAttribute("r", "1.8"); eye.setAttribute("fill", "#2e9a67");
        svg.appendChild(eye);
      });
      mark.replaceChildren(svg);
    } else {
      mark.replaceChildren(PV.icon("file"));
    }
  }

  function renderPreview(result) {
    previewResult = result;
    const platform = result?.platform_spec?.platform || result?.task?.platform || "xiaohongshu";
    const poster = platform === "poster";
    const device = poster ? "poster" : previewDevice || (previewMedia.matches ? "mobile" : "desktop");
    UI.$("preview-workspace").dataset.device = device;
    UI.$("preview-toolbar").hidden = poster;
    UI.$("preview").dataset.device = device;
    const captions = { xiaohongshu: "图文笔记", wechat_article: "公众号文章", moments: "朋友圈动态" };
    UI.$("preview-device-caption").textContent = `${device === "desktop" ? "电脑端" : "手机端"} · ${captions[platform] || "图文预览"}`;
    document.querySelectorAll("[data-preview-device]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.previewDevice === device));
    });
    UI.$("preview").replaceChildren(window.renderPreview(result, { device }));
    UI.$("preview").parentElement.scrollTo(0, 0);
  }

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
    try {
      const savedDevice = sessionStorage.getItem("studio-preview-device");
      if (["desktop", "mobile"].includes(savedDevice)) previewDevice = savedDevice;
    } catch { /* Device switching also works without browser storage. */ }
    document.querySelectorAll("[data-preview-device]").forEach(button => button.addEventListener("click", () => {
      previewDevice = button.dataset.previewDevice;
      try { sessionStorage.setItem("studio-preview-device", previewDevice); } catch { /* Keep the in-memory choice. */ }
      if (previewResult) renderPreview(previewResult);
    }));
    previewMedia.addEventListener("change", () => {
      if (!previewDevice && previewResult) renderPreview(previewResult);
    });
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
    document.querySelectorAll("[data-refine-preset]").forEach(button => button.addEventListener("click", () => {
      const preset = button.dataset.refinePreset;
      selectRefinement(preset);
      UI.$("instr").value = refineInstructions[preset] || "";
      UI.$("instr").focus({ preventScroll: true });
    }));
    UI.$("instr").addEventListener("input", () => selectRefinement("custom"));
    UI.$("instr").addEventListener("keydown", event => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing) {
        event.preventDefault(); UI.$("redo").click();
      }
    });
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
    const platform = result.platform_spec?.platform || result.task?.platform || "xiaohongshu";
    const platformNames = { xiaohongshu: "小红书", wechat_article: "公众号", moments: "朋友圈", poster: "门店海报" };
    UI.$("result-platform").textContent = result.platform_spec?.platform_name || platformNames[platform] || "图文作品";
    UI.$("result-model").textContent = result.model?.name || "";
    setPlatformMark(platform);
    const verification = result.verification || {};
    const judge = verification.judge?.overall;
    const needsReview = (verification.remaining || []).length > 0 || !["pass", "ok"].includes(judge);
    UI.$("work-review-status").textContent = needsReview ? "待人工复核" : "核验通过";
    UI.$("work-review-status").dataset.state = needsReview ? "warn" : "ok";
    UI.$("instr").value = "";
    selectRefinement(null);
    navigate("work");
  }
  window.Studio = { init, navigate, setMode, getMode: () => mode, syncPlatform, syncOptions, toast, startRun, stopRun, finishRun, renderPreview };
})();
