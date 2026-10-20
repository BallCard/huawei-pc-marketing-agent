(function () {
  "use strict";
  const WHERE = { title: "标题", lead: "导语", body: "正文", caption: "图注", cta: "行动引导" };
  const PLATFORMS = { xiaohongshu: "小红书", wechat_article: "公众号", moments: "朋友圈", poster: "门店海报" };
  const DIMENSIONS = {portability:"携带负担",battery:"续航",display:"查看资料",os_compat:"软件兼容",ecosystem:"设备协同",ports:"外设连接",performance:"性能",creation:"内容创作",value:"选购成本"};
  const reviewStatus = typeof module !== "undefined" && module.exports ? require("./review-status.js") : window.processReviewStatus;
  const text = x => typeof x === "string" ? x : x?.detail || x?.text || x?.reason || "";
  const locate = p => `${WHERE[p?.where] || "文稿"}${p?.index >= 0 ? `第 ${p.index + 1} 段` : ""}`;
  const cleanIssue = x => text(x).replace(/^\[(title|lead|body|caption|cta)#(-?\d+)\]\s*/, (_, where, index) => `${locate({where,index:+index})}：`).replace(/^\[平台\]\s*/, "平台要求：");
  function describe(stage, snapshot) {
    const a = snapshot.artifacts || {}, steps = snapshot.steps || [], result = snapshot.result || {};
    const request = a.request || result.task || snapshot.task || {};
    const spec = steps.find(s => s.step === "style" && s.status === "done")?.detail?.spec;
    const strategy = steps.find(s => s.step === "strategy" && s.status === "done")?.detail;
    const platform = spec?.name || strategy?.platform_name || result.platform_spec?.platform_name || PLATFORMS[request.platform] || "";
    const model = a.sources?.model || a.model?.matched || a.model?.model_id;
    const facts = a.evidence?.facts || a.plan?.facts || [];
    const snippets = a.sources?.snippets || [], images = a.sources?.images || [];
    const active = stage.status === "running", records = [];
    const add = (label, detail = "", extra = {}) => records.push({ label, detail: text(detail), status: "done", ...extra });
    const source = fact => {
      const s = typeof fact.source === "object" ? fact.source : {label:fact.source};
      add(`${fact.id ? fact.id + " · " : ""}${fact.sid || ""} · ${s?.label || s?.title || "资料片段"}`, fact.text,
        { kind: /^https?:\/\//.test(s?.path || "") ? "web" : "knowledge", path: s?.path || "", sourceType: /^https?:\/\//.test(s?.path || "") ? "网页资料" : "知识库" });
    };
    const documents = () => {
      const docs = new Map();
      for (const s of snippets) {
        const key = s.source?.path || s.source?.title || s.source?.label;
        if (!key) continue;
        if (!docs.has(key)) docs.set(key, {snippet:s,count:0});
        docs.get(key).count++;
      }
      for (const {snippet:s,count} of [...docs.values()].slice(0, 3)) add(s.source?.title || s.source?.label || s.sid,
        `已读取 ${count} 条资料片段`, {kind:"knowledge",path:s.source?.path || "",sourceType:"知识库"});
    };
    const toolEvents = (snapshot.events || []).filter(e => e.type === "tool_activity" && e.step === "retrieve");
    const latestTools = new Map();
    for (const event of toolEvents) latestTools.set(event.operation + ":" + (event.resource || ""), event);
    const network = [...latestTools.values()].filter(e => (e.source_kind || e.kind) === "web");
    const checks = version => {
      const finalVersion = a.final?.version || result.verification?.article_version || (a["draft:2"] ? 2 : 1);
      const rules = a[`rules:${version}`], review = a[`review:${version}`] || (version === finalVersion ? result.verification?.judge : null);
      for (const [key,label,published] of [[version===1?"verify":"reverify","规则检查（自动）",rules],[version===1?"judge":"rejudge","独立评审（自动模型）",review]]) {
        const step = steps.find(s=>s.step===key);
        if (!step && !published) continue;
        const artifact = published || (step?.status === "done" && (step.detail?.overall || step.detail?.issues) ? step.detail : null);
        const problems = artifact?.problems || [...(artifact?.issues || []), ...(artifact?.platform_issues || [])];
        let detail = artifact ? problems.length ? cleanIssue(problems[0]) : "已完成，未发现待修改问题" : step?.detail?.error || step?.input_summary || "等待检查结果";
        let status = artifact ? problems.length ? "needs_fix" : "done" : step?.status || "incomplete";
        if (key.includes("judge") && (artifact && !["pass","ok"].includes(artifact.overall) || status === "error")) {
          const summary = reviewStatus(result,{...a,...(artifact?{[`review:${version}`]:artifact}:{})},steps,version);
          detail = summary.detail; status = summary.state === "incomplete" ? "incomplete" : "needs_fix";
        }
        add(label,detail,{status,kind:"check",tool:key});
      }
    };
    let title = stage.label || "等待创作任务", note = "", tone = "";
    switch (stage.id) {
      case "scene": {
        title = active ? "正在解析创作需求" : "创作需求已解析";
        const brief = a.brief;
        const audience = request.audience || brief?.audience, scenario = request.scenario || brief?.scenario;
        if (audience || scenario) add("人群与使用场景", [audience,scenario].filter(Boolean).join(" · "), {kind:"input"});
        else {
          const input = request.extra || steps.find(s=>s.step==="scene")?.input_summary;
          if (input) add("收到的需求",input,{kind:"input"});
        }
        if (brief?.user_problem) add("识别出的具体任务",brief.user_problem,{kind:"analysis"});
        else if (request.extra && (audience || scenario)) add("场景补充",request.extra,{kind:"input"});
        if (brief) {
          const priorities = (brief.top_dims || []).map(d=>DIMENSIONS[d]).filter(Boolean);
          const choices = (brief.tradeoffs || []).join("；") || (brief.soft_preferences || []).map(text).filter(Boolean).slice(0,2).join("；");
          if (choices || priorities.length) add("本次判断摘要",[choices,priorities.length?"优先关注："+priorities.slice(0,3).join("、"):""].filter(Boolean).join("；"),{kind:"analysis"});
        }
        const constraints = brief?.hard_constraints || request.constraints || [];
        const unknown = [...(brief?.unmappable || []), ...(brief?.need_info?.questions || [])].map(text).filter(Boolean);
        if (constraints.length || unknown.length) add(unknown.length ? "限制与待确认" : "用户限制",[...constraints,...unknown].join("；"),{kind:"input"});
        note = brief?.matched_scenario_rule ? `场景规则：${brief.matched_scenario_rule}` : brief ? "场景判断已返回" : "正在分析本次场景，结果返回后展开";
        break;
      }
      case "sources": {
        title = active ? "正在读取产品资料" : "产品资料已读取";
        const currentWeb = network.findLast(e=>e.status==="running");
        if (currentWeb && active) title = currentWeb.label;
        if (snippets.length) documents();
        else if (model) add("已匹配型号", model, {kind:"knowledge"});
        else {
          const step = steps.find(s=>s.step==="model");
          if (step) add(step.label, step.input_summary, {status:step.status,kind:"input"});
        }
        if (network.length) records.splice(2);
        for (const e of network.slice(-2)) add(e.status === "running" && !active ? "联网处理未返回" : e.label, e.detail,
          {kind:"web",status:e.status === "running" && !active ? "error" : e.status,path:e.url || "",sourceType:"联网"});
        if (a.model?.mode === "given") note = "指定型号，已跳过推荐";
        break;
      }
      case "plan":
        title = active ? "正在筛选知识库证据" : `已选定 ${facts.length} 条证据`;
        if (facts.length) facts.slice(0,3).forEach(source); else documents();
        note = active ? `已提交 ${snippets.length} 条候选资料${platform ? ` · ${platform}` : ""}` : `来源：${model || "本次型号资料"}`;
        break;
      case "compose":
        title = active ? `正在生成${platform}初稿` : `${platform}初稿已生成`;
        facts.slice(0,2).forEach(source);
        if (images.length) add(`已载入 ${images.length} 张候选图片`, images.slice(0,2).map(i=>i.name).join("、"), {kind:"image"});
        note = a["draft:1"] ? `已返回 ${a["draft:1"].blocks?.length || 0} 个图文段落` : `${facts.length} 条证据${platform ? ` · ${platform}写作规范` : ""}`;
        break;
      case "review": case "recheck": {
        const version = stage.id === "review" ? 1 : 2;
        title = active ? `正在检查稿件 v${version}` : `稿件 v${version} 检查已结束`;
        checks(version);
        const review = a[`review:${version}`];
        if (review?.problems?.[0]?.quote) add(`${locate(review.problems[0])} · 问题原句`, review.problems[0].quote, {kind:"issue"});
        note = `${facts.length} 条原始证据${platform ? ` · ${platform}平台规范` : ""}`;
        break;
      }
      case "lookup": {
        title = active ? "正在补查本型号资料" : "本型号补查已结束";
        const problem = a["review:1"]?.problems?.find(p=>["unsupported","evidence_gap"].includes(p.type));
        if (problem) add(`${locate(problem)} · 证据缺口`, problem.quote || problem.detail, {kind:"issue"});
        if (a.lookup) add("补查结果", a.lookup.reason, {kind:"knowledge"});
        else documents();
        note = model || "";
        break;
      }
      case "repair": {
        title = active ? "正在按审核问题修订" : "定向修订已完成";
        const problems = a["review:1"]?.problems || [];
        const rules = a["rules:1"];
        const all = a.revision?.issues || [...problems.map(p=>`${locate(p)}：${p.detail}`), ...(rules?.issues || []).map(p=>`${locate(p)}：${p.detail}`), ...(rules?.platform_issues || [])];
        all.slice(0,2).forEach(p=>add("处理审核问题",cleanIssue(p),{kind:"issue"}));
        if (a.revision) add("修订结果", `已修改 ${a.revision.changes?.length || 0} 处文段`, {kind:"check"});
        if (!records.length && facts[0]) source(facts[0]);
        note = "稿件 v1 → v2";
        break;
      }
      case "finish": {
        if (snapshot.state === "error") { title="创作已中断"; add("错误信息",snapshot.error || "本次执行失败",{status:"error",kind:"issue"}); tone="warn"; break; }
        if (result.status === "need_info") { title="等待补充信息"; (result.questions || []).slice(0,3).forEach(q=>add("待确认",q,{kind:"input"})); tone="warn"; break; }
        if (result.status === "budget_exceeded") { title="已到本次时间预算"; add("当前结果","尚无完整稿件；审核未完成",{kind:"issue",status:"error"}); tone="warn"; break; }
        const final=a.final, version=final?.version || (a["draft:2"]?2:1);
        const summary = reviewStatus(result,a,steps,version);
        title=final?.state==="passed"?`终稿 v${version} 已完成`:`终稿 v${version} · ${summary.label}`;
        checks(version);
        const remaining = (final?.remaining || []).filter(s=>summary.state!=="incomplete" || !/独立评审|预算/.test(s));
        for (const issue of remaining.slice(0,1)) add("待核对的具体问题",issue,{kind:"issue",status:"needs_fix"});
        note=summary.needsReview ? summary.state === "incomplete" ? "尚无完整自动评审结论，使用前需补查或复核" : "仅列出的未解决问题需要复核" : `${facts.length} 条引用证据 · ${a.revision?.changes?.length || 0} 处修订`;
        tone=final?.state==="passed"?"passed":"warn";
        break;
      }
      default: title="等待创作任务";
    }
    // Supplementary images can come from cached official assets; this is not a live network call.
    if (stage.id === "sources" && !network.length && a.sources?.image_search) {
      const search=a.sources.image_search;
      if (search.status === "cached") add("复用已核验的官方图片",search.reason,{kind:"cache",sourceType:"缓存",path:search.pages?.[0] || ""});
      else if (["verified","unavailable"].includes(search.status)) add("官网补图检索已结束",search.reason,{kind:"web",sourceType:"联网",path:search.pages?.[0] || "",status:search.status==="verified"?"done":"error"});
    }
    if (!records.length && stage.status === "running") add("任务已提交", "等待本次处理结果返回", {status:"running",kind:"task"});
    if (stage.status === "error" && stage.id !== "finish") {
      title = `${stage.label}未完成`;
      const error = stage.entries?.find(s=>s.status==="error")?.detail?.error;
      if (error) add("处理错误",error,{kind:"issue",status:"error"});
    }
    return {title,records:records.slice(0,4),note,tone};
  }
  if (typeof module !== "undefined" && module.exports) module.exports=describe;
  else window.describeProcessActivity=describe;
})();
