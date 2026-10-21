(function () {
  "use strict";
  const el = window.UI.el;
  const choices = [
    ["fix", "接受意见，按建议修改", "保留原有事实依据，修改这条问题后再审核。"],
    ["disagree", "我认为原文可用", "补充判断理由，交由模型复审，或最后人工裁定采用。"],
    ["defer", "暂时无法确认", "保留这个问题，继续核对资料或稍后处理。"]
  ];
  const locations = {title:"标题", lead:"导语", body:"正文", caption:"图注", cta:"行动引导", article:"整篇稿件", poster:"海报"};
  let result, form, answers, index = 0, submitting = false, generation = 0, initialized = false;
  const drafts = new Map();
  const dialog = () => UI.$("review-dialog");
  const body = () => UI.$("review-question-body");
  const replaceBody = (...children) => body().replaceChildren(...children.filter(child => child != null && child !== false));
  function notice(message) { UI.$("review-question-error").textContent = message; }
  function currentAnswer() { return answers[form.questions[index].id] ||= { choice:"", reason:"" }; }
  function focusQuestion() { UI.$("review-question-title").focus({preventScroll:true}); dialog().scrollTop = 0; body().scrollTop = 0; }
  function evidence(question) {
    const claim = (result.verification?.facts || []).find(c => c.where === question.where && c.index === question.index);
    const related = form.facts.filter(f => claim?.fact_ids?.includes(f.id));
    const facts = related.length ? related : form.facts.slice(0, 3);
    if (!facts.length) return null;
    return el("details", {class:"review-question-evidence"}, el("summary", {}, related.length ? "查看这句引用的事实依据" : "查看本稿资料（本条是否获支持仍需判断）"),
      ...facts.map(f => el("section", {}, el("b", {}, `${f.id} · ${f.source?.title || f.source?.label || "产品资料"}`),
        el("p", {}, f.text || ""), ...(f.conditions || []).map(c => el("p", {}, `适用条件：${c.text || c}`)))));
  }
  function triage() {
    const s = form.summary || {};
    return el("section", {class:"review-triage"},
      el("p", {}, `需人工确认 ${form.questions.length} 项 · 自动处理 ${s.automatic || 0} 项 · 可选优化 ${s.optional || 0} 项`),
      el("small", {}, `交叉核对已排除 ${s.dismissed || 0} 项误报，合并 ${s.merged || 0} 条重复意见。`),
      ...[["automatic_issues", "自动修订或重试，无需逐条裁定"], ["suggestions", "可选优化，不影响通过"], ["dismissed", "已排除的意见与依据"]].map(([key, label]) =>
        form[key]?.length ? el("details", {}, el("summary", {}, `${label}（${form[key].length}）`),
          el("ul", {}, ...form[key].map(p => el("li", {}, p.detail, p.cross_reason ? el("small", {}, p.cross_reason) : null,
            p.generated_observation ? el("small", {}, `成图：${p.generated_observation}`) : null,
            p.reference_observation ? el("small", {}, `依据图：${p.reference_observation}`) : null,
            p.article_quote ? el("small", {}, `核对原句：${p.article_quote}`) : null,
            ...(p.evidence || []).map(e => el("small", {}, `${e.fact_id}：${e.quote}`)))))) : null));
  }
  function renderQuestion() {
    notice("");
    const question = form.questions[index], answer = currentAnswer();
    UI.$("review-question-meta").textContent = `重要未决 · ${index + 1} / ${form.questions.length}`;
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
    replaceBody(triage(), el("section", {class:"review-question-problem"},
      el("span", {class:"section-label"}, `${locations[question.where] || "作品"} · ${question.type === "expression" ? "表达改进" : "待核对问题"}`),
      question.quote ? el("blockquote", {}, question.quote) : null,
      el("p", {}, question.detail), question.cross_reason ? el("p", {}, `交叉核对：${question.cross_reason}`) : null,
      ...(question.evidence || []).map(e => el("p", {}, `${e.fact_id}：${e.quote}`)),
      question.occurrences > 1 ? el("details", {}, el("summary", {}, `查看涉及的 ${question.occurrences} 处原文`),
        ...question.members.map(p => el("section", {}, el("b", {}, locations[p.where] || "作品"), el("blockquote", {}, p.quote), el("p", {}, p.detail)))) : null,
      question.direction ? el("p", {class:"review-direction"}, `修改方向：${question.direction}`) : null),
      evidence(question), el("fieldset", {class:"review-choices"}, el("legend", {class:"sr-only"}, "选择这条意见的处理方式"), ...radios),
      el("label", {for:"review-reason", id:"review-reason-label"}, answer.choice === "disagree" ? "你的判断理由（必填）" : "补充说明（选填）"), reasoning);
    UI.$("review-back").disabled = index === 0;
    UI.$("review-next").textContent = index === form.questions.length - 1 ? "核对并提交 →" : "下一条 →";
    UI.$("review-next").disabled = false;
    UI.$("review-next").hidden = false;
    UI.$("review-question-actions").hidden = false;
  }
  function renderSummary() {
    notice("");
    UI.$("review-question-meta").textContent = "终审反馈 · 提交评审";
    UI.$("review-question-title").textContent = form.questions.length ? "评审已答完，可以提交了" : "继续处理审核结果";
    const automatic = form.automatic_issues?.length || 0;
    const canAdopt = form.questions.length > 0 && !automatic && form.questions.every(q => answers[q.id]?.choice === "disagree");
    const prior = form.previous;
    const counts = Object.fromEntries(["fix", "disagree", "defer"].map(choice => [choice, form.questions.filter(q => answers[q.id]?.choice === choice).length]));
    const actionable = form.questions.length > 0 || automatic > 0;
    const resolution = automatic || counts.fix || counts.disagree ? "continue" : "hold";
    const effect = [counts.fix ? `${counts.fix} 项按建议修改` : "", counts.disagree ? `${counts.disagree} 项结合你的理由复审` : "",
      counts.defer ? `${counts.defer} 项继续保留待确认` : "", automatic ? `${automatic} 项自动修订或重试` : ""].filter(Boolean).join("；");
    replaceBody(triage(), form.questions.length ? el("details", {class:"review-summary-details"}, el("summary", {}, `已确认 ${form.questions.length} 个重要事项 · 展开查看`),
      el("ol", {class:"review-decision-summary"}, ...form.questions.map(q => el("li", {},
      el("span", {}, q.detail), el("b", {}, choices.find(c => c[0] === answers[q.id].choice)?.[1]),
      answers[q.id].reason ? el("small", {}, answers[q.id].reason) : null)))) : null,
      el("p", {class:"review-submit-effect"}, prior?.next_job ? "评审结果已提交，请查看后续任务。" : actionable ? `提交后：${effect}。` : "没有需要人工确认的风险。"),
      !prior?.next_job && (counts.fix || automatic) ? el("p", {class:"dialog-copy"}, "你选择的修改尚未执行，提交后会先处理，再核验结果。") : null,
      !prior?.next_job && actionable ? el("details", {class:"review-summary-details"}, el("summary", {}, "其他处理方式"),
        el("div", {class:"review-resolution"},
          canAdopt ? el("button", {type:"button", class:"review-resolution-option", onclick:() => submit("adopt")},
            el("b", {}, "人工采用当前稿"), el("small", {}, "按你的理由保留原稿，自动审核意见仍会留存。")) : null,
          resolution !== "hold" ? el("button", {type:"button", class:"review-resolution-option", onclick:() => submit("hold")},
            el("b", {}, "只保存评审，稍后处理"), el("small", {}, "保存全部选择，暂不执行修改或复审。")) : null)) : null);
    UI.$("review-back").disabled = !form.questions.length;
    UI.$("review-next").textContent = prior?.next_job ? "查看处理进度 →" : form.questions.length ? "提交评审结果 →" : "自动修订或重试 →";
    UI.$("review-next").disabled = false;
    UI.$("review-next").hidden = !actionable && !prior?.next_job;
    UI.$("review-question-actions").hidden = !actionable && !prior?.next_job;
    UI.$("review-next").dataset.resolution = resolution;
    focusQuestion();
  }
  async function submit(resolution) {
    if (submitting) return;
    submitting = true; notice(form.questions.length ? "正在提交评审结果…" : "正在提交自动处理…");
    UI.$("review-back").disabled = true;
    UI.$("review-next").disabled = true;
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
      answers = drafts.get(form.token) || Object.fromEntries((form.previous?.answers || []).map(a => [a.id, {choice:a.choice, reason:a.reason}]));
      drafts.set(form.token, answers);
      if (!form.questions.length) { renderSummary(); return; }
      if (form.previous?.next_job || form.questions.every(q => answers[q.id]?.choice &&
          (answers[q.id].choice !== "disagree" || answers[q.id].reason?.trim()))) {
        index = form.questions.length; renderSummary(); return;
      }
      UI.$("review-next").hidden = false; renderQuestion(); focusQuestion();
    } catch(error) { notice(error.message); }
  }
  function init() {
    if (initialized) return;
    initialized = true;
    document.addEventListener("keydown", event => { if (event.key === "Escape" && dialog().open && !submitting) dialog().close(); });
    UI.$("review-next").addEventListener("click", () => {
      if (submitting || !form) return;
      if (index >= form.questions.length) {
        if (form.previous?.next_job) {
          dialog().close(); window.dispatchEvent(new CustomEvent("review-followup", {detail:{job:form.previous.next_job, task:result.task}}));
        } else submit(UI.$("review-next").dataset.resolution);
        return;
      }
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
