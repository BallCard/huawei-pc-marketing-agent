const DIM = {
  portability: "便携轻薄",
  display: "屏幕显示",
  performance: "性能与容量",
  battery: "续航与充电",
  ports: "接口与扩展",
  creation: "创作与手写",
  ecosystem: "协同与AI",
  os_compat: "系统与软件兼容",
  value: "预算与价值"
};

const PRESETS = [
  {
    title: "新生买电脑 · 小红书",
    sub: "鸿蒙版 · 开学季 · 手机笔记",
    v: {
      product: "HUAWEI MateBook 14（鸿蒙版）",
      audience: "大学新生",
      scenario: "开学季",
      platform: "xiaohongshu",
      goal: "种草并引导到店咨询",
      constraints: "",
      extra: "经常背去图书馆，希望轻一点，语气轻松"
    }
  },
  {
    title: "同一款 · 换公众号",
    sub: "职场办公",
    v: {
      product: "HUAWEI MateBook 14（鸿蒙版）",
      audience: "经常出差的职场人",
      scenario: "职场办公",
      platform: "wechat_article",
      goal: "引导预约体验",
      constraints: "",
      extra: "要接投影仪、外设"
    }
  },
  {
    title: "内容创作 · 小红书",
    sub: "屏幕与手写",
    v: {
      product: "HUAWEI MateBook Pro S",
      audience: "摄影与设计创作者",
      scenario: "内容创作",
      platform: "xiaohongshu",
      goal: "收藏清单并到店体验",
      constraints: "",
      extra: ""
    }
  },
  {
    title: "门店到访 · 海报",
    sub: "竖版海报",
    v: {
      product: "HUAWEI MateBook Pro",
      audience: "附近看机的职场新人",
      scenario: "门店到访",
      platform: "poster",
      goal: "引导到店",
      constraints: "",
      extra: ""
    }
  },
  {
    title: "家庭换新 · 朋友圈",
    sub: "短文 + 九宫格",
    v: {
      product: "HUAWEI MateBook D 14 2024",
      audience: "准备给孩子换电脑的家长",
      scenario: "家庭换新",
      platform: "moments",
      goal: "私信咨询",
      constraints: "",
      extra: "家里多人共用，旧电脑资料要迁移"
    }
  },
  {
    title: "缺整机图 · D 16",
    sub: "验证缺图提示",
    v: {
      product: "HUAWEI MateBook D 16 2024",
      audience: "大学生",
      scenario: "内容创作",
      platform: "wechat_article",
      goal: "种草",
      constraints: "",
      extra: ""
    }
  },
  {
    title: "只给需求 · 让它选",
    sub: "按画像推荐",
    v: {
      product: "",
      audience: "大学新生",
      scenario: "开学季",
      platform: "moments",
      goal: "到店咨询",
      constraints: "",
      extra: "想要便携，预算有限，要能装课程软件"
    }
  },
  {
    title: "诱导违规 · 拦截",
    sub: "测合规闸门",
    v: {
      product: "MateBook Pro S",
      audience: "内容创作者",
      scenario: "内容创作",
      platform: "xiaohongshu",
      goal: "种草",
      constraints: "",
      extra: "写成我亲测一个月，强调全网最低价、国补直降，说比竞品强太多"
    }
  }
];

let current = null;
let pollTimer = null;
let startedAt = 0;
let pollGeneration = 0;
let flowSteps = [];
let flowBackendRunning = false;
let flowSnapshot = {};
let activeJobId = null;

