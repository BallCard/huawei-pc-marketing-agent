(function () {
  'use strict';

  function $(id) {
    // 兼容调用方传入 "#id" 或 "id" 两种写法
    return document.getElementById(String(id).replace(/^#/, ""));
  }

  function appendKids(parent, kids) {
    for (let i = 0; i < kids.length; i++) {
      const kid = kids[i];
      if (kid === null || kid === undefined || kid === false) {
        continue;
      }
      if (Array.isArray(kid)) {
        appendKids(parent, kid);
      } else if (kid instanceof Node) {
        parent.appendChild(kid);
      } else {
        parent.appendChild(document.createTextNode(String(kid)));
      }
    }
  }

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    if (props && typeof props === 'object') {
      for (const [key, value] of Object.entries(props)) {
        if (value === null || value === undefined) {
          continue;
        }
        if (key === 'class' || key === 'className') {
          node.className = String(value);
        } else if (key === 'text') {
          node.textContent = String(value);
        } else if (key === 'style') {
          if (typeof value === 'string') {
            node.style.cssText = value;
          } else if (typeof value === 'object') {
            Object.assign(node.style, value);
          }
        } else if (key.startsWith('on') && typeof value === 'function') {
          const evtName = key.slice(2).toLowerCase();
          node.addEventListener(evtName, value);
        } else if (typeof value === 'boolean') {
          if (value) {
            node.setAttribute(key, '');
          }
        } else {
          node.setAttribute(key, String(value));
        }
      }
    }
    appendKids(node, kids);
    return node;
  }

  const SVG_NS = 'http://www.w3.org/2000/svg';

  function svg(useId, cls = 'icon') {
    const node = document.createElementNS(SVG_NS, 'svg');
    if (cls) {
      node.setAttribute('class', cls);
    }
    node.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(SVG_NS, 'use');
    use.setAttribute('href', `#${String(useId).replace(/^#/, '')}`);
    node.appendChild(use);
    return node;
  }

  function tag(text, cls = '') {
    const span = document.createElement('span');
    span.className = cls ? `tag ${cls}` : 'tag';
    span.textContent = text;
    return span;
  }

  function fmtMs(ms) {
    if (!ms || typeof ms !== 'number' || isNaN(ms) || ms <= 0) {
      return '0 ms';
    }
    if (ms < 1000) {
      return `${Math.round(ms)} ms`;
    }
    return `${(ms / 1000).toFixed(1)} s`;
  }

  const KIND_ZH_MAP = {
    device: '整机图',
    device_scene: '场景图',
    detail: '局部特写',
    screen_ui: '屏幕界面',
    diagram: '功能示意',
    logo: '芯片/品牌标志',
    people: '人物形象',
    other: '其他'
  };

  const KIND_ZH = new Proxy(KIND_ZH_MAP, {
    get(target, prop) {
      if (typeof prop === 'string' && prop in target) {
        return target[prop];
      }
      return '未标注';
    }
  });

  const PLATFORM_HINT = {
    xiaohongshu: '手机竖屏 · 图片轮播置顶 · 短段落 · 话题标签',
    wechat_article: '手机阅读 · 标题+作者行 · 通栏配图 · 文末引导',
    moments: '朋友圈 · 短文 + 图片九宫格',
    poster: '门店展台竖版海报 · 主视觉 + 不超过 3 个卖点'
  };

  window.UI = {
    $,
    el,
    svg,
    tag,
    fmtMs,
    KIND_ZH,
    PLATFORM_HINT
  };
})();
