/* Visual prototype only. Progress and revisions are local examples, with no model or job calls. */
(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icon = name => `<svg class="icon" aria-hidden="true"><use href="#ic-${name}"/></svg>`;
  const pageNames = {brief:'创作简报',process:'生成过程',work:'图文作品',evidence:'事实核验'};
  const platforms = {xhs:'小红书',wechat:'公众号',moments:'朋友圈',poster:'门店海报'};
  const presets = [
    {title:'大学开学',description:'给大学新生介绍一台适合随身携带的电脑。',prompt:'给每天背着电脑去图书馆的大学新生，写一篇小红书笔记，突出便携，邀请他们到店体验。'},
    {title:'通勤办公',description:'从移动办公场景出发，突出日常使用需求。',prompt:'为经常通勤的职场人，写一篇围绕移动办公的产品介绍，语气直接自然。'},
    {title:'创意工作',description:'介绍创作场景，提醒核对专业软件适配。',prompt:'写给摄影和设计爱好者，从日常创作场景出发介绍电脑，提醒读者先核对专业软件适配。'}
  ];
  const imageNames = ['hwpc_matebook-14-harmonyos_原野绿多彩配色_04.png','hwpc_matebook-14-harmonyos_多彩配色外观_01_7e0eedb6.png','hwpc_matebook-14-harmonyos_深空灰沉稳配色_05.png'];
  const images = imageNames.map(name => `/img/${encodeURIComponent('HUAWEI MateBook 14')}/${encodeURIComponent(name)}`);
  const colors = ['原野绿','樱粉金','深空灰'];
  const stages = [
    {name:'理解需求',title:'正在理解需求',description:'整理读者、使用场景和这次的表达目标。',detail:'示例场景：大学新生、开学季。表达目标：邀请读者到店体验。'},
    {name:'查找依据',title:'正在查找依据',description:'查找对应型号的产品资料和登记配图。',detail:'示例资料：HUAWEI MateBook 14（鸿蒙版）的产品事实、卖点与限制、图片索引。'},
    {name:'编写图文',title:'正在编写图文',description:'围绕日常使用场景，组织标题、正文和配图。',detail:'示例内容围绕便携和校园日常展开，并保留具体配置与软件适配提醒。'},
    {name:'核对事实',title:'正在核对事实',description:'对照产品资料，检查型号、配图与表达。',detail:'核对示例型号与登记图片；将专业软件适配列为发布前待确认项。'},
    {name:'完成作品',title:'图文已准备好',description:'示例图文和引用来源已经整理完成。',detail:'可查看图文、切换配图，并对照来源。专业软件适配需要发布者确认。'}
  ];
  const facts = [
    {category:'产品型号',title:'HUAWEI MateBook 14（鸿蒙版）',file:'产品事实.md',quote:'产品名称：HUAWEI MateBook 14（鸿蒙版）。',note:'对应当前示例型号，使用时需区分具体系统与销售版本。'},
    {category:'产品配色',title:'提供原野绿等配色',file:'图片索引.csv',quote:'登记图片说明：原野绿多彩配色。画面展示浅绿色笔记本整机。',note:'配图展示圆形键帽，需与具体销售配置对应。'},
    {category:'适用条件',title:'专业课程所需软件，需要先确认适配。',file:'卖点与限制.md',quote:'软件使用需结合系统版本和具体应用适配情况核对。',note:'请携带常用软件清单到门店，核对应用适配情况后再发布。',pending:true}
  ];
  const draft = {prompt:'',platform:'xhs',model:'auto',tone:'自然分享',goal:'',constraints:'',speed:'quality'};
  try {
    const saved = JSON.parse(localStorage.getItem('huazhang-minimal-draft-v1') || '{}');
    for (const key of Object.keys(draft)) if (typeof saved?.[key] === 'string') draft[key] = saved[key];
    if (!Object.hasOwn(platforms,draft.platform)) draft.platform = 'xhs';
    if (!['auto','14'].includes(draft.model)) draft.model = 'auto';
    if (!['自然分享','直接介绍','克制表达'].includes(draft.tone)) draft.tone = '自然分享';
    if (!['quality','fast'].includes(draft.speed)) draft.speed = 'quality';
  } catch (_) { /* A blocked store still leaves a usable in-memory draft. */ }
  const state = {page:'brief',draft,preferences:false,processDetails:false,stage:3,playing:false,inspected:null,image:0,device:'desktop',refined:false,refineKind:'tone',refineChoice:'tone',refineText:'',fact:null,error:''};
  let timer, toastTimer;

  const productImage = () => `<img src="${images[state.image]}" alt="HUAWEI MateBook 14（鸿蒙版）${colors[state.image]}登记产品图">`;
  const button = (label,action,primary = false) => `<button type="button" class="button${primary?' primary':''}" data-action="${action}">${label}</button>`;
  const platformOptions = () => Object.entries(platforms).map(([key,label]) => `<option value="${key}"${draft.platform===key?' selected':''}>${label}</option>`).join('');
  function plainSelect(label,name,options) {
    return `<label class="plain-select"><span class="visually-hidden">${label}</span><select name="${name}" aria-label="${label}">${options}</select></label>`;
  }
  function title() {
    if (!state.refined) return '新学期的轻巧搭档，陪你去每一间自习室。';
    return state.refineKind==='tone' ? '课本已经够厚了，电脑就选轻巧一点。' : '选开学电脑，先试重量，再看适配。';
  }
  function paragraphs() {
    const first = !state.refined ? '新学期，从宿舍到教室，再到图书馆，一台每天随行的电脑，轻巧很重要。' : state.refineKind==='tone' ? '课本、笔记、水杯，书包里的东西已经不少。挑选每天随行的电脑时，不妨先试试重量和手感。' : '开学选电脑，先带着常用软件清单到门店，试试重量与手感，再核对系统和应用适配情况。';
    return [first,'HUAWEI MateBook 14（鸿蒙版）提供原野绿等配色。挑选时，也别忘了确认键盘版本、实际重量与专业课程所需软件的适配情况。','不妨把常用的软件清单带到门店，现场体验手感、屏幕与日常操作，再选适合自己的那一台。'];
  }
  function deliveryText() {
    return draft.platform==='poster' ? '新的学期，轻巧出发。\n\nHUAWEI MateBook 14（鸿蒙版）\n带上你的软件清单，来店里试一试。' : title()+'\n\n'+paragraphs().join('\n\n');
  }

  function brief() {
    return `<section class="page narrow brief-page"><div class="page-heading"><h1>创作简报</h1></div>
      <form id="brief-form"><div class="composer">
        <label class="visually-hidden" for="brief-prompt">创作需求</label>
        <textarea id="brief-prompt" name="prompt" placeholder="描述你的创作需求…" rows="4">${escape(draft.prompt)}</textarea>
        <div class="composer-controls"><div class="composer-options">
          ${plainSelect('发布平台','platform',platformOptions())}
          ${plainSelect('电脑型号','model',`<option value="auto"${draft.model==='auto'?' selected':''}>自动推荐型号</option><option value="14"${draft.model==='14'?' selected':''}>MateBook 14 鸿蒙版</option>`)}
        </div><button class="button primary" type="submit">开始创作 ${icon('arrow')}</button></div>
      </div><p class="form-error" role="alert"${state.error?'':' hidden'}>${escape(state.error)}</p>
      <div class="brief-support"><button type="button" class="text-button" data-action="presets">试试示例</button>
        <details class="preferences"${state.preferences?' open':''}><summary>更多设置 ${icon('plus')}</summary><div class="preference-fields">
          <label>表达语气<select name="tone">${['自然分享','直接介绍','克制表达'].map(t=>`<option${draft.tone===t?' selected':''}>${t}</option>`).join('')}</select></label>
          <label>希望读者做什么<input name="goal" value="${escape(draft.goal)}" placeholder="例如：到店体验"></label>
          <label>额外限制<input name="constraints" value="${escape(draft.constraints)}" placeholder="选填"></label>
          <label>创作档位<select name="speed"><option value="quality"${draft.speed==='quality'?' selected':''}>质量优先</option><option value="fast"${draft.speed==='fast'?' selected':''}>快速创作</option></select></label>
        </div></details></div></form></section>`;
  }

  function process() {
    const current = stages[state.stage];
    const completed = state.stage===4;
    return `<section class="page narrow process-page">
      <div class="process-heading${state.playing?'':' is-paused'}${completed?' is-complete':''}" role="status"><span class="process-spinner" aria-hidden="true">${completed?icon('check'):''}</span><h1>${current.title}</h1></div>
      <p class="page-description">${current.description}</p>
      <div class="progress-meter" role="progressbar" aria-label="演示创作进度" aria-valuemin="0" aria-valuemax="5" aria-valuenow="${state.stage+1}"><div class="progress-fill" style="width:${(state.stage+1)*20}%"></div></div>
      <div class="process-meta"><span>${state.stage+1} / 5</span><button type="button" data-action="play">${state.playing?'暂停演示':completed?'重新演示':'播放演示'}</button></div>
      <details class="process-details"${state.processDetails?' open':''}><summary>查看过程 ${icon('chevron')}</summary><ol>
        ${stages.map((stage,index)=>`<li class="${index<state.stage?'is-done':index===state.stage?'is-active':''}"><span class="step-mark">${index<state.stage?icon('check'):index+1}</span><button type="button" data-stage="${index}" aria-expanded="${state.inspected===index}">${stage.name}</button><span class="step-state">${index<state.stage?'已完成':index===state.stage?(completed?'已完成':'当前环节'):'待处理'}</span></li>${state.inspected===index?`<div class="step-notes">${stage.detail}</div>`:''}`).join('')}
      </ol></details><div class="process-bottom"><span>演示进度 · 示例任务</span><button type="button" class="text-button" data-page="work">查看作品 ${icon('arrow')}</button></div>
    </section>`;
  }

  function preview() {
    if (draft.platform==='poster') return `<article class="poster-sheet"><div class="poster-model">HUAWEI MateBook 14 · 鸿蒙版</div><h2>新的学期，<br>轻巧出发。</h2>${productImage()}<p>带上你的软件清单，来店里试一试。</p><small>海报排版示例</small></article>`;
    return `<article class="content-preview post-${draft.platform} device-${state.device}">
      <figure class="product-figure">${productImage()}<figcaption class="image-controls"><button type="button" data-action="prev-image" aria-label="上一张配图">${icon('chevron')}</button><span>${state.image+1} / 3</span><button type="button" data-action="next-image" aria-label="下一张配图">${icon('chevron')}</button></figcaption></figure>
      <div class="post-copy"><div class="post-byline">华为 PC 门店 · 示例稿</div><h2>${title()}</h2>${paragraphs().map((text,index)=>`<p>${text}${index===1?'<button type="button" class="citation" data-citation="1" aria-label="查看配色来源">[1]</button>':''}</p>`).join('')}<div class="post-tags">#开学装备 &nbsp; #华为电脑 &nbsp; #校园日常</div></div>
    </article>`;
  }

  function work() {
    return `<section class="page wide work-page"><div class="page-heading work-heading"><div><h1>图文作品</h1><div class="work-meta">
      ${plainSelect('作品平台','platform',platformOptions())}
      ${plainSelect('预览设备','device',`<option value="desktop"${state.device==='desktop'?' selected':''}>电脑预览</option><option value="mobile"${state.device==='mobile'?' selected':''}>手机预览</option>`)}
      </div></div><div class="work-actions"><button type="button" class="text-button" data-action="refine">修改</button>${button(`${icon('copy')}复制`,'copy')}${button('导出','export',true)}</div></div>
      ${preview()}<div class="work-bottom"><div><span class="pending-label">1 项待确认</span><button class="text-button" type="button" data-page="evidence">查看依据 ${icon('chevron')}</button></div>${state.refined?'<button type="button" class="text-button" data-action="undo">撤销修改</button>':'<span class="version-note">示例图文</span>'}</div>
    </section>`;
  }

  function evidence() {
    return `<section class="page narrow evidence-page"><div class="page-heading"><div><h1>事实核验</h1><p class="page-description">2 条有来源，1 条待确认。</p></div><button type="button" class="text-button" data-page="work">返回作品 ${icon('arrow')}</button></div>
      <div class="fact-list">${facts.map((fact,index)=>`<article class="fact-item"><button type="button" class="fact-toggle" data-fact="${index}" aria-expanded="${state.fact===index}" aria-controls="fact-body-${index}"><span class="fact-main"><span class="fact-category">${fact.category}</span><span class="fact-title">${fact.title}</span></span><span class="fact-status${fact.pending?' pending':''}">${fact.pending?'待确认':'有来源'}</span>${icon('chevron')}</button>
        <div class="fact-body" id="fact-body-${index}"${state.fact===index?'':' hidden'}><div class="fact-path">产品参数库 / HUAWEI MateBook 14 / ${fact.file}</div><blockquote>${fact.quote}</blockquote><p>${fact.note}</p>${index===1?`<img class="fact-source-image" src="${images[0]}" alt="原野绿登记产品图">`:''}</div></article>`).join('')}</div><p class="evidence-footnote">示例来源，供视觉与交互预览。</p>
    </section>`;
  }

  function saveDraft() {
    try { localStorage.setItem('huazhang-minimal-draft-v1',JSON.stringify(draft)); } catch (_) { /* In-memory state is still preserved. */ }
  }
  function render() {
    const main = $('#app');
    const focus = main.contains(document.activeElement) ? document.activeElement : null;
    const attribute = focus ? ['name','data-stage','data-fact','data-action'].find(key=>focus.hasAttribute(key)) : null;
    const value = attribute ? focus.getAttribute(attribute) : null;
    main.innerHTML = ({brief,process,work,evidence}[state.page])();
    document.querySelectorAll('.site-header [data-page]').forEach(button=>button.setAttribute('aria-current',button.dataset.page===state.page?'page':'false'));
    if (attribute) main.querySelector(`[${attribute}="${value}"]`)?.focus({preventScroll:true});
    history.replaceState(null,'',`#s=${state.page}`);
  }
  function pause() { clearInterval(timer); state.playing=false; }
  function navigate(page) {
    pause(); state.page=page; render();
    window.scrollTo({top:0,behavior:'instant'}); $('#app').focus({preventScroll:true});
  }
  function notify(text) {
    const toast=$('#review-toast');clearTimeout(toastTimer);toast.textContent=text;toast.hidden=false;
    toastTimer=setTimeout(()=>toast.hidden=true,2600);
  }
  function playback(restart = false) {
    if (state.playing) {pause();render();return;}
    if (restart || state.stage===4) state.stage=0;
    state.playing=true;render();
    timer=setInterval(()=>{
      state.stage=Math.min(4,state.stage+1);
      if(state.stage===4) pause();
      render();
    },1600);
  }
  function generate() {
    if (!draft.prompt.trim()) {
      state.error='请先写下创作需求，或选择一个示例。';
      render();$('#brief-prompt').focus();return;
    }
    state.error='';navigate('process');playback(true);
  }
  function openDialog(title,content) {
    $('#dialog-title').textContent=title;$('#dialog-content').innerHTML=content;$('#review-dialog').showModal();
  }
  function presetsDialog() {
    openDialog('选择一个示例',`<div class="preset-list">${presets.map((preset,index)=>`<button type="button" data-preset="${index}"><div><strong>${preset.title}</strong><p>${preset.description}</p></div>${icon('arrow')}</button>`).join('')}</div>`);
  }
  function refineDialog() {
    state.refineChoice=state.refineKind;
    openDialog('修改文案',`<div class="refine-choices" role="group" aria-label="示例改写方向"><button type="button" data-refine-kind="tone" aria-pressed="${state.refineChoice==='tone'}">更自然</button><button type="button" data-refine-kind="direct" aria-pressed="${state.refineChoice==='direct'}">更直接</button></div><label class="field-label" for="refine-input">修改想法</label><textarea id="refine-input" name="refineText" rows="3" placeholder="例如：开头更直接一点…">${escape(state.refineText)}</textarea><p class="refine-note">本页预览两种预设的示例改写。</p><div class="dialog-actions">${button('预览修改','apply-refine',true)}</div>`);
  }
  async function copy() {
    try {await navigator.clipboard.writeText(deliveryText());notify('已复制示例文案。');}
    catch (_) {
      openDialog('复制文案',`<p class="copy-explanation">可选中下方文字复制。</p><textarea class="copy-fallback" readonly rows="8">${escape(deliveryText())}</textarea>`);
      $('.copy-fallback').select();
    }
  }
  function download() {
    const url=URL.createObjectURL(new Blob(['视觉原型 · 示例文案\n\n'+deliveryText()],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='华章有据-示例文案.txt';document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);notify('已导出示例文案。');
  }

  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.page){navigate(button.dataset.page);return;}
    if(button.hasAttribute('data-close')){$('#review-dialog').close();return;}
    if(button.hasAttribute('data-preset')){
      draft.prompt=presets[Number(button.dataset.preset)].prompt;state.error='';saveDraft();render();$('#review-dialog').close();$('#brief-prompt').focus();return;
    }
    if(button.hasAttribute('data-fact')){
      const index=Number(button.dataset.fact);state.fact=state.fact===index?null:index;render();return;
    }
    if(button.hasAttribute('data-stage')){
      const index=Number(button.dataset.stage);state.inspected=state.inspected===index?null:index;render();return;
    }
    if(button.hasAttribute('data-citation')){state.fact=Number(button.dataset.citation);navigate('evidence');return;}
    if(button.dataset.refineKind){
      state.refineChoice=button.dataset.refineKind;
      document.querySelectorAll('[data-refine-kind]').forEach(option=>option.setAttribute('aria-pressed',String(option.dataset.refineKind===state.refineChoice)));return;
    }
    switch(button.dataset.action){
      case 'presets':presetsDialog();break;
      case 'play':playback();break;
      case 'refine':refineDialog();break;
      case 'apply-refine':state.refined=true;state.refineKind=state.refineChoice;$('#review-dialog').close();render();notify('已预览示例修改。');break;
      case 'undo':state.refined=false;render();notify('已还原。');break;
      case 'copy':copy();break;
      case 'export':download();break;
      case 'prev-image':state.image=(state.image+2)%3;render();break;
      case 'next-image':state.image=(state.image+1)%3;render();break;
    }
  });
  document.addEventListener('input',event=>{
    if(Object.hasOwn(draft,event.target.name)){draft[event.target.name]=event.target.value;saveDraft();}
    if(event.target.name==='refineText')state.refineText=event.target.value;
    if(event.target.name==='prompt'&&state.error){state.error='';$('.form-error').hidden=true;}
  });
  document.addEventListener('change',event=>{
    if(event.target.name==='platform'){
      draft.platform=event.target.value;saveDraft();if(state.page==='work')render();
    }
    if(event.target.name==='device'){state.device=event.target.value;render();}
  });
  document.addEventListener('toggle',event=>{
    if(event.target.matches?.('.preferences'))state.preferences=event.target.open;
    if(event.target.matches?.('.process-details'))state.processDetails=event.target.open;
  },true);
  document.addEventListener('submit',event=>{if(event.target.id==='brief-form'){event.preventDefault();generate();}});
  $('#review-dialog').addEventListener('click',event=>{
    if(event.target!==$('#review-dialog'))return;
    const box=event.target.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)event.target.close();
  });
  function readHash(){const page=new URLSearchParams(location.hash.slice(1)).get('s');if(Object.hasOwn(pageNames,page))state.page=page;}
  window.addEventListener('hashchange',()=>{pause();readHash();render();});
  readHash();render();
})();
