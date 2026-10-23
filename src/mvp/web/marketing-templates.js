(() => {
  'use strict';
  const $ = id => document.getElementById(id), el = (...args) => UI.el(...args);
  let host, select, demo, subject, title, source, checked, pending, catalog = [];
  const defaults = () => ({marketing_template: 'auto', demo_mode: false, concept_subject: '', topic_context: {title: '', source: '', checked_on: ''}});
  function read() {
    if (!host || $('prompt-variant')?.value !== 'differentiated') return defaults();
    return {marketing_template: select.value, demo_mode: demo.checked, concept_subject: subject.value.trim(),
      topic_context: {title: title.value.trim(), source: source.value.trim(), checked_on: checked.value}};
  }
  function restore(task) {
    if (!host) return;
    pending = task;
    select.value = task.marketing_template || 'auto'; demo.checked = Boolean(task.demo_mode);
    subject.value = task.concept_subject || ''; title.value = task.topic_context?.title || '';
    source.value = task.topic_context?.source || ''; checked.value = task.topic_context?.checked_on || ''; update();
  }
  function update() {
    host.hidden = $('prompt-variant')?.value !== 'differentiated';
    const platform = $('platform')?.value;
    [...select.options].forEach(o => { const t = catalog.find(x => x.id === o.value); o.disabled = Boolean(t && !t.platforms.includes(platform)); });
    if (select.selectedOptions[0]?.disabled) select.value = 'auto';
    const t = catalog.find(x => x.id === select.value);
    $('template-choice-note').textContent = t ? `${t.user_note || t.title}。${t.demo ? '此样板需要概念演示。' : ''}` : 'bot 只从你审核通过且当前资料可支持的样板中选择；结果可查看依据与槽位。';
    $('concept-subject-group').hidden = !demo.checked;
  }
  async function init() {
    const variant = $('prompt-variant'); if (!variant) return;
    host = el('section', {id: 'marketing-template-options', class: 'template-options'});
    select = el('select', {id: 'marketing-template', 'aria-label': '已审核营销样板'}, el('option', {value: 'auto'}, '自动匹配已审核样板'));
    demo = el('input', {type: 'checkbox', id: 'concept-demo'});
    subject = el('input', {id: 'concept-subject', maxLength: 80, placeholder: '例如：拟议的品牌或原创 IP；不代表真实合作'});
    title = el('input', {maxLength: 160, placeholder: '文化现象或社会议题', 'aria-label': '议题名称'});
    source = el('input', {type: 'url', maxLength: 600, placeholder: '议题来源链接', 'aria-label': '议题来源'});
    checked = el('input', {type: 'date', 'aria-label': '议题核对日期'});
    host.append(el('label', {for: 'marketing-template'}, '营销样板'), select,
      el('p', {id: 'template-choice-note', class: 'dialog-copy'}),
      el('label', {class: 'template-demo-toggle'}, demo, '概念演示（虚构资料、角色或联动会保留醒目标识）'),
      el('p', {class: 'dialog-copy'}, '演示活动使用“春风体验点”等示例资料，独立于真实门店，不写入门店历史；产品参数继续查真实依据。'),
      el('div', {id: 'concept-subject-group', class: 'form-group'}, el('label', {for: 'concept-subject'}, '拟议联动对象（C10 必填）'), subject),
      el('details', {}, el('summary', {}, '议题来源（C15；有效期七天）'), title, source, checked));
    variant.parentElement.after(host);
    variant.addEventListener('change', update); $('platform')?.addEventListener('change', update);
    host.addEventListener('input', () => { update(); pending = read(); sessionStorage.setItem('marketing-template-preferences', JSON.stringify(pending)); });
    update();
    try {
      const response = await fetch('/api/info'); if (!response.ok) throw new Error('样板读取失败');
      const info = await response.json(); catalog = info.marketing_templates?.templates || [];
      catalog.forEach(t => select.append(el('option', {value: t.id}, `${t.id} · ${t.format}`)));
      const saved = sessionStorage.getItem('marketing-template-preferences');
      if (pending) restore(pending); else if (saved) restore(JSON.parse(saved));
      update();
    } catch { $('template-choice-note').textContent = '样板选项未载入；可以稍后重开页面。'; }
  }
  function showResult(r) {
    const t = r.planning?.template || r.marketing_template; if (!t || !document.querySelector('#dbg-judge .dbg-content')) return;
    const d = el('details', {class: 'template-result'}, el('summary', {}, `模仿样板 ${t.id} · ${t.title}`));
    const pair = t.product_pair || {};
    d.append(el('p', {}, `${t.selection_source}：${t.reason || '按任务与可用素材匹配'}`),
      el('p', {}, `对标华为型号：${pair.model_name || '未记录'}；场景：${pair.scene || '未记录'}`),
      el('p', {}, `预制样例：${t.fallback_url || '当前不可用'}。${pair.fallback_note || ''}`),
      el('p', {}, `你的审核备注：${t.user_note || '未附备注'}`),
      el('ol', {}, ...t.pattern.map(s => el('li', {}, s))),
      el('a', {href: t.source, target: '_blank', rel: 'noopener noreferrer'}, '查看原案例 ↗'));
    (t.filled_slots || []).forEach(s => d.append(el('p', {}, `${s.slot}：${s.text || '按样板结构展开'}${s.refs?.length ? '（'+s.refs.join('、')+'）' : ''}`)));
    document.querySelector('#dbg-judge .dbg-content').append(d);
  }
  window.MarketingTemplates = {init, read, restore, showResult};
})();
