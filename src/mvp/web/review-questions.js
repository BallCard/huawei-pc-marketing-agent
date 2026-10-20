(function () {
  "use strict";
  const el = window.UI.el;
  const choices = [
    ["fix", "接受意见，按建议修改", "保留原有事实依据，修改这条问题后再审核。"],
    ["disagree", "我认为原文可用", "补充判断理由，交由模型复审，或最后人工裁定采用。"],
    ["defer", "暂时无法确认", "保留这个问题，继续核对资料或稍后处理。"]
  ];
  const locations = {title:"标题", lead:"导语", body:"正文", caption:"图注", cta:"行动引导", article:"整篇稿件"};
  let result, form, answers, index = 0, submitting = false, generation = 0, initialized = false;
  const drafts = new Map();
  const dialog = () => UI.$("review-dialog");
  const body = () => UI.$("review-question-body");
  function notice(message) { UI.$("review-question-error").textContent = message; }
  function currentAnswer() { return answers[form.questions[index].id] ||= { choice:"", reason:"" }; }
  function focusQuestion() { UI.$("review-question-title").focus({preventScroll:true}); dialog().scrollTop = 0; }
  function evidence(question) {
    const claim = (result.verification?.facts || []).find(c => c.where === question.where && c.index === question.index);
    const related = form.facts.filter(f => claim?.fact_ids?.includes(f.id));
    const facts = related.length ? related : form.facts.slice(0, 3);
    if (!facts.length) return null;
    return el("details", {class:"review-question-evidence"}, el("summary", {}, related.length ? "查看这句引用的事实依据" : "查看本稿资料（本条是否获支持仍需判断）"),
      ...facts.map(f => el("section", {}, el("b", {}, `${f.id} · ${f.source?.title || f.source?.label || "产品资料"}`),
        el("p", {}, f.text || ""), ...(f.conditions || []).map(c => el("p", {}, `适用条件：${c.text || c}`)))));
  }
  function renderQuestion() {
    notice("");
    const question = form.questions[index], answer = currentAnswer();
    UI.$("review-question-meta").textContent = `终审反馈 · ${index + 1} / ${form.questions.length}`;
    UI.$("review-question-title").textContent = question.question;
    const reasoning = el("textarea", {rows:3, maxlength:2000, id:"review-reason", placeholder:"例如：原文已经保留‘约’，见 F2；或补充你希望怎样改。",
      oninput:event => { answer.reason = event.target.value; }});
    reasoning.value = answer.reason;
    const radios = choices.map(([value, title, description]) => {
      const input = el("input", {type:"radio", name:"review-choice", value, onchange:() => {
        answer.choice = value; reasoning.required = value === "disagree";
        body().querySelectorAll(".review-choice").forEach(row => row.classList.toggle("is-selected", row.contains(input)));
        UI.$("review-reason-label").textContent = value === "disagree" ? "你的判断理由（必填）" : "补充说明（选填）";
      }});
      input.checked = answer.choice === value;
      return el("label", {class:`review-choice${input.checked ? " is-selected" : ""}`}, input,
        el("span", {}, el("b", {}, title), el("small", {}, description)));
    });
    body().replaceChildren(el("section", {class:"review-question-problem"},
      el("span", {class:"section-label"}, `${locations[question.where] || "作品"} · ${question.type === "expression" ? "表达改进" : "待核对问题"}`),
      question.quote ? el("blockquote", {}, question.quote) : null,
      el("p", {}, question.detail), question.direction ? el("p", {class:"review-direction"}, `模型建议：${question.direction}`) : null),
      evidence(question), el("fieldset", {class:"review-choices"}, el("legend", {class:"sr-only"}, "选择这条意见的处理方式"), ...radios),
      el("label", {for:"review-reason", id:"review-reason-label"}, answer.choice === "disagree" ? "你的判断理由（必填）" : "补充说明（选填）"), reasoning);
    UI.$("review-back").disabled = index === 0;
    UI.$("review-next").textContent = index === form.questions.length - 1 ? "查看裁定汇总 →" : "下一条 →";
    UI.$("review-question-actions").hidden = false;
  }
  function renderSummary() {
    notice("");
    UI.$("review-question-meta").textContent = "终审反馈 · 裁定汇总";
    UI.$("review-question-title").textContent = "接下来，怎样处理这份作品？";
    const canAdopt = Object.values(answers).length === form.questions.length && form.questions.every(q => answers[q.id]?.choice === "disagree");
    const prior = form.previous;
    const actions = [
      ["continue", "按反馈修订与复审", "模型只处理你选定的问题，并重新给出审核结论。", false],
      ["adopt", "人工裁定采用本稿", "保存你的裁定，原始自动审核意见保留。", !canAdopt],
      ["hold", "暂缓处理，保留问题", "保存本次选择，返回作品，稍后继续。", false]
    ];
    body().replaceChildren(el("details", {class:"review-summary-details"}, el("summary", {}, `已逐项选择 ${form.questions.length} 条意见 · 展开查看`),
      el("ol", {class:"review-decision-summary"}, ...form.questions.map(q => el("li", {},
      el("span", {}, q.detail), el("b", {}, choices.find(c => c[0] === answers[q.id].choice)?.[1]),
      answers[q.id].reason ? el("small", {}, answers[q.id].reason) : null)))),
      el("p", {class:"dialog-copy"}, "人工采用需逐项确认原文可用并填写理由。"),
      prior?.next_job ? el("button", {class:"btn-primary", type:"button", onclick:() => {
        dialog().close(); window.dispatchEvent(new CustomEvent("review-followup", {detail:{job:prior.next_job, task:result.task}}));
      }}, "打开已提交的复审任务 →") : el("div", {class:"review-resolution"}, ...actions.map(([value,title,description,disabled]) =>
        el("button", {type:"button", class:"review-resolution-option", disabled, onclick:() => submit(value)},
          el("b", {}, title), el("small", {}, description), el("span", {"aria-hidden":"true"}, "→")))));
    UI.$("review-back").disabled = false;
    UI.$("review-next").hidden = true;
    focusQuestion();
  }
  async function submit(resolution) {
    if (submitting) return;
    submitting = true; notice("正在保存你的裁定…");
    UI.$("review-back").disabled = true;
    dialog().querySelector("[data-close-dialog]").disabled = true;
    body().querySelectorAll("button").forEach(b => { b.disabled = true; });
    try {
      const response = await fetch(`/api/job/${encodeURIComponent(result.job_id)}/review`, {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token:form.token, resolution, answers:form.questions.map(q => ({id:q.id, ...answers[q.id]}))})});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "裁定未能保存，请重试。");
      drafts.delete(form.token); dialog().close();
      window.dispatchEvent(new CustomEvent("review-updated", {detail:data}));
    } catch (error) { renderSummary(); notice(error.message); }
    finally { submitting = false; dialog().querySelector("[data-close-dialog]").disabled = false; }
  }
  async function open(nextResult) {
    init();
    if (!nextResult?.job_id) { Studio.toast("请先打开已保存的任务，再查看问题详情。"); return; }
    const turn = ++generation;
    result = nextResult; form = null; index = 0; submitting = false;
    UI.$("review-question-meta").textContent = "终审反馈";
    UI.$("review-question-title").textContent = "正在读取问题详情";
    body().replaceChildren(); UI.$("review-question-actions").hidden = true; notice("");
    if (UI.$("step-dialog").open) UI.$("step-dialog").close();
    if (window.AgentAsk) window.AgentAsk.close({ reset: true });
    if (!dialog().open) dialog().show();
    try {
      const response = await fetch(`/api/job/${encodeURIComponent(result.job_id)}/review`);
      const data = await response.json();
      if (turn !== generation) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "暂时无法读取审核问题。");
      form = data;
      if (!form.questions.length) { UI.$("review-question-title").textContent = "本稿没有待裁定的问题"; return; }
      answers = drafts.get(form.token) || Object.fromEntries((form.previous?.answers || []).map(a => [a.id, {choice:a.choice, reason:a.reason}]));
      drafts.set(form.token, answers);
      UI.$("review-next").hidden = false; renderQuestion(); focusQuestion();
    } catch(error) { notice(error.message); }
  }
  function init() {
    if (initialized) return;
    initialized = true;
    document.addEventListener("keydown", event => { if (event.key === "Escape" && dialog().open && !submitting) dialog().close(); });
    UI.$("review-next").addEventListener("click", () => {
      const answer = currentAnswer();
      if (!answer.choice) { notice("先选择这条意见的处理方式。"); return; }
      if (answer.choice === "disagree" && !answer.reason.trim()) { notice("请补充你的判断理由或依据。"); UI.$("review-reason").focus(); return; }
      index++;
      if (index === form.questions.length) renderSummary(); else { renderQuestion(); focusQuestion(); }
    });
    UI.$("review-back").addEventListener("click", () => { if (index > 0) index--; UI.$("review-next").hidden = false; renderQuestion(); focusQuestion(); });
  }
  window.ReviewQuestions = {open, init};
})();
