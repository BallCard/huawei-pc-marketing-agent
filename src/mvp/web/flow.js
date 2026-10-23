(function () {
  "use strict";
  const state = new window.ProcessState();
  const el = (tag, props, ...kids) => UI.el(tag, props, ...kids);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const STATUS = { running: "正在处理", done: "已完成", waiting: "等待补充", error: "需关注", skip: "已跳过", needs_fix:"发现问题", incomplete:"未完成" };
  const WHERE = { title: "标题", lead: "导语", body: "正文", caption: "图注", cta: "行动引导" };
  const PRIMARY = ["scene", "sources", "plan", "compose", "review"];
  const primary = () => state.artifacts.request?.platform === "poster" || latest.result?.poster ? [...PRIMARY, "poster_image", "poster_review"] : PRIMARY;
  let root, deck, peek, latest = {}, displayed, signature = "", detailStage = null, detailSignature = "";
  const clock = new window.ProcessClock();
  let running = false;
  const rotation = new window.StageRotation({ onChange: render, holdMs: reduced.matches ? 0 : 1700 });
  const value = v => typeof v === "string" ? v : Array.isArray(v) ? v.map(value).filter(Boolean).join("；") : v?.detail || v?.text || v?.title || v?.reason || v?.error || "";
  function issues(version) {
    const a = state.artifacts, review = a[`review:${version}`], rules = a[`rules:${version}`];
    return [...(review?.problems || []).map(p => p.detail), ...(rules?.issues || []).map(p => p.detail), ...(rules?.platform_issues || [])].filter(Boolean);
  }
  function content(stage) {
    const data = window.describeProcessActivity(stage, { ...latest, artifacts: state.artifacts, steps: state.steps, events: state.orderedEvents() });
    return { ...data, rows: data.records.map(row => [row.label, [row.path, row.detail].filter(Boolean).join(" · ")]) };
  }
  function makeRoot() {
    peek = el("div", { class: "stage-peek", "aria-hidden": "true" });
    deck = el("div", { class: "stage-deck", "aria-live": "polite", "aria-atomic": "true" }, peek);
    root = el("div", { class: "rotation-stage" }, deck);
    return root;
  }
  function makeCard(stage, data) {
    const phases = primary(), index = phases.indexOf(stage.id);
    const avatar = el("div", { class: "bot-avatar", "aria-hidden": "true" }, window.BotPortrait(stage.bot ?? 0, stage.bot === 7 ? "#9ca98f" : "#c28c6c"));
    const rows = el("div", { class: "stage-activities" }, ...data.records.map(record => {
      const mark = el("span", { class: `activity-mark ${record.status}`, "aria-hidden": "true" }, record.status === "running" ? "" : ["error","needs_fix","incomplete"].includes(record.status) ? "!" : "✓");
      return el("div", { class: `activity-row ${record.kind || "task"} ${record.status}`, "data-kind": record.kind || "task", "data-tool": record.tool }, mark,
        el("div", { class: "activity-content" }, el("div", { class: "activity-label" }, record.sourceType ? el("span", { class: "activity-source-type" }, record.sourceType) : null, record.label),
          record.path ? el("p", { class: "activity-path", title: record.path }, record.path) : null,
          record.detail ? el("p", { class: "activity-excerpt", title: record.detail }, record.detail) : null),
        el("span", { class: "activity-state" }, STATUS[record.status] || ""));
    }));
    const processing = el("div", { class: "stage-processing" },
      data.note ? el("span", {}, data.note) : null,
      stage.entries.length ? el("time", { "data-phase-id": stage.id }) : null);
    const meta = el("div", { class: "stage-meta" }, el("span", {}, index >= 0 ? `${String(index + 1).padStart(2,"0")} / ${String(phases.length).padStart(2,"0")}` : stage.id === "finish" ? "本次结果" : "质量回流"),
      el("span", { class: "stage-role" }, stage.role || "内容策划"), el("span", { class: "stage-status" }, STATUS[stage.status] || "等待开始"));
    return el("article", { class: `turn-card is-current ${stage.status || "idle"} ${data.tone || ""}`, "data-stage": stage.id, "aria-label": stage.label || "创作准备" },
      el("div", { class: "stage-bot" }, avatar, el("span", { class: "bot-caption" }, stage.role || "内容策划")),
      el("div", { class: "stage-copy" }, meta, el("h3", {}, stage.status === "running" ? el("span", { class: "activity-spinner", "aria-hidden": "true" }) : null, el("span", {}, data.title)),
        ["poster_image","poster_review"].includes(stage.id) ? el("div", {class:"poster-process-visual"},
          (state.artifacts.poster?.image_url || state.artifacts.poster?.fallback_image_url) ? el("img", {src:state.artifacts.poster.image_url || state.artifacts.poster.fallback_image_url, alt:state.artifacts.poster.image_url ? "已返回的海报，审核结论尚待确认" : "预制样例，现场生图尚未完成"}) :
          el("div", {class:"poster-skeleton", "aria-label":"等待模型返回海报", role:"img"},
            el("span", {class:"poster-skeleton-title"}), el("span", {class:"poster-skeleton-visual"}), el("span", {class:"poster-skeleton-line"}), el("span", {class:"poster-skeleton-line short"}))) : null,
        rows, processing,
        stage.id === "idle" ? null : el("button", { class: "stage-detail", type: "button", onclick: () => openDetail(stage) }, "全部处理记录", el("span", { "aria-hidden": "true" }, "↗")),
        latest.state === "done" && ["finish","recheck","review"].includes(stage.id) && latest.result?.article && window.processReviewStatus(latest.result).needsReview ?
          el("button", {class:"text-button review-question-entry", type:"button", onclick:() => window.dispatchEvent(new CustomEvent("open-review-questions"))}, "问题详情 ↗") : null));
  }
  function render({ stage, next, rotate }) {
    if (!root) makeRoot();
    stage ||= { id: "idle", label: "创作准备", role: "内容策划", bot: 0, entries: [] };
    const title = UI.$("process-title");
    if (title.textContent !== stage.label) title.textContent = stage.label;
    const data = content(stage);
    const nextPlanned = { scene: "准备依据", sources: "确定立意", plan: "图文创作", compose: "独立评审", review: "根据评审结果继续", lookup: "定向修订", repair: "终稿复核", recheck: "汇总核验结果", poster_image:"成图审核", poster_review:"汇总审核结果" };
    const nextText = next?.label || nextPlanned[stage.id];
    peek.textContent = nextText ? `接下来 · ${nextText}` : "";
    peek.hidden = !nextText;
    const nextSignature = JSON.stringify([stage, data]);
    if (nextSignature !== signature) {
      const old = deck.querySelector(".is-current"), card = makeCard(stage, data);
      const changing = old && displayed !== stage.id && rotate && !reduced.matches;
      if (changing) {
        const hadFocus = old.contains(document.activeElement);
        deck.querySelectorAll(".is-leaving").forEach(n => n.remove());
        old.classList.remove("is-current", "is-entering");
        old.classList.add("is-leaving"); old.inert = true; old.setAttribute("aria-hidden", "true");
        card.classList.add("is-entering"); deck.append(card);
        if (hadFocus) card.querySelector("button")?.focus({ preventScroll: true });
        setTimeout(() => old.remove(), 650);
        card.addEventListener("animationend", () => card.classList.remove("is-entering"), { once: true });
      } else {
        const hadFocus = old?.contains(document.activeElement);
        deck.replaceChildren(peek, card);
        if (hadFocus) card.querySelector("button")?.focus({ preventScroll: true });
      }
      displayed = stage.id; signature = nextSignature;
    }
    renderTrack();
    if (detailStage && UI.$("step-dialog").open) fillDetail(detailStage);
  }
  function renderTrack() {
    const track = UI.$("phase-track");
    if (!track) return;
    const stages = window.deriveStages({ steps: state.steps, state: state.state, result: latest.result });
    const phases = [...primary().map(id=>window.PROCESS_PHASES.find(p=>p.id===id)), ...stages.filter(s=>["lookup","repair","recheck"].includes(s.id))];
    const active = stages.findLast(s=>s.status === "running");
    const trackSignature = JSON.stringify(stages.map(s => [s.id, s.status]));
    if (track.dataset.signature === trackSignature) return;
    track.dataset.signature = trackSignature;
    track.style.setProperty("--phase-count",phases.length);
    track.style.setProperty("--track-min-width",`${phases.length * 62}px`);
    const previousActive = track.dataset.active;
    track.dataset.active = active?.id || "";
    for (const node of [...track.children]) if (!phases.some(p=>p.id === node.dataset.phase)) node.remove();
    phases.forEach((phase,index)=>{
      const actual = stages.find(s=>s.id === phase.id), status = actual?.status || "wait";
      let node = track.querySelector(`[data-phase="${phase.id}"]`);
      if (!node) node = el("span", {"data-phase":phase.id,role:"listitem"},
        el("span",{class:"phase-line","aria-hidden":"true"},el("b")),
        el("i",{"aria-hidden":"true"}),el("span",{class:"phase-name"},phase.label));
      node.className = `phase-dot ${status}${active?.id === phase.id ? " current" : ""}`;
      node.title = `${phase.label} · ${actual ? STATUS[status] : "待处理"}`;
      node.setAttribute("aria-label",node.title);
      if (active?.id === phase.id) node.setAttribute("aria-current","step"); else node.removeAttribute("aria-current");
      node.querySelector("i").textContent = status === "done" ? "✓" : status === "error" ? "!" : String(index+1).padStart(2,"0");
      const next = stages.find(s=>s.id === phases[index+1]?.id);
      const line = node.querySelector(".phase-line");
      line.hidden = index === phases.length-1;
      line.className = `phase-line${status === "done" && next ? " done" : status === "running" ? " running" : ""}`;
      if (track.children[index] !== node) track.insertBefore(node,track.children[index] || null);
    });
    const scroller = track.parentElement;
    if (active && active.id !== previousActive && scroller.scrollWidth > scroller.clientWidth) {
      const node = track.querySelector(`[data-phase="${active.id}"]`);
      scroller.scrollTo({left:Math.max(0,node.offsetLeft + node.offsetWidth/2 - scroller.clientWidth/2),behavior:reduced.matches ? "instant" : "smooth"});
    }
  }
  function detailBlock(title, text) {
    if (!text) return null;
    return el("section", { class: "detail-block" }, el("h3", {}, title), el("p", {}, value(text)));
  }
  function fillDetail(stage) {
    const a = state.artifacts, data = content(stage), body = UI.$("step-dialog-body");
    const current = window.deriveStages({ steps: state.steps, state: state.state, result: latest.result }).find(s => s.id === stage.id) || stage;
    const nextSignature = JSON.stringify([stage.id, current, data, a]);
    if (detailSignature === nextSignature) return;
    detailSignature = nextSignature;
    UI.$("step-dialog-meta").textContent = `${stage.role} · ${STATUS[current.status] || "等待开始"}`;
    UI.$("step-dialog-title").textContent = stage.label;
    UI.$("step-dialog-note").textContent = "本次实际使用的资料、处理结果与耗时。";
    body.replaceChildren(...data.rows.map(([label, text]) => detailBlock(label, text)));
    for (const step of current.entries) body.append(el("section", { class: "detail-block step-record" },
      el("h3", {}, step.label, el("span", {}, `${STATUS[step.status]} · ${UI.fmtMs(step.ms)}`)),
      step.input_summary ? el("p", {}, "输入：" + value(step.input_summary)) : null,
      value(step.detail) ? el("p", {}, value(step.detail)) : null));
    if (["plan", "sources"].includes(stage.id)) {
      if (stage.id === "plan") {
        const ctx = a.creative_context || {};
        body.append(detailBlock("实际载入的创作上下文", `门店 ${ctx.store?.name || ctx.store_id || '未登记'} · 有效资料 ${ctx.confirmed_items?.length || 0} 条 · 近期历史 ${ctx.history?.length || 0} 篇 · 可用样板 ${ctx.approved_templates?.length || 0} 个`));
        body.append(detailBlock("本篇结构与避重", [a.plan?.format, ...(a.plan?.avoidance || [])].filter(Boolean)));
        const template = a.plan?.template;
        if (template) {
          body.append(detailBlock(`已审核样板 ${template.id} · ${template.title}`, [template.selection_source, template.reason, `审核备注：${template.user_note || '未附备注'}`, ...template.pattern]));
          for (const slot of template.filled_slots || []) body.append(detailBlock(slot.slot, `${slot.text || '未填槽位'} · 引用 ${(slot.refs || []).join('、') || '无产品主张'}`));
        }
        for (const angle of a.plan?.angles || []) body.append(detailBlock(`${angle.id === a.plan.selected_angle ? "选定" : "另一个角度"} · ${angle.title}`, angle.reason));
        if (a.plan?.unsupported_requests?.length) body.append(detailBlock("缺乏依据，不作承诺", a.plan.unsupported_requests));
      }
      const facts = a.evidence?.facts || a.plan?.facts;
      for (const fact of facts || a.sources?.snippets || []) body.append(el("section", { class: "detail-block evidence-record" },
        el("h3", {}, `${fact.id || fact.sid} · ${fact.source?.label || fact.source?.title || value(fact.source)}`),
        fact.claim ? el("p", {}, "支持的主张：" + fact.claim) : null,
        el("blockquote", {}, fact.text), fact.conditions?.length ? el("p", {}, "适用条件：" + value(fact.conditions)) : null));
    }
    if (["review", "repair", "recheck", "finish"].includes(stage.id)) {
      const version = stage.id === "review" ? 1 : stage.id === "repair" ? 1 : a.final?.version || Math.max(1,...Object.keys(a).filter(k=>/^draft:\d+$/.test(k)).map(k=>+k.split(":")[1]));
      const similarity = a[`similarity:${version}`] || a['similarity:final'];
      if (similarity) body.append(detailBlock("历史稿字面重合检查", [`实际对照 ${similarity.compared} 篇，不代表原创率`, ...(similarity.matches || []).map(m => `${m.where}#${m.index} 与《${m.title}》重合：${m.overlap}`)]));
      for (const p of a[`review:${version}`]?.problems || []) body.append(el("section", { class: "detail-block problem-record" },
        el("h3", {}, `${WHERE[p.where] || "文稿"} · ${p.type === "expression" ? "表达改进" : "必须修改"}`),
        p.quote ? el("blockquote", {}, p.quote) : null, el("p", {}, p.detail), p.direction ? el("p", {}, "修改方向：" + p.direction) : null));
      for (const issue of issues(version)) body.append(detailBlock("待处理问题", issue));
      if (["repair", "recheck", "finish"].includes(stage.id)) for (const change of a.revision?.changes || []) body.append(el("section", { class: "detail-block revision-record" },
        el("h3", {}, `${WHERE[change.where] || "文稿"} · 修改前后`),
        el("del", {}, change.before || "（原稿无此句）"), el("ins", {}, change.after || "（删除无依据内容）"),
        change.fact_refs?.length ? el("p", {}, "相关证据：" + change.fact_refs.join("、")) : null));
      if (latest.state === "done" && latest.result?.article && window.processReviewStatus(latest.result).needsReview)
        body.append(el("button", {class:"btn-primary", type:"button", onclick:() => window.dispatchEvent(new CustomEvent("open-review-questions"))}, "问题详情 · 逐项裁定 →"));
    }
    if (stage.id === "compose") {
      const draft = a["draft:1"];
      if (draft) body.append(detailBlock("初稿导语", draft.lead));
    }
  }
  function openDetail(stage) {
    detailStage = stage; detailSignature = "";
    fillDetail(stage);
    UI.$("step-dialog").showModal();
  }
  function tick() {
    const elapsedMs = clock.read();
    const elapsed = Math.max(0, Math.floor(elapsedMs / 1000));
    if (UI.$("process-elapsed")) UI.$("process-elapsed").textContent = elapsed || running ? `已用 ${elapsed} 秒` : "";
    const phases = window.deriveStages({steps:state.steps,state:state.state,result:latest.result});
    for (const node of root?.querySelectorAll("[data-phase-id]") || []) {
      const phase = phases.find(s=>s.id===node.dataset.phaseId);
      node.textContent = `本环节${phase?.status === "running" ? "" : "耗时"} ${Math.floor(window.phaseDuration(phase,elapsedMs)/1000)} 秒`;
    }
  }
  function update(snapshot = {}, { restore = false } = {}) {
    latest = snapshot; running = snapshot.state === "running";
    clock.update(snapshot);
    state.ingest(snapshot);
    const urgent = snapshot.state === "error" || ["need_info", "input_required", "budget_exceeded"].includes(snapshot.result?.status);
    rotation.update(window.deriveStages({ steps: state.steps, state: state.state, result: latest.result }), { restore, urgent });
    const live = UI.$("process-live");
    if (live) {
      const needInfo = snapshot.result?.status === "need_info";
      live.textContent = running ? "正在创作" : snapshot.state === "error" ? "执行中断" : snapshot.result?.status === "input_required" ? "暂未生成作品" : snapshot.state === "done" ? (needInfo ? "本次待补充" : "本次已完成") : "等待开始";
      live.dataset.active = String(running);
    }
    tick();
    return root;
  }
  function reset() {
    rotation.reset(); state.reset(); latest = {}; displayed = null; signature = ""; detailStage = null; detailSignature = "";
    clock.reset(); running = false; root = null;
    if (UI.$("step-dialog").open) UI.$("step-dialog").close();
  }
  // 追问续跑：已完成环节的展示保持原样，只让新出现的环节继续入场。
  function resume() {
    clock.holdFloor();
    rotation.release(["finish"]);
  }
  reduced.addEventListener("change", () => { rotation.holdMs = reduced.matches ? 0 : 1700; rotation.update(window.deriveStages({ steps: state.steps, state: state.state, result: latest.result })); });
  window.buildFlow = (steps, isRunning) => update({ steps, state: isRunning ? "running" : "idle" });
  window.ProcessView = { update, reset, resume };
  setInterval(tick, 250);
})();
