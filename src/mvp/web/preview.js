(function () {
  "use strict";

  const DEFAULT_MISSING_REASON = "暂未找到通过来源与型号核验的整机图，可补充官方图片或稍后重试联网检索。";

  const PV = (window.PV = window.PV || {});
  PV.renderers = PV.renderers || {};

  function publisherAvatar(className, brand = false) {
    const avatar = document.createElement("div");
    avatar.className = `${className} publisher-avatar`;
    avatar.setAttribute("aria-hidden", "true");
    if (brand) {
      const logo = document.createElement("img");
      logo.src = "/static/brand/huawei-mark.svg";
      logo.alt = "";
      logo.width = 48;
      logo.height = 48;
      logo.style.cssText = "width:72%;height:72%;object-fit:contain";
      avatar.appendChild(logo);
      return avatar;
    }
    const ns = "http://www.w3.org/2000/svg";
    const icon = document.createElementNS(ns, "svg");
    icon.setAttribute("viewBox", "0 0 48 48");
    const outline = document.createElementNS(ns, "path");
    outline.setAttribute("d", "M10 12.5c7-.6 20-.5 27 .1l-.3 20-27-.2.3-19.9ZM6 37l35 .3M21 33l-.5 4m8-4 .6 4M15 18l15 .2m-15 5 10 .2");
    icon.appendChild(outline);
    avatar.appendChild(icon);
    return avatar;
  }

  function imgUrl(r, im) {
    const modelId = r?.model?.id != null ? String(r.model.id) : "";
    const imName = im?.name != null ? String(im.name) : "";
    return `/img/${encodeURIComponent(modelId)}/${encodeURIComponent(imName)}`;
  }

  function imageFor(r, blockOrId) {
    const list = Array.isArray(r?.images) ? r.images : [];
    if (!blockOrId) return null;
    let targetId = "";
    if (typeof blockOrId === "string") {
      targetId = blockOrId;
    } else if (typeof blockOrId === "object") {
      targetId = blockOrId.image_id || blockOrId.id || "";
    }
    if (!targetId) return null;
    return list.find((im) => im && im.id === targetId) || null;
  }

  function figure(r, block, cls = "") {
    const im = imageFor(r, block);
    if (!im) return null;

    const fig = document.createElement("figure");
    fig.className = cls ? `pv-fig ${cls}`.trim() : "pv-fig";

    const img = document.createElement("img");
    img.src = imgUrl(r, im);
    img.alt = block?.caption || im.caption || im.name || "产品图";
    img.loading = "lazy";
    fig.appendChild(img);

    if (im.shows_device === false) {
      const badge = document.createElement("span");
      badge.className = "pv-badge";
      const kindZh =
        (window.UI && window.UI.KIND_ZH && window.UI.KIND_ZH[im.kind]) ||
        "非整机";
      badge.textContent = kindZh;
      fig.appendChild(badge);
    }

    return fig;
  }

  function missingFigure(reason, hero = false) {
    const rText =
      typeof reason === "string" && reason.trim().length > 0
        ? reason.trim()
        : DEFAULT_MISSING_REASON;

    if (hero) {
      const container = document.createElement("div");
      container.className = "pv-missing-hero";

      const label = document.createElement("div");
      label.className = "pv-missing-hero-label";
      label.textContent = "此处缺少产品主视觉";
      container.appendChild(label);

      const sub = document.createElement("div");
      sub.className = "pv-missing-hero-sub";
      sub.textContent = rText;
      container.appendChild(sub);

      return container;
    }

    const container = document.createElement("div");
    container.className = "pv-missing";

    const title = document.createElement("div");
    title.className = "pv-missing-title";
    title.textContent = "此处缺少产品图";
    container.appendChild(title);

    const desc = document.createElement("div");
    desc.className = "pv-missing-desc";
    desc.textContent = rText;
    container.appendChild(desc);

    return container;
  }

  function hasHero(r) {
    const notices = Array.isArray(r?.image_notice) ? r.image_notice : [];
    const hasNoticeNoDevice = notices.some(
      (n) => typeof n === "string" && n.includes("均不含笔记本整机")
    );
    if (hasNoticeNoDevice) {
      return false;
    }
    const list = Array.isArray(r?.images) ? r.images : [];
    return list.some((im) => im && im.shows_device !== false);
  }

  function heroReason(r) {
    const notices = Array.isArray(r?.image_notice) ? r.image_notice : [];
    if (notices.length > 0) {
      const matchDevice = notices.find(
        (n) => typeof n === "string" && n.includes("整机")
      );
      if (matchDevice) {
        return matchDevice;
      }
      if (typeof notices[0] === "string" && notices[0].trim().length > 0) {
        return notices[0];
      }
    }
    return DEFAULT_MISSING_REASON;
  }

  function para(text, cls = "") {
    const p = document.createElement("p");
    if (cls) {
      p.className = cls;
    }
    p.textContent = text != null ? String(text) : "";
    return p;
  }

  function hashTags(tags) {
    if (!Array.isArray(tags)) return [];
    return tags
      .filter((t) => t != null && String(t).trim().length > 0)
      .map((t) => {
        const span = document.createElement("span");
        span.className = "pv-hash";
        span.textContent = String(t);
        return span;
      });
  }

  function imageBlocks(r) {
    const blocks = Array.isArray(r?.article?.blocks) ? r.article.blocks : [];
    return blocks.filter((b) => b && b.type === "image");
  }

  function textBlocks(r) {
    const blocks = Array.isArray(r?.article?.blocks) ? r.article.blocks : [];
    return blocks.filter((b) => b && b.type === "text");
  }

  // Inline Lucide paths keep preview icons available in exported HTML, too.
  function icon(name) {
    const paths = {
      left: "m15 18-6-6 6-6", right: "m9 18 6-6-6-6",
      heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z",
      bookmark: "M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2Z",
      message: "M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z",
      grid: "M3 3h7v7H3Zm11 0h7v7h-7ZM3 14h7v7H3Zm11 0h7v7h-7Z",
      file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M8 13h8m-8 4h6",
      minimize: "M5 12h14", maximize: "M5 5h14v14H5Z", close: "m18 6-12 12M6 6l12 12"
    };
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", paths[name] || paths.file);
    svg.appendChild(path);
    return svg;
  }

  function desktopBar(title) {
    return UI.el("div", { className: "pv-windowbar" },
      UI.el("span", { className: "pv-window-title" }, icon("message"), title),
      UI.el("span", { className: "pv-window-controls", "aria-hidden": "true" }, icon("minimize"), icon("maximize"), icon("close")));
  }

  function renderPreview(r, options = {}) {
    const platform = r?.platform_spec?.platform || r?.task?.platform || "";
    const renderer =
      PV.renderers[platform] || PV.renderers.xiaohongshu;

    if (typeof renderer === "function") {
      return renderer(r, options);
    }

    const tip = document.createElement("div");
    tip.className = "pv-missing";

    const title = document.createElement("div");
    title.className = "pv-missing-title";
    title.textContent = "预览渲染器尚未就绪";
    tip.appendChild(title);

    const desc = document.createElement("div");
    desc.className = "pv-missing-desc";
    desc.textContent = platform
      ? `尚未加载平台「${platform}」的渲染组件。`
      : "缺少平台规范定义。";
    tip.appendChild(desc);

    return tip;
  }

  PV.imgUrl = imgUrl;
  PV.publisherAvatar = publisherAvatar;
  PV.imageFor = imageFor;
  PV.figure = figure;
  PV.missingFigure = missingFigure;
  PV.hasHero = hasHero;
  PV.heroReason = heroReason;
  PV.para = para;
  PV.hashTags = hashTags;
  PV.imageBlocks = imageBlocks;
  PV.textBlocks = textBlocks;
  PV.icon = icon;
  PV.desktopBar = desktopBar;

  window.renderPreview = renderPreview;
})();
