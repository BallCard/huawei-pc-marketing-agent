(function () {
  "use strict";

  const DEFAULT_MISSING_REASON = "知识库没有该型号的整机图，不会用其他型号顶替。";

  const PV = (window.PV = window.PV || {});
  PV.renderers = PV.renderers || {};

  function publisherAvatar(className) {
    const avatar = document.createElement("div");
    avatar.className = `${className} publisher-avatar`;
    avatar.setAttribute("aria-hidden", "true");
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

  function renderPreview(r) {
    const platform = r?.platform_spec?.platform || "";
    const renderer =
      PV.renderers[platform] || PV.renderers.xiaohongshu;

    if (typeof renderer === "function") {
      return renderer(r);
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

  window.renderPreview = renderPreview;
})();