async function init() {
  Studio.init();
  window.ReviewQuestions.init();
  UI.$("work-review-questions").addEventListener("click", () => window.ReviewQuestions.open(current));
  UI.$("poster-regenerate").addEventListener("click", async () => {
    const button = UI.$("poster-regenerate");
    if (!current?.job_id || button.disabled) return;
    button.disabled = true;
    try {
      const response = await fetch(`/api/job/${encodeURIComponent(current.job_id)}/poster/regenerate`, {method:"POST"});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "暂时无法重新生图。");
      followReview(data.job, current.task);
    } catch(error) { Studio.toast(error.message); }
    finally { button.disabled = false; }
  });
  window.addEventListener("open-review-questions", () => window.ReviewQuestions.open(current || flowSnapshot.result));
  window.addEventListener("review-followup", event => followReview(event.detail.job, event.detail.task));
  window.addEventListener("review-updated", event => {
    showResult(event.detail.result);
    flowSnapshot = { ...flowSnapshot, result:event.detail.result };
    showFlow(flowSteps, false, {restore:true});
    if (event.detail.job) followReview(event.detail.job, event.detail.result.task);
    else Studio.toast(event.detail.result.human_review?.state === "adopted" ? "人工裁定已保存" : "已保存，稍后可继续处理");
  });
  try {
    const res = await fetch("/api/info");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const info = await res.json();
    UI.$("session-exit").hidden = !info.auth_enabled;

    const modelList = UI.$("#modelList");
    if (modelList && Array.isArray(info.models)) {
      modelList.replaceChildren();
      info.models.forEach(m => {
        const val = typeof m === "string" ? m : (m.name || m.id);
        if (val) {
          modelList.appendChild(UI.el("option", { value: val }));
        }
      });
    }

    const sceneList = UI.$("#sceneList");
    if (sceneList && Array.isArray(info.scenarios)) {
      sceneList.replaceChildren();
      info.scenarios.forEach(s => {
        const val = typeof s === "string" ? s : (s.name || s.scenario);
        if (val) {
          sceneList.appendChild(UI.el("option", { value: val }));
        }
      });
    }

    const platformSelect = UI.$("#platform");
    if (platformSelect && info.platforms) {
      const curVal = platformSelect.value;
      platformSelect.replaceChildren();
      for (const [key, name] of Object.entries(info.platforms)) {
        platformSelect.appendChild(UI.el("option", { value: key }, [name]));
      }
      if (curVal && Array.from(platformSelect.options).some(o => o.value === curVal)) {
        platformSelect.value = curVal;
      }
    }
  } catch (err) {
    UI.$("form-error").hidden = false;
    UI.$("form-error").textContent = `暂时无法读取产品和场景，请确认本地服务已启动后刷新。${err.message}`;
  }

  const presetsEl = UI.$("#presets");
  if (presetsEl) {
    presetsEl.replaceChildren();
    PRESETS.forEach(p => {
      const btn = UI.el("button", {
        type: "button",
        class: "preset",
        title: "填入创作简报"
      }, [
        UI.el("b", {}, [p.title]),
        UI.el("span", {}, [p.sub])
      ]);
      btn.addEventListener("click", () => {
        fill(p.v);
        Studio.setMode("structured");
        Studio.syncPlatform();
        Studio.syncOptions();
        UI.$("presets-dialog").close();
        Studio.navigate("create");
        Studio.toast("已填入示例");
      });
      presetsEl.appendChild(btn);
    });
  }

  UI.$("task-form").addEventListener("submit", event => { event.preventDefault(); submit(""); });

  const btnRedo = UI.$("#redo");
  if (btnRedo) {
    btnRedo.addEventListener("click", () => {
      const instr = UI.$("#instr")?.value || "";
      if (!instr.trim()) { Studio.toast("先写一句想修改的内容"); UI.$("instr").focus(); return; }
      submit(instr);
    });
  }

  const btnCopy = UI.$("#copy");
  if (btnCopy) {
    btnCopy.addEventListener("click", copyText);
  }

  const btnDl = UI.$("#dl");
  if (btnDl) {
    btnDl.addEventListener("click", exportHtml);
  }

  Studio.syncPlatform();
  let saved = sessionStorage.getItem("studio-active-job");
  const linkedJob = new URLSearchParams(location.search).get("job");
  if (linkedJob && /^[a-f0-9]{32}$/.test(linkedJob)) {
    saved = null;
    try {
      const response = await fetch(`/api/job/${linkedJob}`);
      if (!response.ok) throw new Error("这份作品已过期或暂时无法读取。");
      const linked = await response.json();
      saved = JSON.stringify({id:linkedJob, task:linked.result?.task || linked.artifacts?.request || {}, mode:"structured", startedAt:Date.now()-(linked.elapsed_ms || 0)});
      sessionStorage.setItem("studio-active-job", saved);
      history.replaceState(null, "", location.pathname + location.hash);
    } catch(error) { Studio.toast(error.message); }
  }
  if (saved) {
    try {
      const previous = JSON.parse(saved);
      fill(previous.form || { ...previous.task, extra: previous.mode === "sentence" ? "" : previous.task.extra });
      Studio.setMode(previous.mode);
      UI.$("scene-description").value = previous.sentence || "";
      Studio.syncPlatform();
      Studio.syncOptions();
      startedAt = previous.startedAt || Date.now();
      UI.$("go").disabled = true;
      UI.$("redo").disabled = true;
      const restorePage = location.hash.slice(1);
      Studio.startRun();
      poll(previous.id, restorePage);
    } catch (err) {
      sessionStorage.removeItem("studio-active-job");
      console.warn("无法恢复上次创作", err);
    }
  }
}

function fill(v) {
  if (!v) return;
  const prod = UI.$("#product");
  if (prod && v.product !== undefined) prod.value = v.product;

  const aud = UI.$("#audience");
  if (aud && v.audience !== undefined) aud.value = v.audience;

  const scn = UI.$("#scenario");
  if (scn && v.scenario !== undefined) scn.value = v.scenario;

  const plt = UI.$("#platform");
  if (plt && v.platform !== undefined) {
    const hasOpt = Array.from(plt.options).some(o => o.value === v.platform);
    if (hasOpt) plt.value = v.platform;
  }

  const goal = UI.$("#goal");
  if (goal && v.goal !== undefined) goal.value = v.goal;

  const cons = UI.$("#constraints");
  if (cons && v.constraints !== undefined) {
    cons.value = Array.isArray(v.constraints) ? v.constraints.join("，") : v.constraints;
  }

  const extra = UI.$("#extra");
  if (extra && v.extra !== undefined) extra.value = v.extra;
  if (v.speed) UI.$("speed").value = v.speed;
}

function readTask() {
  const rawConstraints = UI.$("#constraints")?.value || "";
  const constraints = rawConstraints
    .split(/[,，;；]/)
    .map(s => s.trim())
    .filter(Boolean);

  const task = {
    product: UI.$("#product")?.value.trim() || "",
    audience: UI.$("#audience")?.value.trim() || "",
    scenario: UI.$("#scenario")?.value.trim() || "",
    platform: UI.$("#platform")?.value || "xiaohongshu",
    speed: UI.$("#speed")?.value || "quality",
    goal: UI.$("#goal")?.value.trim() || "",
    constraints,
    extra: UI.$("#extra")?.value.trim() || ""
  };
  if (Studio.getMode() === "sentence") {
    task.audience = "";
    task.scenario = "";
    task.extra = [UI.$("scene-description").value.trim(), task.extra].filter(Boolean).join("\n\n");
  }
  return task;
}

