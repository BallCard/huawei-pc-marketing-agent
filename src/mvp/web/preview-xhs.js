(function () {
  "use strict";

  const UI = window.UI;
  const PV = window.PV;
  if (!UI || !PV) return;

  function renderXhs(r) {
    const data = r || {};
    const article = data.article || {};
    const blocks = Array.isArray(article.blocks) ? article.blocks : [];

    // 1. .xhs-head
    const ava = UI.el("div", { className: "xhs-ava" }, "华");
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
    const dots = UI.el("div", { className: "xhs-dots" });

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

        const dot = UI.el("i", { className: idx === 0 ? "xhs-dot on" : "xhs-dot" });
        dot.addEventListener("click", function () {
          item.fig.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
          const allDots = dots.querySelectorAll(".xhs-dot");
          allDots.forEach(function (d, dIdx) {
            if (dIdx === idx) {
              d.classList.add("on");
            } else {
              d.classList.remove("on");
            }
          });
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
        allDots.forEach(function (d, dIdx) {
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
      UI.el("button", { type: "button", className: "xhs-act-btn" }, "赞"),
      UI.el("button", { type: "button", className: "xhs-act-btn" }, "收藏"),
      UI.el("button", { type: "button", className: "xhs-act-btn" }, "评论")
    );
    const bar = UI.el("div", { className: "xhs-bar" }, inputEl, actEl);

    // 根容器组合
    const root = UI.el("div", { className: "pv-phone pv-xhs" });
    root.appendChild(head);

    if (!hasHero && slides.length > 0 && missingHeroEl) {
      root.appendChild(missingHeroEl);
    }
    root.appendChild(car);
    if (slides.length > 0) {
      root.appendChild(dots);
    }
    root.appendChild(body);
    root.appendChild(bar);

    return root;
  }

  PV.renderers = PV.renderers || {};
  PV.renderers.xiaohongshu = renderXhs;
})();
