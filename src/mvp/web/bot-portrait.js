(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs = {}, children = []) {
    const n = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => n.setAttribute(key, value));
    children.forEach(child => n.appendChild(child));
    return n;
  }
  function portrait(index, color) {
    const p = svg("svg", { viewBox: "0 0 80 80", class: "bot-portrait", "aria-hidden": "true" });
    const ink = "#37372f";
    const paper = "#f8f7f3";
    const g = svg("g", { stroke: ink, "stroke-width": "1.45", "stroke-linejoin": "round", "stroke-linecap": "round" });
    // Deliberately uneven contours echo the studio's pen-and-paper illustration.
    g.append(svg("path", { d: "M24 72c-.7-10 3-17 15-18 12-.8 17 7 17 18l-12 1-20-1Z", fill: paper }));
    g.append(svg("path", { d: "m34 55 1 7 9 .4 1-8M20 64l-4 5m43-4 5 3M30 73l-.7 4m20-4 1 4", fill: "none" }));
    g.append(svg("path", { d: "M17 29c-6-1-7 3-6 8s2 7 6 6m46-14c6-1 7 4 6 9s-3 6-6 5", fill: paper }));
    const contours = [
      "M18 26c0-11 9-14 22-13 13-.5 23 4 23 15l-.6 16c-1 10-11 13-23 13-14 .3-23-5-23-16Z",
      "M18 27c-2-9 9-15 22-15 13 0 24 6 23 16l-.4 15c-.4 10-11 14-23 14-13 .4-23-5-23-15Z",
      "M19 25c1-10 7-13 21-12 14-.7 23 2 23 14l-1 19c-1 8-9 12-23 11-15 0-23-4-22-15Z"
    ];
    g.append(svg("path", { d: contours[index % 3], fill: paper }));
    g.append(svg("path", { d: "M23 28c7-3 25-3 33 0m-33 0c-2 6-2 12 1 17m32-17c3 6 2 12 0 17", stroke: "#ccc6b8", "stroke-width": ".8", fill: "none" }));
    if (index % 3 === 0) {
      g.append(svg("path", { d: "m40 13 .5-5" }), svg("path", { d: "M37 5c0-4 7-4 7 0s-7 4-7 0Z", fill: paper }));
    } else if (index % 3 === 1) {
      g.append(svg("path", { d: "m27 15-1-7m27 7 1-7M24 8l5 .5m23-.5 5 .4", fill: "none" }));
    } else {
      g.append(svg("path", { d: "M21 22c-4-13 22-20 35-6l-4 6-31 .4ZM25 20l30-1", fill: "#ebe7dc" }));
    }
    if ([1, 4, 7].includes(index)) {
      g.append(svg("path", { d: "M25 36c-1-8 13-9 13 0s-13 8-13 0Zm18 0c-.4-8 13-9 13-.2s-13 9-13 .2Zm-5-.6h5", fill: "none" }));
    }
    g.append(svg("path", { d: "m31 34 .2 3m17.5-3-.1 3", "stroke-width": "2.5", fill: "none" }));
    g.append(svg("path", { d: index % 2 ? "M37 44c2 1 4 1 6-.3" : "M36 43q4 5 8-.2", fill: "none" }));
    g.append(svg("path", { d: "m25 43 2 .5m26-.6 2 .4", stroke: "#b98269", "stroke-width": "1.4", fill: "none" }));
    g.append(svg("path", { d: "M29 65v4m22-4v4m-15-1 8 .4", stroke: "#aaa393", "stroke-width": "1", fill: "none" }));
    g.append(svg("path", { d: "M38 64h4v4h-4Z", fill: color, stroke: "#a69b85", "stroke-width": ".7" }));
    p.appendChild(g);
    return p;
  }
  window.BotPortrait = portrait;
})();