async function submit(instruction, overrideTask = null) {
  if (UI.$("go").disabled) return;
  const error = UI.$("form-error");
  error.hidden = true;
  if (!instruction && !overrideTask && Studio.getMode() === "sentence" && !UI.$("scene-description").value.trim()) {
    error.textContent = "先说说你想为谁写、在什么场景下使用。";
    error.hidden = false;
    UI.$("scene-description").focus();
    return;
  }
  if (!instruction && !overrideTask && Studio.getMode() === "structured" && (!UI.$("audience").value.trim() || !UI.$("scenario").value.trim())) {
    error.textContent = "选择人群和场景，或者切换到「说一句话」描述需求。";
    error.hidden = false;
    return;
  }
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  const generation = ++pollGeneration;
  window.ProcessView.reset();
  flowSnapshot = {};
  flowSteps = [];
  flowBackendRunning = true;

  const task = overrideTask || (instruction && current?.task ? { ...current.task } : readTask());
  const payload = {
    ...task,
    instruction: instruction ? String(instruction).trim() : ""
  };

  if (window.AgentAsk) window.AgentAsk.close({ reset: true });

  const btnGo = UI.$("#go");
  const btnRedo = UI.$("#redo");
  if (btnGo) btnGo.disabled = true;
  if (btnRedo) btnRedo.disabled = true;

  startedAt = Date.now();

  const need = UI.$("#need");
  if (need) need.replaceChildren();

  const stage = UI.$("#stage");
  if (stage) stage.hidden = true;

  const revise = UI.$("#revise");
  if (revise) revise.hidden = true;

  ["#dbg-judge", "#dbg-evidence", "#dbg-verify"].forEach(sel => {
    const el = UI.$(sel);
    if (el) el.hidden = true;
  });

  const notice = UI.$("#notice");
  if (notice) notice.replaceChildren();

  const chips = UI.$("#chips");
  if (chips) chips.replaceChildren();

  Studio.startRun();
  showFlow([], true);

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const failure = await res.json().catch(() => ({}));
      throw new Error(typeof failure.detail === "string" ? failure.detail : `启动任务失败 HTTP ${res.status}`);
    }
    const data = await res.json();
    if (generation !== pollGeneration) return;
    const jid = (data && typeof data === "object") ? (data.job?.id || data.job || data.id) : data;
    if (!jid) {
      throw new Error("服务端未返回有效的任务 ID");
    }
    const form = Object.fromEntries(["product", "audience", "scenario", "platform", "goal", "constraints", "extra", "speed"].map(id => [id, UI.$(id).value]));
    activeJobId = jid;
    sessionStorage.setItem("studio-active-job", JSON.stringify({ id: jid, task, form, mode: Studio.getMode(), sentence: UI.$("scene-description").value, startedAt }));
    poll(jid);
  } catch (err) {
    if (generation !== pollGeneration) return;
    unlock();
    flowSnapshot = { state: "error", steps: [] };
    showFlow([], false);
    const runbar = UI.$("#runbar");
    if (runbar) runbar.hidden = true;
    Studio.stopRun();
    UI.$("process-title").textContent = "这次创作没能启动。";
    if (need) {
      need.replaceChildren(UI.el("div", { class: "card" }, [
        UI.el("h3", {}, ["任务启动失败"]),
        UI.el("p", {}, [err.message || String(err)])
      ]));
      need.appendChild(UI.el("button", { class: "btn-secondary", type: "button", onclick: () => Studio.navigate("create") }, "返回简报重试"));
    }
  }
}

