(function () {
  "use strict";

  const UI = window.UI;
  const PV = window.PV;
  if (!UI || !PV) return;

  function renderWx(r, options = {}) {
    const desktop = options.device === "desktop";
    const data = r || {};
    const article = data.article || {};
    const blocks = Array.isArray(article.blocks) ? article.blocks : [];

    // 1. .wx-nav
    const navBack = UI.el("span", { className: "wx-nav-back" }, "‹");
    const navTitle = UI.el("span", null, "公众号");
    const navDots = UI.el("span", { className: "wx-nav-dots" }, "···");
    const nav = UI.el("div", { className: "wx-nav" }, navBack, navTitle, navDots);

    // 2. .wx-article
    const articleEl = UI.el("div", { className: "wx-article" });

    if (article.title) {
      articleEl.appendChild(UI.el("h3", { className: "wx-title" }, article.title));
    }

    const author = UI.el("span", { className: "wx-author" }, "华为PC选购指南");
    const origBadge = UI.el("span", { className: "wx-badge-orig" }, "原创");
    const dateText = document.createTextNode("今天");
    const meta = UI.el("div", { className: "wx-meta" }, author, origBadge, dateText);
    articleEl.appendChild(meta);

    if (article.lead) {
      articleEl.appendChild(UI.el("blockquote", { className: "wx-lead" }, article.lead));
    }

    const hasHero = typeof PV.hasHero === "function" ? PV.hasHero(data) : true;
    const heroReason = typeof PV.heroReason === "function" ? PV.heroReason(data) : "缺整机图";

    if (!hasHero && typeof PV.missingFigure === "function") {
      const mf = PV.missingFigure(heroReason, true);
      if (mf) articleEl.appendChild(mf);
    }

    // 3. 正文 blocks
    blocks.forEach(function (b) {
      if (!b) return;
      if (b.type === "image") {
        const fig = PV.figure(data, b, "wx-fig");
        if (fig) {
          if (b.caption && !fig.querySelector(".wx-caption")) {
            fig.appendChild(UI.el("figcaption", { className: "wx-caption" }, b.caption));
          }
          articleEl.appendChild(fig);
        }
      } else if (b.type === "text" && b.text) {
        articleEl.appendChild(UI.el("p", { className: "wx-p" }, b.text));
      }
    });

    // 4. 文末 .wx-cta
    if (article.cta && typeof article.cta === "string" && article.cta.trim()) {
      const ctaTitle = UI.el("div", { className: "wx-cta-title" }, "预约体验 / 到店核对");
      const ctaDesc = UI.el("div", { className: "wx-cta-desc" }, article.cta.trim());
      const ctaBtn = UI.el("button", { type: "button", className: "wx-cta-btn" }, "查看门店");
      const ctaEl = UI.el("div", { className: "wx-cta" }, ctaTitle, ctaDesc, ctaBtn);
      articleEl.appendChild(ctaEl);
    }

    // 5. .wx-footer
    const statRead = UI.el("span", { className: "wx-stat-read" }, "阅读 1.2 万");
    const statActions = UI.el(
      "div",
      { className: "wx-stat-actions" },
      UI.el("span", { className: "wx-action-item" }, "阅读"),
      UI.el("span", { className: "wx-action-item" }, "在看"),
      UI.el("span", { className: "wx-action-item" }, "点赞")
    );
    const stats = UI.el("div", { className: "wx-stats" }, statRead, statActions);
    const footer = UI.el("div", { className: "wx-footer" }, stats);

    // 根容器
    let root;
    if (desktop) {
      const account = UI.el("aside", { className: "wx-account" }, PV.publisherAvatar("wx-account-avatar", true),
        UI.el("b", {}, "华为PC选购指南"), UI.el("span", {}, "公众号"));
      const page = UI.el("div", { className: "wx-desktop-page" },
        UI.el("div", { className: "wx-reading-column" }, articleEl, footer), account);
      root = UI.el("div", { className: "pv-desktop pv-wx" },
        PV.desktopBar("微信 · 公众号"), UI.el("div", { className: "pv-scroll wx-desktop-scroll" }, page));
    } else {
      // 手机预览保持一页设备框，文章正文在设备内滚动，避免撑开外层工作区。
      root = UI.el("div", { className: "pv-phone pv-wx wide" }, nav,
        UI.el("div", { className: "pv-scroll wx-mobile-scroll" }, articleEl, footer));
    }

    return root;
  }

  PV.renderers = PV.renderers || {};
  PV.renderers.wechat_article = renderWx;
})();
