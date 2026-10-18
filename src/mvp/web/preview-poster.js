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
    const article = data.article || {};

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

    let noteText = "";
    for (const tb of rawTextBlocks) {
      const text = tb && typeof tb.text === "string" ? tb.text.trim() : "";
      if (isDisclaimerOrActivity(text)) {
        noteText = text;
        break;
      }
    }
    if (!noteText) {
      noteText = "产品具体配置、价格与当前活动请以官方渠道为准。";
    }
    const noteEl = UI.el("div", { className: "po-note" }, noteText);

    const action = UI.el("div", { className: "po-action" }, ctaEl, noteEl);

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