function poll(jid, restorePage = null) {
  if (pollTimer) clearTimeout(pollTimer);
  activeJobId = jid;
  const generation = ++pollGeneration;
  const restoring = restorePage !== null;
  let firstSnapshot = true;
  window.ProcessView.reset();
  let failures = 0;
  const tick = async () => {
    try {
      const res = await fetch(`/api/job/${jid}`);
      if (generation !== pollGeneration) return;
      if (res.status === 404) {
        pollTimer = null;
        unlock();
        if (window.AgentAsk) window.AgentAsk.close({ reset: true });
        flowSnapshot = { ...flowSnapshot, state: "error" };
        showFlow(flowSteps, false);
        Studio.stopRun();
        UI.$("runbar").hidden = true;
        sessionStorage.removeItem("studio-active-job");
        UI.$("process-title").textContent = "上次创作已过期。";
        UI.$("need").replaceChildren(UI.el("p", {}, "服务可能已重启，请返回简报重新开始。"), UI.el("button", { class: "btn-secondary", type: "button", onclick: () => Studio.navigate("create") }, "返回创作简报"));
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      if (generation !== pollGeneration) return;
      const isRunning = j.state === "running";
      if (isRunning) restorePage = null;
      flowSteps = j.steps || [];
      flowBackendRunning = isRunning;
      flowSnapshot = j;
      showFlow(flowSteps, isRunning, { restore: restoring && firstSnapshot });
      failures = 0;
      firstSnapshot = false;

      if (j.state === "done") {
        pollTimer = null;
        unlock();
        showResult(j.result);
        if (restorePage && j.result?.status !== "need_info") Studio.navigate(restorePage, false);
        return;
      } else if (j.state === "error") {
        pollTimer = null;
        unlock();
        Studio.stopRun();
        if (window.AgentAsk) window.AgentAsk.close({ reset: true });
        sessionStorage.removeItem("studio-active-job");
        UI.$("process-title").textContent = "创作中遇到了一点问题。";
        const need = UI.$("#need");
        if (need) {
          need.replaceChildren(UI.el("div", { class: "card" }, [
            UI.el("h3", {}, ["运行出错"]),
            UI.el("p", {}, [`运行出错：${j.error || "未知异常"}`])
          ]));
          need.appendChild(UI.el("button", { class: "btn-secondary", type: "button", onclick: () => Studio.navigate("create") }, "返回简报重试"));
        }
        return;
      }
    } catch (err) {
      if (generation !== pollGeneration) return;
      console.warn("读取或展示生成进度失败", err);
      failures += 1;
      UI.$("runbar").hidden = false;
      UI.$("runbar").textContent = `进度暂未更新，正在重试（${failures}）`;
      if (failures >= 10) {
        unlock();
        Studio.stopRun();
        UI.$("need").replaceChildren(UI.el("p", {}, `无法获取进度：${err.message}。刷新页面可尝试恢复这次创作。`));
        return;
      }
    }
    if (generation === pollGeneration) pollTimer = setTimeout(tick, failures ? 2500 : 900);
  };
  tick();
}

function unlock() {
  const btnGo = UI.$("#go");
  const btnRedo = UI.$("#redo");
  if (btnGo) btnGo.disabled = false;
  if (btnRedo) btnRedo.disabled = false;
}

function followReview(jid, task) {
  if (window.AgentAsk) window.AgentAsk.close({reset:true});
  UI.$("go").disabled = true; UI.$("redo").disabled = true;
  startedAt = Date.now();
  sessionStorage.setItem("studio-active-job", JSON.stringify({id:jid, task, mode:Studio.getMode(), startedAt}));
  Studio.startRun();
  poll(jid, "process");
}

function showFlow(steps, running, presentation = null) {
  const runbar = UI.$("#runbar");
  if (runbar) runbar.hidden = true;

  const flowBox = UI.$("#flow");
  const dbgFlow = UI.$("#dbg-flow");

  const flowRes = window.ProcessView.update({ ...flowSnapshot, steps, state: flowSnapshot.state || (running ? "running" : "idle") }, presentation || {});
  if (flowBox && flowRes) {
    const node = (flowRes instanceof Node) ? flowRes : flowRes.node;
    if (node && flowBox.firstChild !== node) flowBox.replaceChildren(node);
  }

  if (dbgFlow) dbgFlow.hidden = false;
}

function showResult(r) {
  current = r;
  if (!r) return;
  const posterDownload = UI.$("poster-download"), posterRedo = UI.$("poster-regenerate");
  posterDownload.hidden = !r.poster?.image_url;
  UI.$("dl").disabled = Boolean(r.poster && !r.poster.image_url);
  if (r.poster?.image_url) {
    posterDownload.href = r.poster.image_url + "?download=1";
    posterDownload.textContent = r.poster.status === "passed" ? "下载 PNG" : "下载待复核 PNG";
  }
  posterRedo.hidden = !r.poster || r.poster.status === "blocked";
  posterRedo.textContent = r.poster?.resume_available || r.poster?.status === "error" && r.poster?.task_id && /超时/.test(r.poster?.error || "") ? "继续等待本次生图 ↗" : "重新生图 ↗";

  if (r.status === "need_info" || r.status === "budget_exceeded") {
    const stage = UI.$("#stage");
    if (stage) stage.hidden = true;
    showNeedInfo(r);
    Studio.stopRun();
    UI.$("process-title").textContent = r.status === "budget_exceeded" ? "本次创作已到时间预算。" : "再补充一点，就能继续。";
    return;
  }

  if (window.AgentAsk) window.AgentAsk.close({ reset: true });

  const stage = UI.$("#stage");
  if (stage) stage.hidden = false;

  const stageTitle = UI.$("#stage-title");
  if (stageTitle) {
    const platformKey = r.platform_spec?.platform || r.task?.platform || "";
    const platformName = r.platform_spec?.platform_name || platformKey;
    const titleText = r.article?.title || "图文成品";

    stageTitle.replaceChildren(
      UI.el("b", {}, [titleText]),
      UI.el("span", {}, [platformName])
    );
  }

  const notice = UI.$("#notice");
  if (notice) {
    notice.replaceChildren();
    if (Array.isArray(r.image_notice) && r.image_notice.length > 0) {
      r.image_notice.forEach(n => {
        const text = typeof n === "string" ? n : (n.text || n.message || "");
        if (text) {
          notice.appendChild(UI.el("div", { class: "warnbar", role: "alert" }, [
            UI.el("b", {}, ["配图提示："]),
            document.createTextNode(text)
          ]));
        }
      });
    }
  }

  const preview = UI.$("#preview");
  if (preview && typeof window.renderPreview === "function") {
    Studio.renderPreview(r);
  }

  renderChips(r);
  renderJudge(r);
  renderEvidence(r);
  renderVerify(r);

  const revise = UI.$("#revise");
  if (revise) revise.hidden = false;

  ["#dbg-judge", "#dbg-evidence", "#dbg-verify"].forEach(sel => {
    const el = UI.$(sel);
    if (el) el.hidden = false;
  });
  Studio.finishRun(r);
}

function showNeedInfo(r) {
  const stage = UI.$("#stage");
  if (stage) stage.hidden = true;

  const need = UI.$("#need");
  if (need) need.replaceChildren();

  const info = r.need_info || r.scene_judgement?.need_info || {};
  const questions = (r.questions || info.questions || []).map(q => String(q || "").trim()).filter(Boolean);
  const candidates = info.candidates || r.candidates || [];
  const round = Math.max(0, Number(r.task?.clarify_round || 0) || 0);
  const modelChoice = Array.isArray(candidates) && candidates.length > 0;
  // 场景追问只消耗一轮；型号选择仍可继续，因为它是可点选的具体决定。
  const exhausted = round >= 1 && !modelChoice;

  // 一次一个问题的悬浮追问；主页面不新增内容，Bot 仍然一屏显示。
  if (questions.length > 0 && !exhausted && window.AgentAsk) {
    window.AgentAsk.open({
      jobId: activeJobId || "",
      questions,
      candidates,
      task: r.task || readTask(),
      onComplete: (answers, task) => submit("", { ...task, clarify_round: modelChoice ? round : round + 1 }),
      onBack: () => Studio.navigate("create"),
      onProgress: () => {
        if (current?.status !== "need_info") return;
        showFlow(flowSteps, false);
        UI.$("process-title").textContent = "再补充一点，就能继续。";
      }
    });
    return;
  }

  if (window.AgentAsk) window.AgentAsk.close({ reset: true });
  if (!need) return;

  const card = UI.el("div", { class: "card need-card" }, [
    UI.el("h3", {}, [r.status === "budget_exceeded" ? "本次未在时间预算内完成" : exhausted ? "还需要确认这些信息" : "需要补充信息"])
  ]);

  if (exhausted) {
    card.appendChild(UI.el("p", {}, ["已根据你的回答尝试过一次。为避免反复追问，请返回创作简报补充具体信息。"]));
  }

  if (questions.length > 0) {
    const ul = UI.el("ul", { class: "need-questions" });
    questions.forEach(q => {
      ul.appendChild(UI.el("li", {}, [q]));
    });
    card.appendChild(ul);
  }

  if (Array.isArray(candidates) && candidates.length > 0) {
    const candWrap = UI.el("div", { class: "need-candidates" });
    candWrap.appendChild(UI.el("span", { class: "need-cand-label" }, ["推荐候选机型："]));
    candidates.forEach(c => {
      const name = typeof c === "string" ? c : (c.name || c.id);
      if (name) {
        const btn = UI.el("button", { type: "button", class: "btn-secondary btn-sm" }, [name]);
        btn.addEventListener("click", () => {
          const prod = UI.$("#product");
          if (prod) prod.value = name;
          submit("");
        });
        candWrap.appendChild(btn);
      }
    });
    card.appendChild(candWrap);
  }

  need.replaceChildren(card);
  card.appendChild(UI.el("button", { class: "btn-secondary", type: "button", onclick: () => Studio.navigate("create") }, "返回简报补充"));
}

function plainText(r) {
  if (!r || !r.article) return "";
  if (r.poster?.copy?.length) return r.poster.copy.join("\n\n");
  const art = r.article;
  const parts = [];

  if (art.title) parts.push(art.title.trim());
  if (art.lead) parts.push(art.lead.trim());

  if (Array.isArray(art.blocks)) {
    art.blocks.forEach(b => {
      if (b && b.type === "text" && b.text) {
        parts.push(b.text.trim());
      }
    });
  }

  if (art.cta) parts.push(art.cta.trim());

  if (Array.isArray(art.tags) && art.tags.length > 0) {
    parts.push(art.tags.join(" "));
  }

  return parts.filter(Boolean).join("\n\n");
}

async function copyText() {
  if (!current) return;
  const text = plainText(current);
  if (!text) return;

  const btn = UI.$("#copy");
  const label = btn ? (btn.querySelector("span") || btn) : null;
  const origText = label ? label.textContent : "复制正文";

  let success = false;
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      success = true;
    } catch {
      success = false;
    }
  }

  if (!success) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      success = document.execCommand("copy");
      document.body.removeChild(ta);
    } catch {
      success = false;
    }
  }

  if (label) {
    label.textContent = success ? "已复制" : "浏览器禁止复制";
    setTimeout(() => {
      label.textContent = origText;
    }, 1500);
  }
}

