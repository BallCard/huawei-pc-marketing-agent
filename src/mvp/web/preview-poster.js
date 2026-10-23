(function () {
  const UI = window.UI;
  const PV = window.PV;

  function isDisclaimerOrActivity(text) {
    if (!text || typeof text !== "string") {
      return false;
    }
    return (
      text.includes("活动说明") ||
      text.includes("以官方渠道为准") ||
      text.includes("建议以")
    );
  }

  function splitColon(text) {
    const idxZh = text.indexOf("：");
    const idxEn = text.indexOf(":");
    let idx = -1;
    if (idxZh !== -1 && idxEn !== -1) {
      idx = Math.min(idxZh, idxEn);
    } else if (idxZh !== -1) {
      idx = idxZh;
    } else {
      idx = idxEn;
    }

    if (idx === -1) {
      return { name: text, spec: "" };
    }
    return {
      name: text.slice(0, idx),
      spec: text.slice(idx + 1)
    };
  }

  function renderPoster(r) {
    const data = r || {};
    if (data.poster) {
      const poster = data.poster;
      const fallback = !poster.image_url && poster.fallback_image_url;
      const caption = poster.status === "passed" ? "AI 生成海报 · 成图核验通过" : poster.fallback_from ? "AI 生成海报 · 免费备选链路，待复核" : poster.image_url ? "AI 生成海报 · 待复核" : fallback ? "预制样例 · 现场生图未完成，不能作为最终成图" : "海报尚未就绪";
      return UI.el("figure", {className:"pv-generated-poster"},
        poster.image_url || fallback ? UI.el("img", {src:poster.image_url || poster.fallback_image_url, alt:fallback ? "预制营销样例，非本次最终海报" : "生成的门店海报", loading:"eager"}) :
          UI.el("div", {className:"poster-unavailable"}, UI.el("h3", {}, poster.status === "blocked" ? "先核对文案，再生成海报" : "这张海报尚未生成"),
            UI.el("p", {}, poster.error || "请查看任务记录。")),
        fallback ? UI.el("p", {className:"fallback-poster-note"}, poster.fallback_warning || poster.fallback_note || "现场生图未完成，当前为预制样例。") : null,
        UI.el("figcaption", {}, caption));
    }
    const article = data.article || {};
    const template = data.planning?.template || data.task?._template_plan;
    if (template) {
      // 样板文案预览不沿用旧版“最多三个卖点”，避免四格最后一格被截去。
      const blocks = PV.textBlocks(data);
      const product = PV.imageBlocks(data).map(b => PV.figure(data, b)).find(Boolean);
      const comic = template.id === 'C07';
      const cards = blocks.map((b, i) => UI.el('div', {className: 'template-draft-panel'},
        comic && i === 2 ? product : null, UI.el('p', {}, b.text)));
      return UI.el('div', {className: `pv-template-poster ${comic ? 'is-comic' : ''}`},
        UI.el('p', {className: 'template-draft-state'}, comic ? '四格文案分镜 · 尚未生成插画' : '样板文案预览 · 尚未生图'),
        UI.el('p', {className: 'template-draft-model'}, data.model?.name || ''),
        UI.el('div', {className: 'po-body'}, UI.el('h3', {}, article.title || ''),
          article.lead ? UI.el('p', {}, article.lead) : null,
          !comic ? product : null,
          UI.el('div', {className: 'template-draft-panels'}, ...cards),
          UI.el('p', {className: 'template-draft-cta'}, article.cta || '')));
    }

    const brand = UI.el("div", { className: "po-brand" }, "HUAWEI");
    const header = UI.el("div", { className: "po-header" }, brand);

    const rawImages = Array.isArray(data.images) ? data.images : [];
    const imgMetaMap = new Map();
    for (const im of rawImages) {
      if (im && im.id) {
        imgMetaMap.set(im.id, im);
      }
    }

    const imgBlocks = PV.imageBlocks(data) || [];
    let visualFig = null;

    if (PV.hasHero(data)) {
      for (const b of imgBlocks) {
        const meta = b && b.image_id ? imgMetaMap.get(b.image_id) : null;
        if (!meta || meta.shows_device !== false) {
          const fig = PV.figure(data, b, "");
          if (fig) {
            visualFig = fig;
            break;
          }
        }
      }
    }

    if (!visualFig) {
      visualFig = PV.missingFigure(PV.heroReason(data), true);
    }

    const visual = UI.el("div", { className: "po-visual" }, visualFig);

    const titleText = article.title && typeof article.title === "string" ? article.title : "";
    const titleEl = UI.el("h3", { className: "po-title" }, titleText);

    let subEl = null;
    if (article.lead && typeof article.lead === "string" && article.lead.trim()) {
      subEl = UI.el("p", { className: "po-sub" }, article.lead.trim());
    }

    const rawTextBlocks = PV.textBlocks(data) || [];
    const listItems = [];

    for (const tb of rawTextBlocks) {
      const text = tb && typeof tb.text === "string" ? tb.text.trim() : "";
      if (!text || isDisclaimerOrActivity(text)) {
        continue;
      }
      const { name, spec } = splitColon(text);
      const item = UI.el(
        "div",
        { className: "po-item" },
        UI.el("div", { className: "po-item-name" }, name),
        UI.el("div", { className: "po-item-spec" }, spec)
      );
      listItems.push(item);
      if (listItems.length >= 3) {
        break;
      }
    }

    const listEl = UI.el("div", { className: "po-list" }, ...listItems);

    const bodyKids = [titleEl];
    if (subEl) {
      bodyKids.push(subEl);
    }
    bodyKids.push(listEl);
    const body = UI.el("div", { className: "po-body" }, ...bodyKids);

    const ctaText =
      article.cta && typeof article.cta === "string" && article.cta.trim()
        ? article.cta.trim()
        : "到店体验真机";
    const ctaEl = UI.el("div", { className: "po-cta" }, ctaText);

    const noteTexts = [];
    for (const tb of rawTextBlocks) {
      const text = tb && typeof tb.text === "string" ? tb.text.trim() : "";
      if (isDisclaimerOrActivity(text)) {
        noteTexts.push(text);
      }
    }
    const action = UI.el("div", { className: "po-action" }, ctaEl);
    if (noteTexts.length) {
      action.appendChild(UI.el("div", { className: "po-note" }, noteTexts.join("\n")));
    }

    const qrDots = [];
    for (let i = 0; i < 15; i++) {
      qrDots.push(UI.el("span", { className: "po-qr-dot" }));
    }
    const qrFinder = UI.el("span", { className: "po-qr-finder-bl" });
    const qr = UI.el(
      "div",
      { className: "po-qr", "aria-label": "咨询二维码占位" },
      qrFinder,
      ...qrDots
    );
    qr.setAttribute("aria-label", "咨询二维码占位");

    const footer = UI.el("div", { className: "po-footer" }, action, qr);

    return UI.el("div", { className: "pv-poster" }, header, visual, body, footer);
  }

  PV.renderers.poster = renderPoster;
})();
