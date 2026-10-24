(function () {
  "use strict";

  const UI = window.UI;
  const PV = window.PV;
  if (!UI || !PV) return;

  function renderXhs(r, options = {}) {
    const desktop = options.device === "desktop";
    const data = r || {};
    const article = data.article || {};
    const blocks = Array.isArray(article.blocks) ? article.blocks : [];

    // 1. .xhs-head
    const ava = PV.publisherAvatar("xhs-ava", true);
    const name = UI.el("span", { className: "xhs-name" }, "华为PC门店");
    const user = UI.el("div", { className: "xhs-user" }, ava, name);
    const follow = UI.el("button", { type: "button", className: "xhs-follow" }, "关注");
    const head = UI.el("div", { className: "xhs-head" }, user, follow);

    // 2. 图片轮播
    const imgBlocks = blocks.filter(function (b) {
      return b && b.type === "image";
    });
    const slides = [];
    imgBlocks.forEach(function (b) {
      const fig = PV.figure(data, b, "xhs-slide");
      if (fig) {
        slides.push({ fig: fig, block: b });
      }
    });

    const car = UI.el("div", { className: "xhs-car" });
    const dots = UI.el("div", { className: "xhs-dots", role: "group", "aria-label": "笔记图片" });
    let activeSlide = 0;
    function goToSlide(index) {
      activeSlide = (index + slides.length) % slides.length;
      car.scrollTo({ left: activeSlide * car.clientWidth, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    }

    const hasHero = typeof PV.hasHero === "function" ? PV.hasHero(data) : true;
    const heroReason = typeof PV.heroReason === "function" ? PV.heroReason(data) : "缺整机图";

    let missingHeroEl = null;
    if (!hasHero && typeof PV.missingFigure === "function") {
      missingHeroEl = PV.missingFigure(heroReason, true);
    }

    if (slides.length === 0) {
      if (typeof PV.missingFigure === "function") {
        const mf = PV.missingFigure(heroReason, true);
        if (mf) car.appendChild(mf);
      }
    } else {
      const total = slides.length;
      slides.forEach(function (item, idx) {
        const idxBadge = UI.el("span", { className: "xhs-idx" }, (idx + 1) + "/" + total);
        item.fig.appendChild(idxBadge);
        car.appendChild(item.fig);

        const dot = UI.el("button", { type: "button", className: idx === 0 ? "xhs-dot on" : "xhs-dot", "aria-label": `查看第 ${idx + 1} 张图片`, "aria-current": String(idx === 0) });
        dot.addEventListener("click", function () {
          goToSlide(idx);
        });
        dots.appendChild(dot);
      });

      car.addEventListener("scroll", function () {
        const carRect = car.getBoundingClientRect();
        const carCenter = carRect.left + carRect.width / 2;
        let closestIdx = 0;
        let minDiff = Infinity;
        slides.forEach(function (item, idx) {
          const rect = item.fig.getBoundingClientRect();
          const figCenter = rect.left + rect.width / 2;
          const diff = Math.abs(carCenter - figCenter);
          if (diff < minDiff) {
            minDiff = diff;
            closestIdx = idx;
          }
        });
        const allDots = dots.querySelectorAll(".xhs-dot");
        activeSlide = closestIdx;
        allDots.forEach(function (d, dIdx) {
          d.setAttribute("aria-current", String(dIdx === closestIdx));
          if (dIdx === closestIdx) {
            d.classList.add("on");
          } else {
            d.classList.remove("on");
          }
        });
      }, { passive: true });
    }

    // 3. .xhs-body
    const bodyChildren = [];
    if (article.title) {
      bodyChildren.push(UI.el("h3", { className: "xhs-title" }, article.title));
    }
    if (article.lead) {
      bodyChildren.push(UI.el("p", { className: "xhs-p" }, article.lead));
    }
    blocks.forEach(function (b) {
      if (b && b.type === "text" && b.text) {
        bodyChildren.push(UI.el("p", { className: "xhs-p" }, b.text));
      }
    });

    if (article.cta) {
      bodyChildren.push(UI.el("p", { className: "xhs-p" }, article.cta));
    }

    if (Array.isArray(article.tags) && article.tags.length > 0 && typeof PV.hashTags === "function") {
      const renderedTags = PV.hashTags(article.tags);
      if (renderedTags) {
        const tagsContainer = UI.el("div", { className: "xhs-tags" }, renderedTags);
        bodyChildren.push(tagsContainer);
      }
    }

    bodyChildren.push(UI.el("div", { className: "xhs-time" }, "编辑于 今天 · 华为PC门店"));
    const body = UI.el("div", { className: "xhs-body" }, ...bodyChildren);

    // 4. .xhs-bar
    const inputEl = UI.el("div", { className: "xhs-input" }, "说点什么…");
    const actEl = UI.el(
      "div",
      { className: "xhs-act" },
      UI.el("span", { className: "xhs-act-btn" }, PV.icon("heart"), "赞"),
      UI.el("span", { className: "xhs-act-btn" }, PV.icon("bookmark"), "收藏"),
      UI.el("span", { className: "xhs-act-btn" }, PV.icon("message"), "评论")
    );
    const bar = UI.el("div", { className: "xhs-bar" }, inputEl, actEl);

    // 根容器组合
    const root = UI.el("div", { className: desktop ? "pv-desktop pv-xhs" : "pv-phone pv-xhs" });
    root.appendChild(head);
    const media = UI.el("div", { className: "xhs-media" });
    if (!hasHero && slides.length > 0 && missingHeroEl) {
      media.appendChild(missingHeroEl);
    }
    media.appendChild(car);
    if (slides.length > 0) {
      media.appendChild(dots);
    }
    if (desktop && slides.length > 1) {
      const previous = UI.el("button", { type: "button", className: "xhs-carousel-arrow previous", "aria-label": "上一张图片" }, PV.icon("left"));
      const next = UI.el("button", { type: "button", className: "xhs-carousel-arrow next", "aria-label": "下一张图片" }, PV.icon("right"));
      previous.addEventListener("click", () => goToSlide(activeSlide - 1));
      next.addEventListener("click", () => goToSlide(activeSlide + 1));
      media.append(previous, next);
    }
    const content = UI.el("div", { className: "xhs-content" }, body);
    if (desktop) {
      root.appendChild(media);
      const interactive = (r.planning?.template || r.marketing_template)?.id === 'C01';
      content.appendChild(UI.el("div", { className: "xhs-comments-empty" },
        UI.el("span", {}, interactive ? "这篇想问你" : "评论区"), UI.el("p", {}, interactive ? article.cta || '说说你的选择' : "暂无评论"),
        interactive ? UI.el('small', {}, '等待真实回复，未预置评论') : null));
      root.appendChild(content);
    } else {
      // 手机预览保持一页设备框，媒体与正文在设备内滚动，避免撑开工作区。
      root.appendChild(UI.el("div", { className: "pv-scroll xhs-mobile-scroll" }, media, content));
    }
    root.appendChild(bar);

    return root;
  }

  PV.renderers = PV.renderers || {};
  PV.renderers.xiaohongshu = renderXhs;
})();