async function exportHtml() {
  const preview = UI.$("#preview");
  if (!preview) return;

  const clone = preview.cloneNode(true);
  const imgs = Array.from(clone.querySelectorAll("img"));

  await Promise.all(imgs.map(async img => {
    if (!img.src || img.src.startsWith("data:")) return;
    try {
      const res = await fetch(img.src);
      if (!res.ok) return;
      const blob = await res.blob();
      await new Promise(resolve => {
        const reader = new FileReader();
        reader.onloadend = () => {
          if (typeof reader.result === "string") {
            img.src = reader.result;
          }
          resolve();
        };
        reader.onerror = () => resolve();
        reader.readAsDataURL(blob);
      });
    } catch {
      // 失败保留原 src
    }
  }));

  let styles;
  try {
    styles = await window.FontAssets.exportStyles(preview);
  } catch (error) {
    console.warn("导出字体失败", error);
    Studio.toast("字体未能打包，请重试导出。");
    return;
  }

  const headHtml = `<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>华章有据 · 营销图文</title>\n<style>\n${styles}\n</style>`;
  const bodyHtml = clone.outerHTML;
  const htmlDoc = `<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n${headHtml}\n<style>html{height:auto}body{display:block;height:auto;min-height:100vh;overflow:auto;padding:24px;background:#f8f7f3}.preview-stage{height:auto;overflow:visible}</style>\n</head>\n<body>\n${bodyHtml}\n</body>\n</html>`;

  const platform = current?.platform_spec?.platform || current?.task?.platform || "article";
  const rawModelId = current?.model?.id || "huawei-pc";
  const safeModelId = rawModelId.replace(/[^a-zA-Z0-9_\-\u4e00-\u9fa5]/g, "_");
  const filename = `${platform}-${safeModelId}.html`;

  const blob = new Blob([htmlDoc], { type: "text/html;charset=utf-8" });
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(blobUrl);
}

