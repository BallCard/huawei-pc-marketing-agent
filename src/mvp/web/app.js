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

/* 门店状态带：把「门店经营意识」接到创作简报上。
   角色、门店目标、私域触点全部沿用现有 store_id / goal / extra 契约，不改后端。 */
const STORE_GOALS = ["引导到店", "预约体验", "私信咨询", "消化库存"];
const STORE_TOUCHPOINTS = ["企业微信私信", "朋友圈", "门店社群", "到店邀约"];
const STORE_ROLE_LABELS = { manager: "门店店长", sales: "销售顾问" };
const storeDesk = {
  role: "manager",
  goals: [],
  touchpoints: [],
  readSession() {
    try {
      const r = sessionStorage.getItem("studio-role");
      if (r === "manager" || r === "sales") this.role = r;
      this.goals = JSON.parse(sessionStorage.getItem("studio-goals") || "[]");
      this.touchpoints = JSON.parse(sessionStorage.getItem("studio-touchpoints") || "[]");
      if (!Array.isArray(this.goals)) this.goals = [];
      if (!Array.isArray(this.touchpoints)) this.touchpoints = [];
      this.goals = this.goals.filter(g => STORE_GOALS.includes(g));
      this.touchpoints = this.touchpoints.filter(t => STORE_TOUCHPOINTS.includes(t));
    } catch (e) { /* 浏览器禁存储时保持默认 */ }
  },
  writeSession() {
    try {
      sessionStorage.setItem("studio-role", this.role);
      sessionStorage.setItem("studio-goals", JSON.stringify(this.goals));
      sessionStorage.setItem("studio-touchpoints", JSON.stringify(this.touchpoints));
    } catch (e) { /* 忽略 */ }
  },
  syncChips() {
    document.querySelectorAll("[data-role]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.role === this.role)));
    document.querySelectorAll("[data-goal]").forEach(b => b.setAttribute("aria-pressed", String(this.goals.includes(b.dataset.goal))));
    document.querySelectorAll("[data-touchpoint]").forEach(b => b.setAttribute("aria-pressed", String(this.touchpoints.includes(b.dataset.touchpoint))));
  },
  syncGoalInput() {
    const input = UI.$("goal");
    if (!input) return;
    const composed = this.goals.join("、");
    if (composed) {
      input.value = composed;
    } else if (!input.value || STORE_GOALS.some(g => input.value.includes(g))) {
      input.value = "";
    }
  },
  syncFromGoalInput() {
    const value = UI.$("goal")?.value || "";
    this.goals = STORE_GOALS.filter(g => value.includes(g));
    this.writeSession();
    this.syncChips();
  },
  init() {
    this.readSession();
    this.syncChips();
    document.querySelectorAll("[data-role]").forEach(button => button.addEventListener("click", () => {
      this.role = button.dataset.role === "sales" ? "sales" : "manager";
      this.writeSession();
      this.syncChips();
      window.dispatchEvent(new CustomEvent("store-role-change", { detail: this.role }));
    }));
    document.querySelectorAll("[data-goal]").forEach(button => button.addEventListener("click", () => {
      const label = button.dataset.goal;
      const i = this.goals.indexOf(label);
      if (i >= 0) this.goals.splice(i, 1); else this.goals.push(label);
      this.writeSession();
      this.syncChips();
      this.syncGoalInput();
    }));
    document.querySelectorAll("[data-touchpoint]").forEach(button => button.addEventListener("click", () => {
      const label = button.dataset.touchpoint;
      const i = this.touchpoints.indexOf(label);
      if (i >= 0) this.touchpoints.splice(i, 1); else this.touchpoints.push(label);
      this.writeSession();
      this.syncChips();
    }));
    const dialog = UI.$("options-dialog");
    if (dialog) dialog.addEventListener("close", () => this.syncFromGoalInput());
    window.addEventListener("store-context-updated", () => refreshStoreBoard().catch(() => {}));
  }
};

/* 门店私域链路：讲清思路，并把焦点直接落到第四步（触点） */
function initStoreLoop() {
  const dialog = UI.$("store-loop-dialog");
  const open = UI.$("open-store-loop");
  if (!dialog || !open) return;
  open.addEventListener("click", () => dialog.showModal());
  UI.$("start-store-loop")?.addEventListener("click", () => {
    dialog.close();
    document.querySelector(".touchpoint-field")?.scrollIntoView({ block: "center", behavior: "smooth" });
    document.querySelector("[data-touchpoint]")?.focus({ preventScroll: true });
  });
}

/* 平台标注：与第一页「发到哪里」使用同一套图标与名称，避免两套叫法。 */
const PLATFORM_META = {
  xiaohongshu: { label: "小红书", icon: "i-book" },
  wechat_article: { label: "公众号", icon: "i-file" },
  moments: { label: "朋友圈", icon: "i-grid" },
  poster: { label: "门店海报", icon: "i-poster" }
};

const REVIEW_LABELS = {
  passed: { text: "已通过核验", ok: true },
  needs_review: { text: "待复核", ok: false },
  pending: { text: "待核验", ok: false },
  unknown: { text: "未标记", ok: false }
};

function platformTag(platform) {
  const meta = PLATFORM_META[platform] || { label: platform || "图文", icon: "i-file" };
  return UI.el("span", { class: "plat-tag" }, UI.svg(meta.icon), UI.el("span", {}, meta.label));
}

function refreshStoreBoard() {
  const box = UI.$("store-history");
  if (!box) return Promise.resolve();
  const sid = (window.CreativeContext && window.CreativeContext.storeId) ? window.CreativeContext.storeId() : "default";
  return fetch(`/api/context/${encodeURIComponent(sid)}`)
    .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
    .then(data => {
      const rows = data.history || [];
      const count = UI.$("store-history-count");
      if (count) count.textContent = rows.length ? `${rows.length} 篇` : "暂无稿件";
      if (!rows.length) {
        box.replaceChildren(UI.el("p", { class: "store-empty" }, "这家门店还没有稿件记录，生成第一篇后会自动出现在这里。"));
        return;
      }
      box.replaceChildren(...rows.map(row => {
        const state = REVIEW_LABELS[row.review_state] || { text: row.review_state || "未标记", ok: false };
        return UI.el("article", { class: "history-row" },
          UI.el("p", { class: "history-title" }, row.title || "未命名稿件"),
          UI.el("div", { class: "history-meta" },
            platformTag(row.platform),
            UI.el("span", { class: "history-state" + (state.ok ? " ok" : "") }, state.text)));
      }));
    })
    .catch(err => {
      box.replaceChildren(UI.el("p", { class: "store-empty" }, `读取失败：${err.message}。请确认本地服务已启动。`));
    });
}

/* 看板交互：动态筛选、角色切换后的视角与数字联动。 */
function initStoreBoard() {
  const list = document.querySelector(".feed-list");
  if (!list) return;
  const items = Array.from(list.querySelectorAll("li"));
  const filters = Array.from(document.querySelectorAll("[data-feed-filter]"));
  const kindNames = { new: "新客加微", group: "社群接龙", visit: "到店 / 预约", ask: "待确认", stock: "库存", old: "老客换新" };
  let filter = "all";

  const inScope = () => items.filter(li => storeDesk.role === "manager" || li.dataset.owner !== "manager");

  function sync() {
    const scoped = inScope();
    const shown = scoped.filter(li => filter === "all" || li.dataset.kind === filter);
    items.forEach(li => { li.hidden = !shown.includes(li); });
    filters.forEach(button => {
      const key = button.dataset.feedFilter;
      const count = key === "all" ? scoped.length : scoped.filter(li => li.dataset.kind === key).length;
      button.querySelector("b").textContent = String(count);
      button.hidden = key !== "all" && count === 0;
      button.setAttribute("aria-pressed", String(key === filter));
    });
    const status = UI.$("feed-status");
    if (status) {
      status.textContent = filter === "all"
        ? `${storeDesk.role === "manager" ? "全店" : "本人"}视角 · 共 ${scoped.length} 条动态`
        : `${kindNames[filter]} · ${shown.length} 条`;
    }
    const scope = UI.$("store-scope");
    if (scope) {
      scope.textContent = storeDesk.role === "manager"
        ? "全店视角 · 含社群、库存与全部跟进"
        : "我的顾客视角 · 只看本人跟进的顾客";
    }
    document.querySelectorAll(".store-kpi b[data-mgr]").forEach(node => {
      node.textContent = storeDesk.role === "manager" ? node.dataset.mgr : node.dataset.sales;
    });
  }

  filters.forEach(button => button.addEventListener("click", () => { filter = button.dataset.feedFilter; sync(); }));
  window.addEventListener("store-role-change", sync);
  sync();
}


const PRESETS = [
  {
    title: "新生买电脑 · 小红书",
    sub: "鸿蒙版 · 模仿惠普 C01 · 颜色征集",
    v: {
      prompt_variant: "differentiated",
      marketing_template: "C01",
      product: "HUAWEI MateBook 14（鸿蒙版）",
      audience: "大学新生",
      scenario: "开学季",
      platform: "xiaohongshu",
      goal: "种草并引导到店咨询",
      constraints: "",
      extra: "参考惠普 C01 的“细节→征集→真实回复”结构：先展示华为真实配色或外观细节，再问一个新生能直接回答的问题。只交付首帖，不编网友评论、获选名称、奖励或官方采纳。"
    }
  },
  {
    title: "同一款 · 换公众号",
    sub: "职场办公 · 模仿微软 C14 · 主题延展",
    v: {
      prompt_variant: "differentiated",
      marketing_template: "C14",
      product: "HUAWEI MateBook 14（鸿蒙版）",
      audience: "经常出差的职场人",
      scenario: "职场办公",
      platform: "wechat_article",
      goal: "引导预约体验",
      constraints: "",
      extra: "参考微软 C14 的“同一主题→按渠道拆内容→一个入口”结构，把同一条华为产品主张改成公众号阅读，不新增活动、折扣或渠道承诺。要接投影仪、外设的具体兼容性仍需真实资料支持。"
    }
  },
  {
    title: "内容创作 · 小红书",
    sub: "屏幕与手写 · 模仿华硕 C04 · 试验角色",
    v: {
      prompt_variant: "differentiated",
      marketing_template: "C04",
      demo_mode: true,
      product: "HUAWEI MateBook Pro S",
      audience: "摄影与设计创作者",
      scenario: "内容创作",
      platform: "xiaohongshu",
      goal: "收藏清单并到店体验",
      constraints: "",
      extra: "参考华硕 C04 的“一致人设+固定栏目”结构，使用原创试验角色讲一个创作任务。角色与华为品牌方暂无联系，不能复制天选姬或声称官方合作；产品能力仍只写真实资料。"
    }
  },
  {
    title: "门店到访 · 海报",
    sub: "竖版海报 · 模仿联想 C16 · 体验邀请演示",
    v: {
      prompt_variant: "differentiated",
      marketing_template: "C16",
      demo_mode: true,
      product: "HUAWEI MateBook Pro",
      audience: "附近看机的职场新人",
      scenario: "门店到访",
      platform: "poster",
      goal: "引导到店",
      constraints: "",
      extra: "参考联想 C16 的“体验项目→适合任务→时间地点→参与动作”结构。这里是概念演示，使用虚构体验点和安排，海报必须醒目标注非真实门店活动；真实地址、服务、库存和活动只能来自门店确认资料。"
    }
  },
  {
    title: "家庭换新 · 朋友圈",
    sub: "短文 + 九宫格 · 模仿戴尔 C13 · 选购问答",
    v: {
      prompt_variant: "differentiated",
      marketing_template: "C13",
      product: "HUAWEI MateBook D 14 2024",
      audience: "准备给孩子换电脑的家长",
      scenario: "家庭换新",
      platform: "moments",
      goal: "私信咨询",
      constraints: "",
      extra: "参考戴尔 C13 的“真实问题→约束→有据判断→下一步”结构，只回答一个家庭换新问题。家里多人共用、资料迁移的事实需有产品或门店资料支持，不做伪横评。"
    }
  },
  {
    title: "缺整机图 · D 16",
    sub: "验证缺图提示 · 不套案例",
    v: {
      prompt_variant: "baseline",
      marketing_template: "auto",
      demo_mode: false,
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
    sub: "按画像推荐 · 可手动改选 C13",
    v: {
      prompt_variant: "baseline",
      marketing_template: "auto",
      demo_mode: false,
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
    sub: "测合规闸门 · 不套案例",
    v: {
      prompt_variant: "baseline",
      marketing_template: "auto",
      demo_mode: false,
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
  window.CreativeContext?.init();
  storeDesk.init();
  initStoreLoop();
  initStoreBoard();
  refreshStoreBoard().catch(() => {});
  window.PromptCompare?.init(readTask);
  window.MarketingTemplates?.init();
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
  if (v.prompt_variant && UI.$("prompt-variant")) UI.$("prompt-variant").value = v.prompt_variant;
  window.MarketingTemplates?.restore(v);
  storeDesk.syncFromGoalInput();
  storeDesk.syncChips();
}

function readTask() {
  const rawConstraints = UI.$("#constraints")?.value || "";
  const constraints = rawConstraints
    .split(/[,，;；]/)
    .map(s => s.trim())
    .filter(Boolean);

  const baseExtra = UI.$("#extra")?.value.trim() || "";
  const extras = [];
  if (baseExtra) extras.push(baseExtra);
  extras.push(`创作人：华为门店${STORE_ROLE_LABELS[storeDesk.role] || "门店店长"}，站在门店经营与顾客转化的角度组织内容。`);
  const touchpoints = storeDesk.touchpoints.join("、");
  if (touchpoints) extras.push(`私域触达：${touchpoints}。内容按这些触点来写，便于直接分发。`);

  const task = {
    ...(window.MarketingTemplates?.read() || {}),
    prompt_variant: UI.$("prompt-variant")?.value || "baseline",
    store_id: window.CreativeContext?.storeId() || "default",
    product: UI.$("#product")?.value.trim() || "",
    audience: UI.$("#audience")?.value.trim() || "",
    scenario: UI.$("#scenario")?.value.trim() || "",
    platform: UI.$("#platform")?.value || "xiaohongshu",
    speed: UI.$("#speed")?.value || "quality",
    goal: UI.$("#goal")?.value.trim() || "",
    touchpoints: storeDesk.touchpoints.slice(),
    constraints,
    extra: extras.join("\n\n")
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
        if (restorePage && !["need_info", "input_required", "budget_exceeded"].includes(j.result?.status)) Studio.navigate(restorePage, false);
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
  if (r.mode === "prompt_comparison") {
    Studio.stopRun();
    sessionStorage.removeItem("studio-active-job");
    window.PromptCompare?.show(r);
    return;
  }
  window.CreativeContext?.showResult(r);
  const posterDownload = UI.$("poster-download"), posterRedo = UI.$("poster-regenerate");
  posterDownload.hidden = !r.poster?.image_url;
  UI.$("dl").disabled = Boolean(r.poster && !r.poster.image_url);
  if (r.poster?.image_url) {
    posterDownload.href = r.poster.image_url + "?download=1";
    posterDownload.textContent = r.poster.status === "passed" ? "下载 PNG" : "下载待复核 PNG";
  }
  posterRedo.hidden = !r.poster || r.poster.status === "blocked";
  posterRedo.textContent = r.poster?.resume_available || r.poster?.status === "error" && r.poster?.task_id && /超时/.test(r.poster?.error || "") ? "继续等待本次生图 ↗" : "重新生图 ↗";

  if (r.status === "need_info" || r.status === "input_required" || r.status === "budget_exceeded") {
    const stage = UI.$("#stage");
    if (stage) stage.hidden = true;
    showNeedInfo(r);
    Studio.stopRun();
    UI.$("process-title").textContent = r.status === "budget_exceeded" ? "本次创作已到时间预算。" : r.status === "input_required" ? "暂时无法安全确定型号。" : "再确认一点，就能继续。";
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
    if (r.poster?.fallback_used) {
      notice.appendChild(UI.el("div", { class: "warnbar", role: "alert" }, [
        UI.el("b", {}, ["海报回退："]),
        document.createTextNode(r.poster.fallback_warning || r.poster.fallback_note || "现场生图未完成，当前展示预制样例。")
      ]));
    }
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
  window.MarketingTemplates?.showResult(r);
  renderEvidence(r);
  renderVerify(r);

  const revise = UI.$("#revise");
  if (revise) revise.hidden = false;

  ["#dbg-judge", "#dbg-evidence", "#dbg-verify"].forEach(sel => {
    const el = UI.$(sel);
    if (el) el.hidden = false;
  });
  Studio.finishRun(r);
  refreshStoreBoard().catch(() => {});
}

function showNeedInfo(r) {
  const stage = UI.$("#stage");
  if (stage) stage.hidden = true;

  const need = UI.$("#need");
  if (need) need.replaceChildren();

  const info = r.need_info || r.scene_judgement?.need_info || {};
  const specs = r.question_specs || r.questions || info.questions || [];
  const questions = specs.map(q => String(typeof q === "object" && q ? q.question || "" : q || "").trim()).filter(Boolean);
  const candidates = info.candidates || r.candidates || [];
  const round = Math.max(0, Number(r.task?.clarify_round || 0) || 0);
  const exhausted = round >= 2 || r.status === "input_required";

  // 一次一个问题的悬浮追问；主页面不新增内容，Bot 仍然一屏显示。
  if (r.status === "need_info" && questions.length > 0 && !exhausted && window.AgentAsk) {
    window.AgentAsk.open({
      jobId: activeJobId || "",
      questions: specs,
      round: r.clarification?.round || round + 1,
      candidates,
      task: r.task || readTask(),
      onComplete: (answers, task) => submit("", task),
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
    UI.el("h3", {}, [r.status === "budget_exceeded" ? "本次未在时间预算内完成" : exhausted ? "暂时无法确定合适型号" : "需要补充信息"])
  ]);

  if (exhausted) {
    card.appendChild(UI.el("p", {}, [r.message || "已完成两轮需求确认。现有信息不足以安全选型，请在创作简报中明确型号或调整必须条件。"]));
  }

  if (questions.length > 0) {
    const ul = UI.el("ul", { class: "need-questions" });
    questions.forEach(q => {
      ul.appendChild(UI.el("li", {}, [q]));
    });
    card.appendChild(ul);
  }

  if (!exhausted && Array.isArray(candidates) && candidates.length > 0) {
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
  const parts = [...(art.disclosures || [])];

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

function insHead(title, note) {
  const head = document.createElement("div");
  head.className = "ins-head";
  const h = document.createElement("h3");
  h.textContent = title;
  head.appendChild(h);
  if (note) {
    const span = document.createElement("span");
    span.textContent = note;
    head.appendChild(span);
  }
  return head;
}

function clip(text, max) {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  return s.length > max ? s.slice(0, max) + "…" : s;
}

const SPEC_RE = /([\u4e00-\u9fa5]{2,6}|[A-Za-z]{2,12})\s*(约)?\s*(\d+(?:\.\d+)?(?:\s*[×x]\s*\d+(?:\.\d+)?)?)\s*(mm|cm|kg|g|英寸|寸|Wh|mAh|GB|TB|Hz|W|%|nit)?/g;

// 备注跟随所属数值：只把紧跟在数值后的括号归给这一项，避免每张卡重复同一段话。
function parseSpec(text) {
  const src = String(text || "");
  const hits = [];
  SPEC_RE.lastIndex = 0;
  let m;
  while ((m = SPEC_RE.exec(src))) {
    hits.push({ label: m[1], value: `${m[2] || ""}${m[3]}${m[4] || ""}`, at: m.index, end: SPEC_RE.lastIndex });
  }
  const specs = hits.map((hit, i) => {
    const after = src.slice(hit.end, i + 1 < hits.length ? hits[i + 1].at : src.length);
    const note = (after.match(/^[（(]([^）)]{1,40})[）)]/) || [])[1] || "";
    return { label: hit.label, value: hit.value, note };
  });
  const tail = (src.slice(hits.length ? hits[hits.length - 1].end : 0).match(/[*＊][^*＊]{0,90}/) || [""])[0];
  return { specs, tail: tail.replace(/^[*＊]\s*/, "") };
}

// 只挑最有辨识度的几项展示：厚度/重量优先，其余收进折叠区
const SPEC_RANK = ["厚度", "重量", "长度", "宽度", "屏幕", "分辨率", "刷新率", "电池", "续航", "处理器", "内存", "硬盘", "存储", "接口"];

function pickSpecs(specs, limit) {
  const seen = new Set();
  const uniq = specs.filter(s => {
    const key = `${s.label}|${s.value}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const rank = s => {
    const i = SPEC_RANK.findIndex(k => String(s.label).includes(k));
    return i < 0 ? SPEC_RANK.length : i;
  };
  const sorted = uniq.slice().sort((a, b) => rank(a) - rank(b));
  const chosen = sorted.slice(0, limit);
  const rest = sorted.slice(limit);
  return { chosen, rest };
}

function specCard(label, value, note, opts = {}) {
  const card = document.createElement("div");
  card.className = opts.wide ? "spec-card wide" : "spec-card";
  const k = document.createElement("div");
  k.className = "spec-k";
  const dot = document.createElement("i");
  if (opts.used === false) dot.className = "idle";
  k.append(dot, document.createTextNode(label));
  card.appendChild(k);
  const v = document.createElement("div");
  v.className = opts.text ? "spec-v text" : (String(value).length > 16 ? "spec-v long" : "spec-v");
  v.textContent = value;
  card.appendChild(v);
  if (note) {
    const n = document.createElement("div");
    n.className = "spec-note";
    n.textContent = note;
    card.appendChild(n);
  }
  return card;
}

function renderEvidence(r) {
  const dbg = document.getElementById("dbg-evidence");
  if (dbg) dbg.hidden = false;
  const container = document.getElementById("evidence") || dbg;
  if (!container) return;
  container.textContent = "";

  const facts = (r && r.evidence && r.evidence.facts) || [];
  const images = (r && r.images) || [];
  const sources = (r && r.evidence && r.evidence.sources) || [];
  const model = (r && r.model) || {};
  const evSum = document.getElementById("ev-sum");
  if (evSum) evSum.textContent = `${facts.length} 个事实点 · ${images.length} 张图`;

  // 事实点：只留关键数据，其余收进折叠区，避免一屏塞满参数
  const factSection = document.createElement("section");
  factSection.className = "ins-section";
  factSection.appendChild(insHead("产品事实", facts.length ? `${facts.filter(f => f.used).length} 条进入正文` : "本次没有引用事实"));
  const grid = document.createElement("div");
  grid.className = "spec-grid";
  if (model.name) {
    grid.appendChild(specCard("型号", model.name, model.mode === "recommended" ? "按需求推荐" : "用户指定", { wide: true }));
  }
  const specPool = [];
  const plainFacts = [];
  let tailText = "";
  let sourceText = "";
  facts.forEach(f => {
    const parsed = parseSpec(f.text);
    const src = f.source || {};
    sourceText = sourceText || [src.title, src.label].filter(Boolean).join(" · ");
    tailText = tailText || parsed.tail;
    if (parsed.specs.length >= 2) specPool.push(...parsed.specs);
    else plainFacts.push(f);
  });
  const picked = pickSpecs(specPool, 3);
  picked.chosen.forEach(spec => grid.appendChild(specCard(spec.label, spec.value, spec.note, { used: true })));
  plainFacts.slice(0, 1).forEach(f => {
    grid.appendChild(specCard(f.label || "要点", clip(f.text, 60), "", { text: true, wide: true, used: f.used !== false }));
  });
  const rest = picked.rest;
  if (rest.length || plainFacts.length > 1) {
    const more = document.createElement("details");
    more.className = "spec-more";
    const sum = document.createElement("summary");
    sum.textContent = `其余 ${rest.length + Math.max(0, plainFacts.length - 1)} 项参数`;
    more.appendChild(sum);
    rest.forEach(spec => more.appendChild(specCard(spec.label, spec.value, spec.note, { used: true })));
    plainFacts.slice(1).forEach(f => more.appendChild(specCard(f.label || "要点", clip(f.text, 60), "", { text: true, used: f.used !== false })));
    grid.appendChild(more);
  }
  if (sourceText || tailText) {
    const foot = document.createElement("p");
    foot.className = "spec-foot";
    foot.textContent = [tailText, sourceText].filter(Boolean).join(" · ");
    grid.appendChild(foot);
  }
  factSection.appendChild(grid);
  container.appendChild(factSection);

  // 配图：直接展示
  if (images.length) {
    const shotSection = document.createElement("section");
    shotSection.className = "ins-section";
    shotSection.appendChild(insHead("配图", "来自知识库登记图片"));
    const shots = document.createElement("div");
    shots.className = "shot-grid";
    images.forEach(im => {
      const fig = document.createElement("figure");
      fig.className = "shot";
      if (window.PV && window.PV.imgUrl) {
        const img = document.createElement("img");
        img.src = window.PV.imgUrl(r, im);
        img.alt = im.caption || im.name || "产品图";
        img.loading = "lazy";
        fig.appendChild(img);
      }
      const cap = document.createElement("figcaption");
      const capText = document.createElement("span");
      capText.className = "shot-cap";
      capText.textContent = im.caption || im.name || "";
      cap.appendChild(capText);
      const meta = document.createElement("div");
      meta.className = "shot-meta";
      if (im.position) {
        const pos = document.createElement("span");
        pos.textContent = im.position;
        meta.appendChild(pos);
      }
      if (window.UI && UI.KIND_ZH && im.kind) {
        const kind = document.createElement("span");
        kind.textContent = UI.KIND_ZH[im.kind];
        meta.appendChild(kind);
      }
      const url = im.source_url || im.origin_url || "";
      if (/^https:\/\//i.test(url)) {
        const a = document.createElement("a");
        a.href = url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = "官方页面 ↗";
        meta.appendChild(a);
      }
      cap.appendChild(meta);
      fig.appendChild(cap);
      shots.appendChild(fig);
    });
    shotSection.appendChild(shots);

    // 知识库文件路径默认折叠：属于佐证细节，不必占版面
    const tree = document.createElement("details");
    tree.className = "kb-fold";
    const sum = document.createElement("summary");
    sum.textContent = `${images.length} 个知识库文件路径`;
    tree.appendChild(sum);
    const treeBody = document.createElement("div");
    treeBody.className = "kb-tree";
    images.forEach(im => {
      const parts = String(im.local_path || "").split(/[\\/]/).filter(Boolean);
      const at = parts.lastIndexOf("kb");
      const rel = at >= 0 ? parts.slice(at + 1) : parts.slice(-4);
      const row = document.createElement("div");
      row.className = "kb-path";
      const root = document.createElement("b");
      root.textContent = "知识库";
      row.appendChild(root);
      rel.forEach((part, i) => {
        row.appendChild(document.createTextNode(" / "));
        if (i === rel.length - 1) {
          const file = document.createElement("span");
          file.className = "kb-file";
          file.textContent = part;
          row.appendChild(file);
        } else {
          row.appendChild(document.createTextNode(part));
        }
      });
      treeBody.appendChild(row);
    });
    tree.appendChild(treeBody);
    shotSection.appendChild(tree);
    container.appendChild(shotSection);
  }

  // 官方来源：可直接跳转
  if (sources.length) {
    const srcSection = document.createElement("section");
    srcSection.className = "ins-section";
    srcSection.appendChild(insHead("官方来源", "产品页与规格页"));
    const list = document.createElement("ul");
    list.className = "src-list";
    sources.forEach(x => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = x.url || "#";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      if (x.type) {
        const em = document.createElement("em");
        em.textContent = x.type;
        a.appendChild(em);
      }
      const b = document.createElement("b");
      b.textContent = x.title || x.url || "";
      a.appendChild(b);
      const arrow = document.createElement("i");
      arrow.textContent = "↗";
      a.appendChild(arrow);
      if (x.fetched) a.title = `抓取 ${x.fetched}`;
      li.appendChild(a);
      list.appendChild(li);
    });
    srcSection.appendChild(list);
    container.appendChild(srcSection);
  }
}

function renderJudge(r) {
  const dbg = document.getElementById("dbg-judge");
  if (dbg) dbg.hidden = false;
  const judgeEl = document.getElementById("judge");
  if (!judgeEl) return;
  judgeEl.textContent = "";

  const sj = (r && r.scene_judgement) || {};
  const model = (r && r.model) || {};
  const hero = ((r && r.images) || [])[0];

  // 图优先：先给产品，再给结论
  const heroBox = document.createElement("div");
  heroBox.className = "judge-hero";
  if (hero && window.PV && window.PV.imgUrl) {
    const fig = document.createElement("figure");
    const img = document.createElement("img");
    img.src = window.PV.imgUrl(r, hero);
    img.alt = hero.caption || hero.name || "产品图";
    img.loading = "lazy";
    fig.appendChild(img);
    if (hero.caption) {
      const cap = document.createElement("figcaption");
      cap.textContent = hero.caption;
      fig.appendChild(cap);
    }
    heroBox.appendChild(fig);
  }
  const side = document.createElement("div");
  const name = document.createElement("p");
  name.className = "judge-model";
  name.textContent = model.name || "未指定型号";
  side.appendChild(name);
  const chips = document.createElement("div");
  chips.className = "judge-chips";
  [sj.audience, sj.scenario, sj.stage, sj.platform].filter(Boolean).slice(0, 4).forEach(v => chips.appendChild(UI.tag(v)));
  side.appendChild(chips);
  if (sj.strategy_notes) {
    const lead = document.createElement("p");
    lead.className = "judge-lead";
    lead.textContent = clip(sj.strategy_notes, 110);
    side.appendChild(lead);
  }
  heroBox.appendChild(side);
  judgeEl.appendChild(heroBox);

  // 权重构成：一条比例条，不再堆文字
  const mix = sj.weight_mix || { structured: 0.4, unstructured: 0.6 };
  const structuredPct = Math.round((Number(mix.structured) || 0.4) * 100);
  const unstructuredPct = 100 - structuredPct;
  const mixSection = document.createElement("section");
  mixSection.className = "ins-section";
  mixSection.appendChild(insHead("权重构成", "结构化规则 × 非结构化理解"));
  const bar = document.createElement("div");
  bar.className = "mix-bar";
  const left = document.createElement("div");
  left.className = "structured";
  left.style.width = `${structuredPct}%`;
  left.textContent = `结构化 ${structuredPct}%`;
  const right = document.createElement("div");
  right.className = "unstructured";
  right.style.width = `${unstructuredPct}%`;
  right.textContent = `非结构化 ${unstructuredPct}%`;
  bar.append(left, right);
  mixSection.appendChild(bar);
  const legend = document.createElement("p");
  legend.className = "mix-legend";
  const l1 = document.createElement("span");
  l1.className = "structured";
  l1.textContent = sj.matched_scenario_rule ? `场景规则先验 · 命中「${sj.matched_scenario_rule}」` : "场景规则先验 · 通用基线";
  const l2 = document.createElement("span");
  l2.className = "unstructured";
  l2.textContent = sj.user_problem ? `自然语言理解 · ${clip(sj.user_problem, 34)}` : "自然语言理解 · 本次没有额外问题";
  legend.append(l1, l2);
  mixSection.appendChild(legend);
  judgeEl.appendChild(mixSection);

  // 最终需求维度：条形图为主，数字为辅
  const weights = sj.weights || {};
  const prior = sj.prior_weights || {};
  const keys = Object.keys(weights).sort((a, b) => (Number(weights[b]) || 0) - (Number(weights[a]) || 0));
  if (keys.length) {
    const dimSection = document.createElement("section");
    dimSection.className = "ins-section";
    dimSection.appendChild(insHead("最终需求维度", "按权重排序"));
    const max = Math.max(...keys.map(k => Number(weights[k]) || 0), 0.01);
    const list = document.createElement("div");
    list.className = "vdim-list";
    const row = k => {
      const wrap = document.createElement("div");
      wrap.className = "vdim";
      const nm = document.createElement("span");
      nm.className = "vdim-name";
      nm.textContent = DIM[k] || k;
      const track = document.createElement("div");
      track.className = "vdim-track";
      const fill = document.createElement("i");
      fill.className = "vdim-fill";
      fill.style.width = `${Math.min(100, ((Number(weights[k]) || 0) / max) * 100)}%`;
      track.appendChild(fill);
      if (prior[k] !== undefined) {
        const tick = document.createElement("i");
        tick.className = "vdim-tick";
        tick.style.left = `${Math.min(100, ((Number(prior[k]) || 0) / max) * 100)}%`;
        tick.title = `规则先验 ${Number(prior[k]).toFixed(2)}`;
        track.appendChild(tick);
      }
      const val = document.createElement("span");
      val.className = "vdim-val";
      val.textContent = (Number(weights[k]) || 0).toFixed(2);
      wrap.append(nm, track, val);
      return wrap;
    };
    keys.slice(0, 5).forEach(k => list.appendChild(row(k)));
    if (keys.length > 5) {
      const more = document.createElement("details");
      more.className = "vdim-more";
      const sum = document.createElement("summary");
      sum.textContent = `展开其余 ${keys.length - 5} 项`;
      more.appendChild(sum);
      keys.slice(5).forEach(k => more.appendChild(row(k)));
      list.appendChild(more);
    }
    const note = document.createElement("p");
    note.className = "vdim-note";
    note.textContent = "竖线为场景规则先验；条形为规则与自然语言判断合成后的最终权重。";
    dimSection.append(list, note);
    judgeEl.appendChild(dimSection);
  }

  // 完整解释与已审核样板放进折叠区，保持主视觉简洁
  const more = document.createElement("details");
  const sum = document.createElement("summary");
  sum.textContent = "完整策略说明";
  more.appendChild(sum);
  const detail = document.createElement("p");
  detail.textContent = sj.strategy_notes || "本次没有额外策略说明。";
  more.appendChild(detail);
  judgeEl.appendChild(more);
}

function renderVerify(r) {
  const dbg = document.getElementById("dbg-verify");
  if (dbg) dbg.hidden = false;
  const container = document.getElementById("verify") || dbg;
  if (!container) return;
  container.textContent = "";

  const vf = (r && r.verification) || {};
  const judge = vf.judge || {};
  const triage = vf.triage || {};
  const review = window.processReviewStatus ? window.processReviewStatus(r, r.artifacts || {}, r.trace || []) : { label: "", detail: "" };
  const vfSum = document.getElementById("vf-sum");
  if (vfSum) {
    vfSum.textContent = review.label || "";
    vfSum.title = review.detail || "";
  }

  const chat = document.createElement("div");
  chat.className = "chat";
  const addBubble = (tone, title, body, meta, opts = {}) => {
    const rowEl = document.createElement("div");
    rowEl.className = opts.threaded === false ? "chat-row untethered" : "chat-row";
    const avatar = document.createElement("div");
    avatar.className = "chat-avatar";
    avatar.setAttribute("aria-hidden", "true");
    if (opts.threaded === false) {
      avatar.className = "chat-spacer";
    } else if (window.BotPortrait) {
      avatar.appendChild(window.BotPortrait(opts.bot ?? 2, "#c28c6c"));
    }
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${tone}`.trim();
    const b = document.createElement("b");
    b.textContent = title;
    bubble.appendChild(b);
    if (body) {
      if (typeof body === "string") {
        const p = document.createElement("p");
        p.textContent = body;
        bubble.appendChild(p);
      } else {
        bubble.appendChild(body);
      }
    }
    if (meta) {
      const m = document.createElement("p");
      m.className = "chat-meta";
      m.textContent = meta;
      bubble.appendChild(m);
    }
    rowEl.append(avatar, bubble);
    chat.appendChild(rowEl);
    return bubble;
  };

  const rules = vf.rules || {};
  const ruleIssues = (rules.issues || []).length + (rules.platform_issues || []).length;
  const imageChecks = (vf.images || []).length;
  addBubble(
    ruleIssues ? "warn" : "ok",
    ruleIssues ? `规则检查：${ruleIssues} 处需要处理` : "规则检查通过",
    ruleIssues
      ? "数字、型号、图片与平台规格里有需要修正的地方，处理记录见下方。"
      : `数字、型号与平台规格已逐项核对，${imageChecks} 张图全部通过画面检查。`,
    "",
    { bot: 2 }
  );

  const overall = judge.overall || vf.state || "-";
  const pass = overall === "pass" || overall === "ok";
  addBubble(
    pass ? "ok" : "warn",
    pass ? "独立评审通过" : (overall === "not_reviewed" ? "独立评审未完成" : "独立评审提出意见"),
    pass ? "" : "评审问题与处理结果保留在下方，未完成的部分不会算作通过。",
    "独立上下文，不看写作过程，只看终稿",
    { bot: 4, threaded: false }
  );

  const rounds = vf.repair_rounds || [];
  if (rounds.length) {
    addBubble("ok", `自动修订 ${rounds.length} 轮`, "按评审意见定向修改后重新核验，只改被指出的位置。", "", { threaded: false });
  }

  const problems = judge.problems || [];
  if (problems.length) {
    const wrap = document.createElement("div");
    const list = document.createElement("ul");
    problems.slice(0, 6).forEach(p => {
      const li = document.createElement("li");
      li.textContent = `${p.where || ""}：${p.detail || ""}`.replace(/^：/, "");
      list.appendChild(li);
    });
    wrap.appendChild(list);
    addBubble("bad", "仍需人工确认的表达", wrap, "", { threaded: false });
  }

  const improvements = judge.improvements || [];
  if (improvements.length) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = `${improvements.length} 条可选优化 · 不影响通过`;
    det.appendChild(sum);
    const list = document.createElement("ul");
    improvements.forEach(p => {
      const li = document.createElement("li");
      li.textContent = p.detail || p.direction || "";
      list.appendChild(li);
    });
    det.appendChild(list);
    addBubble("ok", "可以更好的地方", det, "", { threaded: false });
  }

  const pendingConfirm = (r && r.pending_confirm) || vf.pending_confirm || [];
  if (pendingConfirm.length) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = `${pendingConfirm.length} 条发布前待确认`;
    det.appendChild(sum);
    const list = document.createElement("ul");
    pendingConfirm.forEach(item => {
      const li = document.createElement("li");
      li.textContent = typeof item === "string" ? item : (item.detail || JSON.stringify(item));
      list.appendChild(li);
    });
    det.appendChild(list);
    addBubble("warn", "这些信息需要门店核实", det, "", { threaded: false });
  }

  const compliance = vf.compliance || [];
  if (compliance.length) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = `${compliance.length} 条合规处理`;
    det.appendChild(sum);
    const list = document.createElement("ul");
    compliance.forEach(c => {
      const li = document.createElement("li");
      li.textContent = `${c.rule || ""}：${c.hit || ""} → ${c.action || ""}`.replace(/^：/, "");
      list.appendChild(li);
    });
    det.appendChild(list);
    addBubble("warn", "合规规则拦截", det, "", { threaded: false });
  }

  const platform = vf.platform || [];
  if (Array.isArray(platform) ? platform.length : Boolean(platform)) {
    addBubble("warn", "平台规格提示", Array.isArray(platform) ? platform.join("；") : String(platform), "", { threaded: false });
  }

  if (review.needsReview || r.human_review || r.automatic_followup || (triage.human || 0) > 0) {
    const rowEl = document.createElement("div");
    rowEl.className = "chat-row";
    const avatar = document.createElement("div");
    avatar.className = "chat-avatar";
    avatar.setAttribute("aria-hidden", "true");
    if (window.BotPortrait) avatar.appendChild(window.BotPortrait(5, "#c28c6c"));
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble warn";
    const b = document.createElement("b");
    b.textContent = (triage.human || 0) > 0 ? `有 ${triage.human} 项需要你决定` : "可以继续自动修订或复审";
    bubble.appendChild(b);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-secondary";
    btn.textContent = "打开问题详情 ↗";
    btn.addEventListener("click", () => window.ReviewQuestions.open(r));
    const action = document.createElement("p");
    action.className = "chat-action";
    action.appendChild(btn);
    bubble.appendChild(action);
    rowEl.append(avatar, bubble);
    chat.appendChild(rowEl);
  }

  container.appendChild(chat);
}

init();
