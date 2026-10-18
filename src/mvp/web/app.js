const DIM = {
  portability: "便携轻薄",
  display: "屏幕显示",
  performance: "性能与容量",
  battery: "续航与充电",
  ports: "接口与扩展",
  creation: "创作与手写",
  ecosystem: "协同与AI",
  os_compat: "系统与软件兼容",
  value: "配置价值"
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
      constraints: "不要提价格，语气轻松",
      extra: "经常背去图书馆，希望轻一点"
    }
  },
  {
    title: "同一款 · 换公众号",
    sub: "长文 · 职场办公",
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
      constraints: "不要提价格",
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

async function init() {
  try {
    const res = await fetch("/api/info");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const info = await res.json();

    const statusEl = UI.$("#status");
    if (statusEl) {
      const label = statusEl.querySelector(".status-label") || statusEl;
      label.textContent = `知识库：${info.kb?.kb_name || ""}（${info.kb?.models ?? 0} 个型号） · 写作 ${info.writer_model || ""} · 审核 ${info.judge_model || ""}`;
    }

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
    const need = UI.$("#need");
    if (need) {
      need.replaceChildren(UI.el("div", { class: "card" }, [
        UI.el("h3", {}, ["系统初始化失败"]),
        UI.el("p", {}, [err.message || String(err)])
      ]));
    }
  }

  const presetsEl = UI.$("#presets");
  if (presetsEl) {
    presetsEl.replaceChildren();
    PRESETS.forEach(p => {
      const btn = UI.el("button", {
        type: "button",
        class: "preset",
        title: "点击直接运行"
      }, [
        UI.el("b", {}, [p.title]),
        UI.el("span", {}, [p.sub])
      ]);
      btn.addEventListener("click", () => {
        fill(p.v);
        submit("");
      });
      presetsEl.appendChild(btn);
    });
  }

  const btnGo = UI.$("#go");
  if (btnGo) {
    btnGo.addEventListener("click", () => submit(""));
  }

  const btnRedo = UI.$("#redo");
  if (btnRedo) {
    btnRedo.addEventListener("click", () => {
      const instr = UI.$("#instr")?.value || "";
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

  if (new URLSearchParams(location.search).has("debug")) {
    document.querySelectorAll("details.dbg").forEach(d => {
      d.open = true;
    });
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
}

function readTask() {
  const rawConstraints = UI.$("#constraints")?.value || "";
  const constraints = rawConstraints
    .split(/[,，;；]/)
    .map(s => s.trim())
    .filter(Boolean);

  return {
    product: UI.$("#product")?.value.trim() || "",
    audience: UI.$("#audience")?.value.trim() || "",
    scenario: UI.$("#scenario")?.value.trim() || "",
    platform: UI.$("#platform")?.value || "xiaohongshu",
    speed: UI.$("#speed")?.value || "quality",
    goal: UI.$("#goal")?.value.trim() || "",
    constraints,
    extra: UI.$("#extra")?.value.trim() || ""
  };
}

async function submit(instruction) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  const task = readTask();
  const payload = {
    ...task,
    instruction: instruction ? String(instruction).trim() : ""
  };

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

  showFlow([], true);

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      throw new Error(`启动任务失败 HTTP ${res.status}`);
    }
    const data = await res.json();
    const jid = (data && typeof data === "object") ? (data.job?.id || data.job || data.id) : data;
    if (!jid) {
      throw new Error("服务端未返回有效的任务 ID");
    }
    poll(jid);
  } catch (err) {
    unlock();
    const runbar = UI.$("#runbar");
    if (runbar) runbar.hidden = true;
    if (need) {
      need.replaceChildren(UI.el("div", { class: "card" }, [
        UI.el("h3", {}, ["任务启动失败"]),
        UI.el("p", {}, [err.message || String(err)])
      ]));
    }
  }
}

function poll(jid) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/job/${jid}`);
      if (!res.ok) return;
      const j = await res.json();
      const isRunning = j.state === "running";
      showFlow(j.steps || [], isRunning);

      if (j.state === "done") {
        clearInterval(pollTimer);
        pollTimer = null;
        unlock();
        showResult(j.result);
      } else if (j.state === "error") {
        clearInterval(pollTimer);
        pollTimer = null;
        unlock();
        const need = UI.$("#need");
        if (need) {
          need.replaceChildren(UI.el("div", { class: "card" }, [
            UI.el("h3", {}, ["运行出错"]),
            UI.el("p", {}, [`运行出错：${j.error || "未知异常"}`])
          ]));
        }
      }
    } catch {
      // 网络异常静默重试
    }
  }, 900);
}

function unlock() {
  const btnGo = UI.$("#go");
  const btnRedo = UI.$("#redo");
  if (btnGo) btnGo.disabled = false;
  if (btnRedo) btnRedo.disabled = false;
}

function showFlow(steps, running) {
  const runbar = UI.$("#runbar");
  if (runbar) {
    if (running) {
      runbar.hidden = false;
      const lastStep = steps && steps.length > 0 ? steps[steps.length - 1] : null;
      const stepLabel = lastStep ? (lastStep.label || lastStep.step || "处理中") : "准备中";
      const doneCount = steps ? steps.filter(s => s.status === "done").length : 0;
      const elapsedSec = Math.round((Date.now() - startedAt) / 1000);

      runbar.replaceChildren(
        UI.el("span", { class: "runbar-spin" }),
        UI.el("b", { class: "runbar-step" }, [stepLabel]),
        UI.el("span", { class: "runbar-meta" }, [`已完成 ${doneCount} 步 · 已用 ${elapsedSec} 秒`])
      );
    } else {
      runbar.hidden = true;
    }
  }

  const flowBox = UI.$("#flow");
  const flowSum = UI.$("#flow-sum");
  const dbgFlow = UI.$("#dbg-flow");

  const flowRes = typeof window.buildFlow === "function" ? window.buildFlow(steps, running) : null;
  if (flowBox && flowRes) {
    const node = (flowRes instanceof Node) ? flowRes : flowRes.node;
    if (node) flowBox.replaceChildren(node);
  }

  const curStep = steps && steps.length > 0 ? (steps[steps.length - 1].label || steps[steps.length - 1].step || "执行中") : "准备中";
  const summaryText = running
    ? `运行中… ${curStep}`
    : (flowRes?.summary || (steps && steps.length ? `已完成 ${steps.length} 步` : "完成"));

  if (flowSum) flowSum.textContent = summaryText;
  if (dbgFlow) dbgFlow.hidden = false;
}

function showResult(r) {
  current = r;
  if (!r) return;

  if (r.status === "need_info") {
    const stage = UI.$("#stage");
    if (stage) stage.hidden = true;
    showNeedInfo(r);
    return;
  }

  const stage = UI.$("#stage");
  if (stage) stage.hidden = false;

  const stageTitle = UI.$("#stage-title");
  if (stageTitle) {
    const platformKey = r.platform_spec?.platform || r.task?.platform || "";
    const platformName = r.platform_spec?.platform_name || platformKey;
    const hint = UI.PLATFORM_HINT[platformKey] || "";
    const titleText = r.article?.title || "图文成品";
    const subText = hint ? `${platformName} · ${hint}` : platformName;

    stageTitle.replaceChildren(
      UI.el("b", {}, [titleText]),
      UI.el("span", {}, [subText])
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
    preview.replaceChildren(window.renderPreview(r));
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
}

function showNeedInfo(r) {
  const stage = UI.$("#stage");
  if (stage) stage.hidden = true;

  const need = UI.$("#need");
  if (!need) return;

  const info = r.need_info || r.scene_judgement?.need_info || {};
  const questions = info.questions || [];
  const candidates = info.candidates || r.candidates || [];

  const card = UI.el("div", { class: "card need-card" }, [
    UI.el("h3", {}, ["需要补充信息"])
  ]);

  if (questions.length > 0) {
    const ul = UI.el("ul", { class: "need-questions" });
    questions.forEach(q => {
      ul.appendChild(UI.el("li", {}, [String(q)]));
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
}

function plainText(r) {
  if (!r || !r.article) return "";
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

  let styles = "";
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      if (sheet.cssRules) {
        for (const rule of Array.from(sheet.cssRules)) {
          styles += rule.cssText + "\n";
        }
      }
    } catch {
      // 忽略同源跨域样式限制
    }
  }

  const headHtml = `<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>华为PC营销图文</title>\n<style>\n${styles}\n</style>`;
  const bodyHtml = clone.outerHTML;
  const htmlDoc = `<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n${headHtml}\n</head>\n<body style="padding:24px;background:#f5f5f5;">\n${bodyHtml}\n</body>\n</html>`;

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
  const rem = vf.remaining || [];
  chips.appendChild(UI.tag("产品事实 " + (rem.length ? "有未解决项" : "全部有依据"), rem.length ? "bad" : "ok"));

  const vfImages = vf.images || [];
  const imgMatch = vfImages.length > 0 && vfImages.every(i => i.model_match);
  chips.appendChild(UI.tag("图片型号 " + (imgMatch ? "全部一致" : "存在不一致"), imgMatch ? "ok" : "bad"));

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
  chips.appendChild(UI.tag(`审核 ${overall}`, judgeOk ? "ok" : "warn"));

  const model = (r && r.model) || {};
  chips.appendChild(UI.tag(`型号 ${model.name || "-"}`));
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
    tdSrc.textContent = i.source_title || i.source_url || "";
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
  const remaining = vf.remaining || [];
  const vfSum = document.getElementById("vf-sum");
  if (vfSum) {
    vfSum.textContent = remaining.length ? `${remaining.length} 项待人工关注` : "通过";
  }

  const container = document.getElementById("verify") || dbg;
  container.textContent = "";

  if (remaining.length > 0) {
    const pRem = document.createElement("p");
    pRem.textContent = "仍需人工关注：";
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
    sum.textContent = "审核模型提示（需人工确认，未自动改写）";
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