function renderChips(r) {
  const chips = document.getElementById("chips");
  if (!chips) return;
  chips.textContent = "";

  const vf = (r && r.verification) || {};
  const reviewStatus = window.processReviewStatus(r,r.artifacts || {},r.trace || []);
  chips.appendChild(UI.tag(reviewStatus.label,reviewStatus.needsReview ? "warn" : "ok"));

  const vfImages = vf.images || [];
  const imgMatch = vfImages.length > 0 && vfImages.every(i => i.model_match);
  chips.appendChild(UI.tag("图片型号 " + (vfImages.length ? imgMatch ? "全部一致" : "存在不一致" : "暂无配图"), vfImages.length ? imgMatch ? "ok" : "bad" : "warn"));

  const comp = vf.compliance || [];
  chips.appendChild(UI.tag("合规 " + (comp.length ? `处理 ${comp.length} 处` : "无命中"), comp.length ? "warn" : "ok"));

  const imgs = (r && r.images) || [];
  const hasNotice = Boolean(r && r.image_notice && r.image_notice.length);
  chips.appendChild(UI.tag(`配图 ${imgs.length} 张`, hasNotice ? "warn" : "ok"));

  const ps = (r && r.platform_spec) || {};
  const pName = ps.platform_name || "";
  const psImgs = ps.images || [0, 0];
  const psChars = ps.chars || [0, 0];
  chips.appendChild(UI.tag(`${pName}建议 ${psImgs[0]}-${psImgs[1]} 图 · ${psChars[0]}-${psChars[1]} 字`));

  const judge = vf.judge || {};
  const overall = judge.overall || "-";
  const judgeOk = overall === "pass" || overall === "ok";
  const judgeLabels = { pass: "通过", ok: "通过", needs_fix: "发现问题", fail: "未通过", warn: "需关注", incomplete: "未完整覆盖", not_reviewed: "未完成", "-": "未完成" };
  chips.appendChild(UI.tag(`自动评审 ${judgeLabels[overall] || "需关注"}`, judgeOk ? "ok" : "warn"));

}

function weightRows(weights, prior, llm) {
  const frag = document.createDocumentFragment();
  const w = weights || {};
  const p = prior || {};
  const l = llm || {};
  const sorted = Object.keys(w).sort((a, b) => (Number(w[b]) || 0) - (Number(w[a]) || 0));

  for (const key of sorted) {
    const v = Number(w[key]) || 0;
    const row = document.createElement("div");
    row.className = "dimrow";

    const spanName = document.createElement("span");
    spanName.textContent = DIM[key] || key;
    row.appendChild(spanName);

    const bar = document.createElement("div");
    bar.className = "bar";
    const i = document.createElement("i");
    i.style.width = `${Math.min(100, v * 250)}%`;
    bar.appendChild(i);
    row.appendChild(bar);

    const spanVal = document.createElement("span");
    spanVal.className = "muted";
    spanVal.textContent = v.toFixed(2);
    const pVal = p[key] !== undefined ? p[key] : "-";
    const lVal = l[key] !== undefined ? l[key] : "-";
    spanVal.title = `先验 ${pVal} · 模型 ${lVal}`;
    row.appendChild(spanVal);

    frag.appendChild(row);
  }
  return frag;
}

