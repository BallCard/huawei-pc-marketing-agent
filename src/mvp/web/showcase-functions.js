(function () {
  "use strict";

  const features = {
    welcome: { no: "01", title: "极简开屏与场景入口", theme: "人机交互", image: "/static/showcase-assets/01-welcome.png", caption: "真实界面：开屏与门店入口", summary: "把第一次使用收束成一个明确动作：从门店、角色和本次任务进入，而不是面对一页空白的提示词。", talk: "这里先不要讲 AI 有多强，先讲它让门店从一个具体场景开始。开屏已经把“我要为谁做什么”放在了入口上。", tags: ["人机交互", "体验设计"], next: "下一步看创作简报如何把场景变成可填写的经营参数。" },
    brief: { no: "02", title: "结构化创作简报", theme: "生态营销 · 人机交互", image: "/static/showcase-assets/brief-filled.png", caption: "真实界面：创作简报完整填写态", summary: "把人群、场景、平台、产品、目标和私域触点变成可以修改、复用、回看的经营参数。", talk: "这里不是在填提示词，而是在告诉系统：这家店要服务谁、发生在什么场景、准备把内容带到哪里，并且希望下一步发生什么。", tags: ["生态营销", "人机交互"], next: "下一步看需求含糊时，系统会怎样补关键缺口。" },
    clarify: { no: "03", title: "智能追问", theme: "人机交互", image: "/static/showcase-assets/ask-1.png", caption: "真实界面：需求确认弹窗", summary: "当人群、场景或任务仍然有关键缺口时，系统只追问影响结果的一点，并允许直接补充。", talk: "它不是把一长串问题甩给用户，而是问一个最值得确认的问题。人给边界，系统再继续往下做。", tags: ["人机交互", "过程可见"], next: "确认之后，系统会把自然语言诉求拆成需求意图和权重。" },
    weight: { no: "04", title: "需求意图与 Weight Mix", theme: "技术升级", image: "/static/showcase-assets/weight-mix.png", caption: "真实界面：结构化规则与自然语言权重", summary: "将稳定的场景规则与用户的自然语言诉求组合起来，形成可解释的需求优先级，而不是只靠模型猜角度。", talk: "这页最适合讲技术升级：结构化指标先提供稳定骨架，自然语言再补足真实诉求，最后形成可回看的权重构成。", tags: ["技术升级", "可解释决策"], next: "有了权重，Agent 才知道该从哪些资料里优先找什么。" },
    context: { no: "05", title: "产品与场景上下文", theme: "生态营销 · 技术升级", image: "/static/showcase-assets/scene-analysis.png", caption: "真实界面：产品图片与场景分析", summary: "知识库、机型资料、登记图片和门店历史共同进入上下文；不确定的内容保持为待确认状态。", talk: "系统不是凭空写一篇“看起来像营销”的文字，而是先把这家店的产品事实、场景和历史稿件放到同一个工作上下文里。", tags: ["生态营销", "技术升级"], next: "接下来进入 Agent 阶段，开始把工作拆开并留下过程记录。" },
    agent: { no: "06", title: "Agent 实时编排", theme: "技术升级 · 人机交互", image: "/static/showcase-assets/work.png", caption: "真实界面：生成过程与阶段轨迹", summary: "理解需求、准备依据、确定立意、图文创作、独立评审、定向修订和终稿复核各自承担不同职责。", talk: "这里不是一个模型从头写到尾，而是一条能被看见的生产线。每个阶段有自己的输入、输出和处理记录，等待时间也变成可解释的过程。", tags: ["技术升级", "人机交互"], next: "作品完成后，继续看事实核验和风险分流。" },
    visual: { no: "07", title: "视觉海报与产品外观保真", theme: "技术升级 · 生态营销", image: "/static/gallery/result.jpg", caption: "真实界面：作品与产品视觉交付", summary: "场景化视觉可以有创意，但产品外观、型号和登记图片仍然沿用真实素材，避免重绘导致事实偏差。", talk: "视觉不是为了把页面做得更花，而是把产品放进用户正在经历的场景。创意负责表达，产品外观负责守住事实。", tags: ["生态营销", "视觉核验"], next: "图文作品交付前，所有主张还要回到事实核验层。" },
    evidence: { no: "08", title: "事实核验与 Fact ID", theme: "技术升级 · 人机交互", image: "/static/showcase-assets/evidence.png", caption: "真实界面：事实与配图引用表", summary: "产品事实、适用条件、配图和来源被逐项列出，正文里的主张可以回查到知识库原文。", talk: "有据不是一句口号，而是每条主张都能找到引用。数字、型号、接口、系统和图片分别有对应来源，不确定的兼容性不会被硬写成承诺。", tags: ["技术升级", "人机交互"], next: "如果检查发现风险，系统会把可自动修订和需要人判断的问题分开。" },
    review: { no: "09", title: "双轨审核与风险分流", theme: "技术升级 · 人机交互", image: "/static/showcase-assets/evidence-judge.png", caption: "真实界面：审核结果与待裁定问题", summary: "确定性规则、独立评审和人工裁定各走自己的路径；自动能修的直接回流，重要未决保留给人。", talk: "这一页要强调分工：模型不替人承担最终责任。它可以发现、归类、修订，但对关键未决和误报，最后仍然由人做裁定。", tags: ["技术升级", "人机交互"], next: "完成审核后，内容按平台结构重新组织并交付。" },
    delivery: { no: "10", title: "多平台原生预览与交付", theme: "生态营销", image: "/static/gallery/result.jpg", caption: "真实界面：图文作品与平台预览", summary: "小红书、公众号、朋友圈和门店海报有不同的信息节奏，系统按平台结构组织标题、正文、图片和行动。", talk: "交付的不是同一段话换几个标题，而是同一份产品事实在不同渠道里变成原生内容，最后可以直接复制、预览或导出。", tags: ["生态营销", "平台原生"], next: "内容发布之后，回到门店看板继续沉淀触点和历史。" },
    revision: { no: "11", title: "快捷打磨与离线导出", theme: "技术升级 · 生态营销", image: "/static/showcase-assets/export-offline.png", caption: "真实界面：定向修订与离线导出", summary: "对具体问题做定向打磨，保留可回查的修改记录，并支持复制正文和导出离线 HTML。", talk: "它不是让用户重新生成一遍，而是指着具体问题改一处、复核一处。这样速度和可控性可以同时保留。", tags: ["技术升级", "可交付"], next: "最后看这些内容怎样回到门店的经营动作。" },
    store: { no: "12", title: "我的门店与私域触点", theme: "生态营销 · 人机交互", image: "/static/showcase-assets/store-final.png", caption: "真实界面：门店私域经营看板", summary: "企微、朋友圈、门店社群和到店邀约被整理成可继续跟进的触点，内容不再停在“发布完成”。", talk: "生态营销最后要落到门店：谁刚加了企微、谁预约到店、哪条历史稿件已经审核，都能成为下一次工作的上下文。", tags: ["生态营销", "经营闭环"], next: "这也解释了为什么历史稿件和复盘不是附属页面，而是系统的一部分。" },
    history: { no: "13", title: "历史稿件与跨稿复盘", theme: "生态营销 · 技术升级", image: "/static/showcase-assets/judge-final.png", caption: "真实界面：历史稿件与审核状态", summary: "历史稿件、审核状态和后续动作持续沉淀，用于字面避重、经验复用和门店经营复盘。", talk: "每次生成都不是一次性消费。已经写过什么、哪些问题被修过、哪个触点还在跟进，都会影响下一次任务。", tags: ["生态营销", "技术升级"], next: "至此，功能可以归回生态营销、技术升级和人机交互三条理念线。" }
  };

  const dialog = document.getElementById("feature-dialog");
  const image = document.getElementById("dialog-image");
  const kicker = document.getElementById("dialog-kicker");
  const theme = document.getElementById("dialog-theme");
  const title = document.getElementById("dialog-title");
  const summary = document.getElementById("dialog-summary");
  const talk = document.getElementById("dialog-talk");
  const tags = document.getElementById("dialog-tags");
  const next = document.getElementById("dialog-next");
  const caption = document.getElementById("dialog-caption");

  function openFeature(id) {
    const feature = features[id];
    if (!feature) return;
    kicker.textContent = `FEATURE / ${feature.no}`;
    theme.textContent = feature.theme;
    title.textContent = feature.title;
    summary.textContent = feature.summary;
    talk.textContent = feature.talk;
    next.textContent = feature.next;
    caption.textContent = feature.caption;
    image.src = feature.image;
    image.alt = feature.title;
    tags.replaceChildren(...feature.tags.map((tag) => {
      const item = document.createElement("span");
      item.textContent = tag;
      return item;
    }));
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  document.querySelectorAll("[data-feature]").forEach((button) => {
    button.addEventListener("click", () => openFeature(button.dataset.feature));
  });
  document.querySelector(".dialog-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") dialog.close();
  });

  const pointer = document.querySelector(".pointer-spotlight");
  if (pointer && window.matchMedia("(pointer: fine)").matches) {
    let pointerMoved = false;
    document.addEventListener("pointermove", (event) => {
      pointerMoved = true;
      pointer.style.setProperty("--pointer-x", `${event.clientX}px`);
      pointer.style.setProperty("--pointer-y", `${event.clientY}px`);
      pointer.classList.add("is-visible");
    }, { passive: true });
    document.addEventListener("pointerleave", () => pointer.classList.remove("is-visible"));
    document.addEventListener("pointerdown", () => {
      if (!pointerMoved) return;
      pointer.classList.remove("is-clicking");
      void pointer.offsetWidth;
      pointer.classList.add("is-clicking");
    }, { passive: true });
  }
}());
