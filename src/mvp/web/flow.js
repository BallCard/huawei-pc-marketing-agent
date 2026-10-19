(function () {
  "use strict";
  const STAGES = [
    { id: "scene", title: "场景分析", role: "读懂你的想法", kind: "场景 Agent", note: "从人群、场景和自由描述里，理解真实需求，区分硬约束与软偏好。", color: "#e5c8b6" },
    { id: "model", title: "产品顾问", role: "找到合适的电脑", kind: "选型 Agent", note: "校验指定机型；没有指定时，按需求从产品知识库中推荐。", color: "#cdd8bc" },
    { id: "strategy", title: "平台策划", role: "决定怎么表达", kind: "平台规则", note: "根据发布平台，规划篇幅、语气、图片数量和内容结构。", color: "#e7d5a6" },
    { id: "retrieve", title: "资料管家", role: "查找可靠资料", kind: "知识库检索", note: "读取对应型号的产品事实和登记配图，优先挑选包含整机的图片。", color: "#c5d6d3" },
    { id: "extract", title: "事实编辑", role: "提炼产品亮点", kind: "提取 Agent", note: "围绕读者需求，选出可引用、有来源的产品事实。", color: "#dccabd" },
    { id: "compose", title: "内容创作者", role: "让图文成形", kind: "写作 Agent", note: "将产品事实和配图编排成平台原生图文，首图优先展示产品整机。", color: "#e6bdab" },
    { id: "verify", title: "事实核验员", role: "把好事实关", kind: "确定性核验", note: "逐项检查数字、型号、配图与合规用语；发现问题时交回修订。", color: "#c9d4bb" },
    { id: "judge", title: "独立审阅者", role: "最后再看一遍", kind: "审核 Agent", note: "独立审阅终稿，把仍需人工判断的意见留下供你确认。", color: "#d6cbb7" }
  ];
  const LABELS = { done: "已完成", running: "正在工作", error: "需要关注", wait: "等待接力", skip: "未执行" };
  const NS = "http://www.w3.org/2000/svg";
  let root = null;
  let latest = [];
  let selected = null;
  let links;

  function drawLinks() {
    if (!root?.isConnected) return;
    const bounds = root.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    links.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
    const avatars = Array.from(root.querySelectorAll(".bot-avatar"), avatar => {
      const box = avatar.getBoundingClientRect();
      return { x: box.x - bounds.x + box.width / 2, y: box.y - bounds.y + box.height / 2, r: box.width / 2 };
    });
    avatars.slice(0, -1).forEach((from, i) => {
      const to = avatars[i + 1];
      let endX, endY, direction, path;
      if (Math.abs(from.y - to.y) < 20) {
        direction = to.x > from.x ? 1 : -1;
        const startX = from.x + direction * (from.r + 9);
        endX = to.x - direction * (to.r + 10);
        endY = to.y;
        path = `M${startX} ${from.y}H${endX}`;
      } else {
        const side = bounds.width > 600 || i === 1 || i === 5 ? 1 : -1;
        const startX = from.x + side * (from.r + 8);
        const turnX = startX + side * 23;
        endX = to.x + side * (to.r + 9);
        endY = to.y;
        direction = -side;
        path = `M${startX} ${from.y}H${turnX}V${endY}H${endX}`;
      }
      const group = links.children[i];
      const status = latest[i]?.status || "wait";
      group.setAttribute("class", status === "done" && latest[i + 1]?.status === "running" ? "handoff" : status);
      group.children[0].setAttribute("d", path);
      group.children[1].setAttribute("d", `M${endX - direction * 5} ${endY - 4}L${endX} ${endY}L${endX - direction * 5} ${endY + 4}`);
    });
  }

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
  function makeGraph() {
    const graph = UI.el("div", { class: "bot-grid", "aria-label": "生成流水线，按箭头顺序接力" });
    STAGES.forEach((st, i) => {
      const node = UI.el("div", { class: "bot-node wait", "data-step": st.id });
      const btn = UI.el("button", { type: "button", class: "bot-button", "aria-label": `${st.title}：等待接力，查看详情` });
      const avatar = UI.el("span", { class: "bot-avatar" });
      avatar.append(svg("svg", { viewBox: "0 0 100 100", class: "bot-ring", "aria-hidden": "true" }, [svg("circle", { cx: 50, cy: 50, r: 46, class: "ring-track" }), svg("circle", { cx: 50, cy: 50, r: 46, class: "ring-active" })]), portrait(i, st.color));
      const check = UI.el("span", { class: "bot-check", hidden: true });
      check.append(svg("svg", { viewBox: "0 0 24 24", class: "icon", "aria-hidden": "true" }, [svg("path", { d: "m20 6-11 11-5-5" })]));
      avatar.appendChild(check);
      btn.append(avatar, UI.el("b", { class: "bot-name", text: st.title }), UI.el("span", { class: "bot-role", text: "等待接力" }));
      btn.addEventListener("click", () => { selected = st.id; updateDetail(); UI.$("step-dialog").showModal(); });
      node.appendChild(btn);
      if (i < STAGES.length - 1) node.append(svg("svg", { viewBox: "0 0 100 18", preserveAspectRatio: "none", class: "bot-connector", "aria-hidden": "true" }, [svg("path", { d: "M0 9H96", class: "connector-line" }), svg("path", { d: "m90 4 7 5-7 5" })]));
      graph.appendChild(node);
    });
    links = svg("svg", { class: "flow-links", "aria-hidden": "true" });
    STAGES.slice(0, -1).forEach(() => links.appendChild(svg("g", {}, [svg("path", { class: "link-line" }), svg("path", { class: "link-head" })])));
    graph.appendChild(links);
    new ResizeObserver(drawLinks).observe(graph);
    return graph;
  }
  function updateDetail() {
    const st = STAGES.find(s => s.id === selected);
    if (!st) return;
    const data = latest.find(s => s.id === selected);
    UI.$("step-dialog-title").textContent = st.title;
    UI.$("step-dialog-meta").textContent = `${st.kind} · ${LABELS[data?.status || "wait"]}`;
    UI.$("step-dialog-note").textContent = st.note;
    const body = UI.$("step-dialog-body");
    const scrollTop = body.parentElement.scrollTop;
    body.replaceChildren();
    if (!data?.steps.length) body.appendChild(UI.el("p", { text: "轮到这位小助手时，这里会展示它的实际执行信息。" }));
    for (const item of data?.steps || []) {
      body.appendChild(UI.el("h3", { text: `${item.label || st.title} · ${LABELS[item.status] || item.status} · ${UI.fmtMs(item.ms)}` }));
      if (item.detail != null) body.appendChild(UI.el("pre", { text: typeof item.detail === "string" ? item.detail : JSON.stringify(item.detail, null, 2) }));
    }
    body.parentElement.scrollTop = scrollTop;
  }
  function buildFlow(steps, running) {
    const safe = Array.isArray(steps) ? steps : [];
    latest = STAGES.map(st => {
      const entries = safe.filter(item => (item.step === "repair" ? "verify" : item.step) === st.id);
      const status = entries.some(s => s.status === "error") ? "error" : entries.some(s => s.status === "running") ? "running" : entries.length ? "done" : running || !safe.length ? "wait" : "skip";
      return { ...st, steps: entries, status, ms: entries.reduce((sum, s) => sum + (s.ms || 0), 0) };
    });
    if (!root) root = makeGraph();
    latest.forEach((data, i) => {
      const node = root.children[i];
      node.className = `bot-node ${data.status}` + (data.status === "done" && latest[i + 1]?.status === "running" ? " handoff" : "");
      node.querySelector(".bot-role").textContent = LABELS[data.status];
      node.querySelector(".bot-check").hidden = data.status !== "done";
      node.querySelector("button").setAttribute("aria-label", `${data.title}：${LABELS[data.status]}，查看详情`);
    });
    const count = latest.filter(s => s.status === "done").length;
    UI.$("process-progress-fill").style.width = `${count / STAGES.length * 100}%`;
    UI.$("process-progress-fill").parentElement.setAttribute("aria-valuenow", count);
    UI.$("progress-count").textContent = `${count} / 8`;
    root.summary = `${count} / 8 个环节已完成`;
    requestAnimationFrame(drawLinks);
    if (UI.$("step-dialog").open) updateDetail();
    return root;
  }
  window.buildFlow = buildFlow;
})();