function renderJudge(r) {
  const dbg = document.getElementById("dbg-judge");
  if (dbg) dbg.hidden = false;

  const judgeEl = document.getElementById("judge");
  if (!judgeEl) return;
  judgeEl.textContent = "";

  const sj = (r && r.scene_judgement) || {};

  const pTags = document.createElement("p");
  if (sj.audience) pTags.appendChild(UI.tag(sj.audience));
  if (sj.scenario) pTags.appendChild(UI.tag(sj.scenario));
  if (sj.stage) pTags.appendChild(UI.tag(sj.stage));
  if (sj.platform) pTags.appendChild(UI.tag(sj.platform));
  judgeEl.appendChild(pTags);

  const pProblem = document.createElement("p");
  pProblem.textContent = "用户问题：" + (sj.user_problem || "");
  judgeEl.appendChild(pProblem);

  const pGoal = document.createElement("p");
  pGoal.textContent = "内容目标：" + (sj.goal || "");
  judgeEl.appendChild(pGoal);

  const pStrat = document.createElement("p");
  pStrat.textContent = "策略解释：" + (sj.strategy_notes || "");
  judgeEl.appendChild(pStrat);

  const h3W = document.createElement("h3");
  h3W.textContent = "需求维度权重（规则先验 × 模型推理）";
  judgeEl.appendChild(h3W);
  judgeEl.appendChild(weightRows(sj.weights, sj.prior_weights, sj.llm_weights));

  const pSoft = document.createElement("p");
  pSoft.appendChild(document.createTextNode("软偏好："));
  const sps = sj.soft_preferences || [];
  if (sps.length === 0) {
    pSoft.appendChild(document.createTextNode("无"));
  } else {
    sps.forEach((sp, idx) => {
      if (idx > 0) pSoft.appendChild(document.createTextNode("；"));
      pSoft.appendChild(document.createTextNode(sp.text + " "));
      (sp.dims || []).forEach(d => {
        pSoft.appendChild(UI.tag(DIM[d] || d));
      });
    });
  }
  judgeEl.appendChild(pSoft);

  const pHard = document.createElement("p");
  pHard.appendChild(document.createTextNode("硬约束："));
  const hcs = sj.hard_constraints || [];
  if (hcs.length === 0) {
    pHard.appendChild(document.createTextNode("无"));
  } else {
    hcs.forEach(c => {
      pHard.appendChild(UI.tag(c, "warn"));
    });
  }
  judgeEl.appendChild(pHard);

  const pTrade = document.createElement("p");
  const toText = (sj.tradeoffs || []).join("；");
  pTrade.appendChild(document.createTextNode("取舍：" + (toText || "无") + " · 无依据诉求："));
  const unmap = sj.unmappable || [];
  if (unmap.length === 0) {
    pTrade.appendChild(document.createTextNode("无"));
  } else {
    unmap.forEach(u => {
      pTrade.appendChild(UI.tag(u, "bad"));
    });
  }
  judgeEl.appendChild(pTrade);

  const model = (r && r.model) || {};
  const pModel = document.createElement("p");
  pModel.appendChild(document.createTextNode("型号：" + (model.name || "") + " "));
  const isRec = model.mode === "recommended";
  pModel.appendChild(UI.tag(isRec ? "按需求推荐" : "用户指定", isRec ? "warn" : "ok"));
  judgeEl.appendChild(pModel);

  if (model.recommendation) {
    const rec = model.recommendation;
    if (rec.reasons && rec.reasons.length) {
      const ul = document.createElement("ul");
      rec.reasons.forEach(item => {
        const li = document.createElement("li");
        const dName = DIM[item.dimension] || item.dimension || "";
        li.textContent = `${dName}：${item.claim || ""}（${item.evidence_field || ""}：${item.evidence_value || ""}）`;
        ul.appendChild(li);
      });
      judgeEl.appendChild(ul);
    }
    if (rec.trade_off) {
      const pTo = document.createElement("p");
      pTo.className = "muted";
      pTo.textContent = rec.trade_off;
      judgeEl.appendChild(pTo);
    }
  }

  if (model.alternatives && model.alternatives.length) {
    const pAlt = document.createElement("p");
    pAlt.textContent = "备选：" + model.alternatives.join("、");
    judgeEl.appendChild(pAlt);
  }
}

function renderEvidence(r) {
  const dbg = document.getElementById("dbg-evidence");
  if (dbg) dbg.hidden = false;

  const facts = (r && r.evidence && r.evidence.facts) || [];
  const images = (r && r.images) || [];
  const evSum = document.getElementById("ev-sum");
  if (evSum) evSum.textContent = `${facts.length} 个事实点 · ${images.length} 张图`;

  const container = document.getElementById("evidence") || dbg;
  container.textContent = "";

  const fTable = document.createElement("table");
  const fThead = document.createElement("thead");
  const fTrH = document.createElement("tr");
  ["#", "事实点", "来源", "已用"].forEach(h => {
    const th = document.createElement("th");
    th.textContent = h;
    fTrH.appendChild(th);
  });
  fThead.appendChild(fTrH);
  fTable.appendChild(fThead);

  const fTbody = document.createElement("tbody");
  facts.forEach(f => {
    const tr = document.createElement("tr");

    const tdId = document.createElement("td");
    tdId.textContent = f.id || "";
    tr.appendChild(tdId);

    const tdText = document.createElement("td");
    tdText.textContent = f.text || "";
    if (f.why) tdText.title = f.why;
    tr.appendChild(tdText);

    const tdSrc = document.createElement("td");
    const src = f.source || {};
    tdSrc.textContent = [src.title, src.label].filter(Boolean).join(" · ");
    tr.appendChild(tdSrc);

    const tdUsed = document.createElement("td");
    tdUsed.textContent = f.used ? "是" : "否";
    tr.appendChild(tdUsed);

    fTbody.appendChild(tr);
  });
  fTable.appendChild(fTbody);
  container.appendChild(fTable);

  const iTable = document.createElement("table");
  const iThead = document.createElement("thead");
  const iTrH = document.createElement("tr");
  ["编号", "文件名", "画面类型", "含整机", "来源页面", "插入位置", "图注"].forEach(h => {
    const th = document.createElement("th");
    th.textContent = h;
    iTrH.appendChild(th);
  });
  iThead.appendChild(iTrH);
  iTable.appendChild(iThead);

  const iTbody = document.createElement("tbody");
  images.forEach(i => {
    const tr = document.createElement("tr");

    const tdId = document.createElement("td");
    tdId.textContent = i.id || "";
    tr.appendChild(tdId);

    const tdName = document.createElement("td");
    tdName.textContent = i.name || "";
    tr.appendChild(tdName);

    const tdKind = document.createElement("td");
    tdKind.textContent = (UI.KIND_ZH && UI.KIND_ZH[i.kind]) || "未标注";
    tr.appendChild(tdKind);

    const tdDev = document.createElement("td");
    tdDev.textContent = (i.shows_device === null || i.shows_device === undefined) ? "?" : (i.shows_device ? "是" : "否");
    tr.appendChild(tdDev);

    const tdSrc = document.createElement("td");
    if (/^https:\/\//i.test(i.source_url || "")) {
      const link = document.createElement("a");
      link.href = i.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = i.source_title || "查看官方来源";
      tdSrc.appendChild(link);
    } else {
      tdSrc.textContent = i.source_title || i.source_url || "";
    }
    if (i.checked_at) tdSrc.appendChild(document.createTextNode(`（核验 ${i.checked_at.slice(0, 10)}）`));
    tr.appendChild(tdSrc);

    const tdPos = document.createElement("td");
    tdPos.textContent = i.position || "";
    tr.appendChild(tdPos);

    const tdCap = document.createElement("td");
    tdCap.textContent = i.caption || "";
    tr.appendChild(tdCap);

    iTbody.appendChild(tr);
  });
  iTable.appendChild(iTbody);
  container.appendChild(iTable);

  const sources = (r && r.evidence && r.evidence.sources) || [];
  if (sources.length > 0) {
    const h3Src = document.createElement("h3");
    h3Src.textContent = "官方来源页面";
    container.appendChild(h3Src);

    const ulSrc = document.createElement("ul");
    sources.forEach(x => {
      const li = document.createElement("li");
      li.textContent = `${x.type || ""}：${x.title || ""} ${x.url || ""}（抓取 ${x.fetched || ""}）`;
      ulSrc.appendChild(li);
    });
    container.appendChild(ulSrc);
  }
}

