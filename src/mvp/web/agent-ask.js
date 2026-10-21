/*
 * 需求追问：以悬浮对话的形式一次只问一个关键信息。
 * 主页面保持 Bot 单页展示，这里只负责收集回答并在完成时交回调用方。
 */
(function () {
  "use strict";

  const STORAGE_KEY = "studio-clarify";
  const PLATFORM_KEYS = { "小红书": "xiaohongshu", "公众号": "wechat_article", "朋友圈": "moments", "门店朋友圈": "moments", "门店海报": "poster", "海报": "poster" };

  const MODEL_QUESTION = /(?:确认|选择|指定|哪个|哪款|具体|收录|对应|选).*?(?:型号|机型)|型号.*(?:选择|确认)|知识库里没有找到/;
  const SOFTWARE_QUESTION = /软件|编程|设计类|课程.*(?:要求|指定)/;
  // 新问题自带选项；规则仅用于恢复旧任务或模型没有给出有效选项的情况。
  const RULES = [
    { test: /该机型|这款(?:电脑|机型)|机身重量|具体(?:配置|参数)|多重|重量是多少/, options: ["按知识库资料为准", "没有额外要求"] },
    { test: /软件.*(?:名称|版本)|(?:名称|版本).*软件|什么软件|具体.*软件/, options: ["编程开发，如 VS Code、Python", "平面设计，如 Photoshop、Illustrator", "CAD 或三维建模类软件", "尚未确定具体软件"] },
    { test: /重量.*(?:上限|不超过|多少千克)|上限.*重量/, options: ["不超过 1.5 kg", "不超过 1.8 kg"] },
    { test: /严格|包含.*配件|配件.*(?:费用|预算)|放宽/, options: ["预算含配件，按这个上限来", "可以适当放宽"] },
    { test: /云电脑|虚拟机|兼容层|原生环境/, options: ["可以接受云电脑/虚拟机", "必须 Windows 原生"] },
    { test: /人群|年龄|年级|职业|写给谁|谁看/, options: ["大学新生", "职场新人"] },
    { test: /软件|编程|设计|环境|专业|课程/, options: ["编程开发", "平面设计", "CAD、三维或视频创作", "主要上网、办公和看视频"] },
    { test: /预算|价位|多少钱|价格|报价|经费|元/, options: ["5000 元以内", "5000–8000 元", "8000 元以上", "预算还没确定"] },
    { test: /携带|通勤|背|重量|便携|距离|频率/, options: ["每天通勤/上课都带着", "偶尔带出门，多在室内"] },
    { test: /系统|Windows|macOS|鸿蒙|操作系统/i, options: ["用惯了 Windows", "想用鸿蒙生态"] },
    { test: /平台|发布|小红书|公众号|朋友圈|海报/, options: ["小红书", "公众号", "朋友圈", "门店海报"] },
    { test: /场景|用途|用来做什么|做什么/, options: ["开学季 · 上课", "职场办公"] },
    { test: /续航|电池|充电/, options: ["经常离开插座使用", "大多在有电源的地方使用"] },
    { test: /屏幕|显示|护眼/, options: ["长时间看屏幕，重视护眼", "屏幕够用就行"] },
    { test: /性能|配置|内存|硬盘|容量|参数/, options: ["够用就行，预算优先", "要跑重度任务，性能优先"] }
  ];

  function questionText(question) {
    return String(question && typeof question === "object" ? question.question || "" : question || "").trim();
  }

  function isModelQuestion(question) {
    const text = questionText(question);
    if (SOFTWARE_QUESTION.test(text)) return false;
    return typeof question === "object" && question.field ? question.field === "product" : MODEL_QUESTION.test(text);
  }

  const FIELD_OPTIONS = {
    software: ["编程开发，如 VS Code、Python", "平面设计，如 Photoshop、Illustrator", "CAD 或三维建模类软件", "尚未确定具体软件"],
    system: ["必须在本机使用 Windows", "可以接受鸿蒙系统", "暂时没有确定要求"],
    budget: ["5000 元以内", "5000–8000 元", "8000 元以上", "预算还没确定"],
    audience: ["在校学生", "职场办公人群", "内容创作者", "家庭用户"],
    scenario: ["学习、网课和查资料", "日常办公与通勤", "专业创作", "家庭日常使用"],
    platform: ["小红书", "公众号", "朋友圈", "门店海报"]
  };

  function suggestAnswers(question, meta) {
    const text = questionText(question);
    const candidates = ((meta && meta.candidates) || []).filter(Boolean).map(String);
    const modelQuestion = isModelQuestion(question);
    const supplied = question && Array.isArray(question.options) ? question.options : [];
    const options = [...new Set(supplied.filter(o => typeof o === "string" && o.trim()).map(o => o.trim()))]
      .filter(o => modelQuestion || (!candidates.includes(o) && !/MateBook/i.test(o))).slice(0, 4);
    if (options.length >= 2) return options;
    if (modelQuestion && candidates.length > 0) {
      return [...candidates.slice(0, 3), "按需求帮我推荐"];
    }
    if (question && FIELD_OPTIONS[question.field]) return FIELD_OPTIONS[question.field].slice();
    if (SOFTWARE_QUESTION.test(text)) return FIELD_OPTIONS.software.slice();
    const rule = RULES.find(item => item.test.test(text));
    return rule ? rule.options.slice() : [];
  }

  // 把回答并入下一次运行的简报：型号与平台直接写回字段，其余作为补充文本留给场景解析。
  function applyAnswers(task, answers, meta) {
    const base = task && typeof task === "object" ? task : {};
    const next = { ...base, constraints: Array.isArray(base.constraints) ? [...base.constraints] : [] };
    const history = Array.isArray(base.clarify_answers) ? [...base.clarify_answers] : [];
    const candidates = ((meta && meta.candidates) || []).filter(Boolean).map(String);
    const lines = [];
    for (const item of answers || []) {
      const question = questionText(item && item.question);
      const field = item && item.field || "";
      const answer = String(typeof item === "string" ? item : (item && item.answer) || "").trim();
      if (!answer) continue;
      const modelQuestion = isModelQuestion({ question, field });
      if (modelQuestion && candidates.includes(answer)) next.product = answer;
      else if (modelQuestion && answer === "按需求帮我推荐") next.product = "";
      else if (modelQuestion) next.product = answer;
      if (field === "audience" || (!field && /人群|写给谁|谁看|目标读者/.test(question))) next.audience = answer;
      if (field === "scenario" || (!field && /场景|用途|用在哪|做什么/.test(question))) next.scenario = answer;
      const platform = PLATFORM_KEYS[answer];
      if (platform && (field === "platform" || (!field && /平台|发布|发到|发在/.test(question)))) next.platform = platform;
      history.push({ id: item && item.id || "", field: field || "other", question, answer });
      lines.push(question ? `问：${question}\n答：${answer}` : `补充：${answer}`);
    }
    if (lines.length > 0) next.extra = [base.extra, lines.join("\n\n")].filter(Boolean).join("\n\n");
    next.clarify_answers = history;
    if (lines.length > 0) next.clarify_round = Math.min(2, Math.max(0, Number(base.clarify_round) || 0) + 1);
    return next;
  }

  let session = null;
  let dom = null;

  function readStored() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
    } catch {
      return null;
    }
  }

  function persist() {
    try {
      if (!session) sessionStorage.removeItem(STORAGE_KEY);
      else sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        jobId: session.jobId,
        questions: session.questions,
        specs: session.specs,
        answers: session.answers
      }));
    } catch {
      /* 浏览器禁用存储时仍可正常问答。 */
    }
  }

  function mount() {
    if (dom) return dom;
    dom = {
      panel: UI.$("agent-ask"),
      avatar: UI.$("agent-ask-avatar"),
      title: UI.$("agent-ask-title"),
      hint: UI.$("agent-ask-hint"),
      progress: UI.$("agent-ask-progress"),
      close: UI.$("agent-ask-close"),
      body: UI.$("agent-ask-body"),
      answers: UI.$("agent-ask-answers"),
      asking: UI.$("agent-ask-asking"),
      question: UI.$("agent-ask-question"),
      options: UI.$("agent-ask-options"),
      custom: UI.$("agent-ask-form"),
      input: UI.$("agent-ask-input"),
      done: UI.$("agent-ask-done"),
      count: UI.$("agent-ask-count"),
      back: UI.$("agent-ask-back"),
      pill: UI.$("agent-ask-pill"),
      pillCount: UI.$("agent-ask-pill-count")
    };
    if (!dom.panel) {
      dom = null;
      return null;
    }
    dom.avatar.replaceChildren(window.BotPortrait(1, "#c28c6c"));
    dom.close.addEventListener("click", () => close());
    dom.back.addEventListener("click", () => {
      const onBack = session && session.onBack;
      close({ reset: true });
      if (onBack) onBack();
    });
    dom.custom.addEventListener("submit", event => {
      event.preventDefault();
      answer(dom.input.value);
    });
    dom.input.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.isComposing) {
        event.preventDefault();
        answer(dom.input.value);
      }
    });
    dom.pill.addEventListener("click", () => reopen());
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && dom && !dom.panel.hidden) close();
    });
    return dom;
  }

  function progressText() {
    if (!session) return "";
    const total = session.questions.length;
    const answered = Math.min(session.answers.length, total);
    return answered >= total ? "已回答" : `第 ${session.round} / 2 轮`;
  }

  function render(options) {
    const { animate = true } = options || {};
    if (!session) return;
    const total = session.questions.length;
    const answered = Math.min(session.answers.length, total);
    dom.progress.textContent = progressText();
    dom.hint.textContent = session.round === 1 ? "只确认影响推荐的关键信息，最多两轮" : "最后一轮，根据上次回答再确认一点";
    dom.panel.dataset.state = answered >= total ? "done" : "asking";

    dom.answers.replaceChildren(...session.answers.slice(0, answered).map((item, index) => UI.el("li", {},
      UI.el("span", { class: "ask-check", "aria-hidden": "true" }, "✓"),
      UI.el("span", { class: "ask-answer", title: `${item.question}\n${item.answer}` }, item.answer)
    )));

    const asking = answered < total;
    dom.asking.hidden = !asking;
    dom.done.hidden = asking;

    if (asking) {
      dom.question.textContent = session.questions[answered];
      const spec = session.specs[answered];
      const modelQuestion = isModelQuestion(spec);
      const suggestions = suggestAnswers(spec, { candidates: session.candidates });
      dom.options.replaceChildren(...suggestions.map((text, index) => {
        const button = UI.el("button", { type: "button", class: "ask-option" }, [
          UI.el("span", { class: "ask-option-key", "aria-hidden": "true" }, String.fromCharCode(65 + index)),
          UI.el("span", { class: "ask-option-text" }, text),
          UI.el("span", { class: "ask-option-arrow", "aria-hidden": "true" }, "→")
        ]);
        button.addEventListener("click", () => answer(text));
        return button;
      }));
      dom.input.value = "";
      dom.input.placeholder = spec.placeholder || (modelQuestion ? "也可以填写具体型号…" : "也可以写自己的情况…");
      if (modelQuestion && session.candidates.length > 0) {
        let list = UI.$("agent-ask-models");
        if (!list) {
          list = UI.el("datalist", { id: "agent-ask-models" });
          dom.panel.appendChild(list);
        }
        list.replaceChildren(...session.candidates.map(name => UI.el("option", { value: name })));
        dom.input.setAttribute("list", "agent-ask-models");
      } else {
        dom.input.removeAttribute("list");
      }
      dom.count.textContent = session.round === 2 ? "本次最后一问" : "本轮只问这一点";
    } else {
      dom.count.textContent = session.round === 2 ? "问询已完成" : "带上回答继续";
      if (!dom.done.querySelector(".ask-submit")) {
        const submit = UI.el("button", { type: "button", class: "btn-primary ask-submit" }, [
          UI.el("span", { class: "ask-submit-text" }, "继续创作"),
          UI.el("span", { "aria-hidden": "true" }, "→")
        ]);
        submit.addEventListener("click", finish);
        dom.done.appendChild(submit);
      }
      dom.done.querySelector(".ask-submit").disabled = Boolean(session.submitting);
    }

    if (animate && !prefersReduced()) {
      dom.body.classList.remove("is-swapping");
      void dom.body.offsetWidth;
      dom.body.classList.add("is-swapping");
    }
    if (!animate) dom.body.classList.remove("is-swapping");

    if (session.onProgress) session.onProgress(snapshot());
    focusFirst(asking);
  }

  function focusFirst(asking) {
    if (!dom || dom.panel.hidden) return;
    const target = asking
      ? dom.options.querySelector(".ask-option") || dom.input
      : dom.done.querySelector(".ask-submit");
    if (target && typeof target.focus === "function") {
      try {
        target.focus({ preventScroll: true });
      } catch {
        target.focus();
      }
    }
  }

  function prefersReduced() {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function answer(value) {
    if (!session || session.submitting) return;
    const text = String(value || "").trim();
    if (!text) {
      if (dom && !dom.input.hidden) dom.input.focus({ preventScroll: true });
      return;
    }
    const index = session.answers.length;
    if (index >= session.questions.length) return;
    const spec = session.specs[index];
    session.answers.push({ id: spec.id || "", field: spec.field || "", question: session.questions[index], answer: text });
    persist();
    render({ animate: true });
  }

  function finish() {
    if (!session || session.submitting) return;
    session.submitting = true;
    const answers = session.answers.slice();
    const task = applyAnswers(session.task, answers, { candidates: session.candidates });
    const onComplete = session.onComplete;
    const submit = dom && dom.done.querySelector(".ask-submit");
    if (submit) {
      submit.disabled = true;
      const label = submit.querySelector(".ask-submit-text");
      if (label) label.textContent = "正在继续…";
    }
    if (onComplete) onComplete(answers, task);
  }

  function open(config) {
    if (!mount()) return false;
    const specs = (config.questions || []).map(item => typeof item === "object" && item ? item : { question: questionText(item) })
      .filter(item => questionText(item)).slice(0, 1);
    const questions = specs.map(questionText);
    if (questions.length === 0) return false;
    const stored = readStored();
    const resumes = Boolean(stored) && stored.jobId === config.jobId &&
      JSON.stringify(stored.questions) === JSON.stringify(questions) &&
      JSON.stringify(stored.specs) === JSON.stringify(specs) &&
      Array.isArray(stored.answers);
    session = {
      jobId: config.jobId || "",
      questions,
      specs,
      round: Math.min(2, Math.max(1, Number(config.round) || (Number(config.task?.clarify_round) || 0) + 1)),
      candidates: (config.candidates || []).map(item => typeof item === "string" ? item : item.name || item.id).filter(Boolean),
      task: config.task || {},
      answers: resumes ? stored.answers.filter(item => item && typeof item.answer === "string").slice(0, questions.length) : [],
      submitting: false,
      collapsed: false,
      onComplete: config.onComplete,
      onBack: config.onBack,
      onProgress: config.onProgress
    };
    dom.panel.hidden = false;
    dom.pill.hidden = true;
    dom.body.scrollTop = 0;
    const submit = dom.done.querySelector(".ask-submit");
    if (submit) {
      submit.disabled = false;
      const label = submit.querySelector(".ask-submit-text");
      if (label) label.textContent = "继续创作";
    }
    render({ animate: false });
    return true;
  }

  function reopen() {
    if (!session || !mount()) return;
    session.collapsed = false;
    dom.panel.hidden = false;
    dom.pill.hidden = true;
    render({ animate: false });
  }

  // 追问属于生成过程页；切到别的页时先收起，回来再恢复，避免悬浮层压住作品或简报。
  function setPage(page) {
    if (!session || !mount()) return;
    if (page !== "process") {
      dom.panel.hidden = true;
      dom.pill.hidden = true;
    } else if (session.collapsed) {
      dom.panel.hidden = true;
      dom.pill.hidden = false;
    } else {
      dom.panel.hidden = false;
      dom.pill.hidden = true;
    }
  }

  function close(options) {
    const { reset = false } = options || {};
    if (!dom && !session) return;
    if (!mount()) return;
    dom.panel.hidden = true;
    dom.body.classList.remove("is-swapping");
    if (reset || !session || session.submitting) {
      session = null;
      persist();
      dom.pill.hidden = true;
    } else {
      session.collapsed = true;
      dom.pill.hidden = false;
      const total = session.questions.length;
      const answered = Math.min(session.answers.length, total);
      dom.pillCount.textContent = answered >= total ? "完成" : `${answered + 1}/${total}`;
      try {
        dom.pill.focus({ preventScroll: true });
      } catch {
        /* 旧浏览器忽略焦点选项。 */
      }
    }
  }

  function snapshot() {
    if (!session) return null;
    const total = session.questions.length;
    const answered = Math.min(session.answers.length, total);
    return {
      index: Math.min(answered + 1, total),
      total,
      answered,
      done: answered >= total,
      question: answered < total ? session.questions[answered] : ""
    };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { suggestAnswers, applyAnswers };
  } else {
    window.AgentAsk = { open, close, reopen, setPage, snapshot, suggestAnswers, applyAnswers };
    window.clarifySnapshot = snapshot;
  }
})();
