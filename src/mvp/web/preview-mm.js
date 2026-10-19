(function () {
  const UI = window.UI;
  const PV = window.PV;

  function renderMoments(r) {
    const data = r || {};
    const article = data.article || {};

    const nav = UI.el(
      "div",
      { className: "mm-nav" },
      UI.el("span", { className: "mm-nav-icon" }, "‹"),
      UI.el("span", {}, "朋友圈"),
      UI.el("span", { className: "mm-more" }, "···")
    );

    const author = UI.el("div", { className: "mm-author" }, "华为PC · 门店");
    const textKids = [];

    if (article.lead && typeof article.lead === "string" && article.lead.trim()) {
      textKids.push(UI.el("p", { className: "mm-text" }, article.lead.trim()));
    }

    const tBlocks = PV.textBlocks(data) || [];
    for (const b of tBlocks) {
      if (b && typeof b.text === "string" && b.text.trim()) {
        textKids.push(UI.el("p", { className: "mm-text" }, b.text.trim()));
      }
    }

    if (article.cta && typeof article.cta === "string" && article.cta.trim()) {
      textKids.push(UI.el("p", { className: "mm-text" }, article.cta.trim()));
    }

    const imgBlocks = PV.imageBlocks(data) || [];
    const imgCount = imgBlocks.length;
    const mediaKids = [];

    if (imgCount === 0) {
      const missing = PV.missingFigure(PV.heroReason(data), true);
      if (missing) {
        mediaKids.push(missing);
      }
    } else {
      if (!PV.hasHero(data)) {
        const missing = PV.missingFigure(PV.heroReason(data), true);
        if (missing) {
          mediaKids.push(missing);
        }
      }

      let gridCls = "mm-grid ";
      if (imgCount === 1) {
        gridCls += "n1";
      } else if (imgCount === 2) {
        gridCls += "n2";
      } else if (imgCount === 3) {
        gridCls += "n3";
      } else if (imgCount === 4) {
        gridCls += "n4";
      } else {
        gridCls += "n9";
      }

      const displayCount = Math.min(imgCount, 9);
      const cells = [];
      for (let i = 0; i < displayCount; i++) {
        const fig = PV.figure(data, imgBlocks[i], "mm-cell");
        if (fig) {
          cells.push(fig);
        }
      }

      if (cells.length > 0) {
        mediaKids.push(UI.el("div", { className: gridCls }, ...cells));
      }
    }

    const meta = UI.el(
      "div",
      { className: "mm-meta" },
      UI.el("span", { className: "mm-time" }, "刚刚"),
      UI.el("span", { className: "mm-op" })
    );

    const main = UI.el(
      "div",
      { className: "mm-main" },
      author,
      ...textKids,
      ...mediaKids,
      meta
    );

    const ava = PV.publisherAvatar("mm-ava");
    const post = UI.el("div", { className: "mm-post" }, ava, main);
    const scroll = UI.el("div", { className: "pv-scroll" }, post);

    return UI.el("div", { className: "pv-phone pv-mm" }, nav, scroll);
  }

  PV.renderers.moments = renderMoments;
})();