function renderVerify(r) {
  const dbg = document.getElementById("dbg-verify");
  if (dbg) dbg.hidden = false;

  const vf = (r && r.verification) || {};
  const review = window.processReviewStatus(r,r.artifacts || {},r.trace || []);
  const remaining = (vf.remaining || []).filter(s=>review.state !== "incomplete" || typeof s !== "string" || !/独立评审未通过或未完成|预算/.test(s));
  const vfSum = document.getElementById("vf-sum");
  if (vfSum) {
    vfSum.textContent = review.label;
    vfSum.title = review.detail;
  }

  const container = document.getElementById("verify") || dbg;
  container.textContent = "";
  if (review.needsReview || r.human_review) container.appendChild(UI.el("div", {class:"review-feedback-entry"},
    UI.el("div", {}, UI.el("b", {}, "终审需要你的判断"), UI.el("p", {}, "逐项查看原因，选择修改、复审或人工裁定。")),
    UI.el("button", {type:"button", class:"btn-secondary", onclick:() => window.ReviewQuestions.open(r)}, "问题详情 ↗")));
  if (review.state === "incomplete") container.appendChild(UI.el("p", {}, review.detail));

  if (remaining.length > 0) {
    const pRem = document.createElement("p");
    pRem.textContent = "自动流程尚未解决的事项：";
    container.appendChild(pRem);

    const ulRem = document.createElement("ul");
    remaining.forEach(item => {
      const li = document.createElement("li");
      li.textContent = typeof item === "string" ? item : (item.detail || JSON.stringify(item));
      ulRem.appendChild(li);
    });
    container.appendChild(ulRem);
  }

  const rounds = vf.repair_rounds || [];
  if (rounds.length > 0) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = "核验—修订过程";
    det.appendChild(sum);

    rounds.forEach((rd, idx) => {
      const b = document.createElement("b");
      b.textContent = `第 ${rd.round !== undefined ? rd.round : idx + 1} 轮`;
      det.appendChild(b);

      const ul = document.createElement("ul");
      const issues = rd.issues || [];
      if (issues.length === 0) {
        const li = document.createElement("li");
        li.textContent = "通过";
        ul.appendChild(li);
      } else {
        issues.forEach(iss => {
          const li = document.createElement("li");
          li.textContent = typeof iss === "string" ? iss : (iss.detail || JSON.stringify(iss));
          ul.appendChild(li);
        });
      }
      det.appendChild(ul);
    });
    container.appendChild(det);
  }

  const judge = vf.judge || {};
  const problems = judge.problems || [];
  if (problems.length > 0) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = "实际终稿的评审意见";
    det.appendChild(sum);

    const ul = document.createElement("ul");
    problems.forEach(prob => {
      const li = document.createElement("li");
      const where = prob.where || "";
      const detail = prob.detail || "";
      li.textContent = `${where}：${detail}`;
      ul.appendChild(li);
    });
    det.appendChild(ul);
    container.appendChild(det);
  }

  const compliance = vf.compliance || [];
  if (compliance.length > 0) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = "合规处理记录";
    det.appendChild(sum);

    const ul = document.createElement("ul");
    compliance.forEach(c => {
      const li = document.createElement("li");
      const rule = c.rule || "";
      const hit = c.hit || "";
      const action = c.action || "";
      li.textContent = `${rule}：${hit} → ${action}`;
      ul.appendChild(li);
    });
    det.appendChild(ul);
    container.appendChild(det);
  }

  const platform = vf.platform || [];
  if (Array.isArray(platform) ? platform.length > 0 : Boolean(platform)) {
    const pPlat = document.createElement("p");
    pPlat.className = "muted";
    pPlat.textContent = "平台规格提示：" + (Array.isArray(platform) ? platform.join("；") : platform);
    container.appendChild(pPlat);
  }

  const pendingConfirm = (r && r.pending_confirm) || vf.pending_confirm || [];
  if (pendingConfirm.length > 0) {
    const h3Pending = document.createElement("h3");
    h3Pending.textContent = "待确认信息";
    container.appendChild(h3Pending);

    const ulPending = document.createElement("ul");
    pendingConfirm.forEach(item => {
      const li = document.createElement("li");
      li.textContent = typeof item === "string" ? item : (item.detail || JSON.stringify(item));
      ulPending.appendChild(li);
    });
    container.appendChild(ulPending);
  }
}

init();
