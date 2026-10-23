(function () {
  'use strict';
  let activeStore = sessionStorage.getItem('creative-store') || 'default';
  const $ = id => document.getElementById(id);
  const el = (tag, props, ...kids) => UI.el(tag, props, ...kids);
  const kinds = {fact: '门店信息', service: '服务', stock: '库存', activity: '活动', customer_question: '真实问题记录', photo_note: '照片文字说明（未看图）'};
  async function request(url, options) {
    const r = await fetch(url, options);
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '保存失败，请核对来源、日期和资料长度');
    return data;
  }
  function status(message) { $('context-status').textContent = message; }
  function itemRow(item = {}) {
    const row = el('fieldset', {class: 'context-item'});
    const select = el('select', {'aria-label': '资料类型'});
    Object.entries(kinds).forEach(([value, label]) => select.append(el('option', {value}, label)));
    select.value = item.kind || 'fact';
    const text = el('textarea', {rows: 2, maxLength: 800, placeholder: '真实内容；产品参数仍须来自产品资料', 'aria-label': '资料内容'});
    text.value = item.text || '';
    const source = el('input', {maxLength: 200, placeholder: '确认来源，例如负责人姓名或记录编号', 'aria-label': '确认来源'});
    source.value = item.source || '';
    const confirmedOn = el('input', {type: 'date', 'aria-label': '确认日期'});
    confirmedOn.value = item.confirmed_on || '';
    const expiresOn = el('input', {type: 'date', 'aria-label': '有效截止日期'});
    expiresOn.value = item.expires_on || '';
    const confirmed = el('input', {type: 'checkbox', checked: Boolean(item.confirmed)});
    const remove = el('button', {type: 'button', class: 'text-button', onclick: () => row.remove()}, '移除此条');
    row.append(select, text, source, el('label', {}, '确认日期', confirmedOn), el('label', {}, '有效截止（库存、活动必填）', expiresOn), el('label', {}, confirmed, '我已核对来源与内容'), remove);
    row.read = () => ({kind: select.value, text: text.value.trim(), source: source.value.trim(), confirmed: confirmed.checked,
      confirmed_on: confirmedOn.value || null, expires_on: expiresOn.value || null});
    $('context-items').append(row);
  }
  function publicationButton(history, sid) {
    let published = history.published;
    const button = el('button', {type: 'button', class: 'text-button'}, published ? '已发布 · 撤回标记' : '手动标记已发布');
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await request(`/api/context/${encodeURIComponent(sid)}/history/${encodeURIComponent(history.job_id)}/publication`,
          {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({published: !published})});
        published = !published;
        button.textContent = published ? '已发布 · 撤回标记' : '手动标记已发布';
      } catch (e) { status(e.message); } finally { button.disabled = false; }
    });
    return button;
  }
  async function load() {
    const sid = $('context-store').value.trim();
    const data = await request(`/api/context/${encodeURIComponent(sid)}`);
    activeStore = sid;
    sessionStorage.setItem('creative-store', sid);
    ['name', 'audience', 'tone'].forEach(key => { $(`context-${key}`).value = data.profile[key] || ''; });
    $('context-items').replaceChildren();
    data.profile.items.forEach(itemRow);
    $('context-history').replaceChildren();
    data.history.forEach(h => $('context-history').append(el('div', {class: 'context-history-row'},
      el('b', {}, h.title), el('small', {}, `${h.platform} · ${h.review_state} · ${h.origin}`), publicationButton(h, sid))));
    if (!data.history.length) $('context-history').textContent = '还没有生成稿件。';
    status(`已载入 ${sid}：有效资料 ${data.context.confirmed_items.length} 条，待确认或过期 ${data.context.unavailable_items.length} 条。`);
    window.dispatchEvent(new CustomEvent('store-context-updated'));
  }
  function init() {
    if (!$('open-context')) return;
    $('open-context').addEventListener('click', async () => {
      $('context-store').value = activeStore;
      $('context-dialog').showModal();
      try { await load(); } catch (e) { status(e.message); }
    });
    $('load-context').addEventListener('click', () => load().catch(e => status(e.message)));
    $('add-context-item').addEventListener('click', () => itemRow());
    $('save-context').addEventListener('click', async () => {
      const button = $('save-context');
      button.disabled = true;
      try {
        if ($('context-store').value.trim() !== activeStore) throw new Error('请先载入该门店，再编辑保存。');
        const profile = Object.fromEntries(['name', 'audience', 'tone'].map(k => [k, $(`context-${k}`).value.trim()]));
        profile.items = Array.from($('context-items').children).map(r => r.read()).filter(r => r.text);
        await request(`/api/context/${encodeURIComponent(activeStore)}`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(profile)});
        await load();
        status('已保存。后续创作将载入这些资料；已有稿件保留生成时的资料快照。');
      } catch (e) { status(e.message); } finally { button.disabled = false; }
    });
  }
  function showResult(r) {
    const box = $('creative-summary');
    if (!box) return;
    box.replaceChildren();
    if (!r.article) return;
    if (r.prompt_version) box.append(el('p', {}, `提示词：${r.prompt_version.label} · ${r.prompt_version.digest}`));
    const ctx = r.creative_context || {};
    const details = el('details', {}, el('summary', {}, '本次差异化依据与历史重合'));
    details.append(el('p', {}, `${ctx.store?.name || ctx.store_id || '未登记门店'} · 可用资料 ${ctx.confirmed_items?.length || 0} 条 · 选用 ${(r.planning?.context_ids || []).join('、') || '无'} · 结构：${r.planning?.format || '未记录'}`));
    if (r.planning?.avoidance?.length) details.append(el('p', {}, r.planning.avoidance.join('；')));
    const sim = r.similarity;
    details.append(el('p', {}, sim ? `对照近期 ${sim.compared} 篇，发现 ${sim.matches.length} 处字面重合；证据原句另列 ${sim.fact_matches.length} 处。此项不是原创率。` : '旧稿未运行历史检查。'));
    (sim?.matches || []).forEach(m => details.append(el('p', {}, `${m.where}#${m.index} 与《${m.title}》重合：${m.overlap}`)));
    const publication = el('span', {}, '正在读取发布标记…');
    if (r.job_id) details.append(publication);
    const alternative = (r.planning?.angles || []).find(a => a.id !== r.planning.selected_angle);
    if (alternative) details.append(el('button', {type: 'button', class: 'text-button', onclick: () => {
      $('instr').value = `改用这个明显不同的切入点：${alternative.title}。${alternative.reason || ''}。保留事实与条件，默认只交付一份成稿。`;
      $('instr').dispatchEvent(new Event('input', {bubbles: true}));
      $('instr').focus();
    }}, `${alternative.needs_new_evidence ? '重新策划角度' : '换角度'}：${alternative.title}`));
    box.append(details);
    if (r.job_id) request(`/api/context/${encodeURIComponent(r.task?.store_id || 'default')}/history/${encodeURIComponent(r.job_id)}`).then(h => {
      publication.replaceWith(publicationButton(h, r.task?.store_id || 'default'));
    }).catch(() => { publication.textContent = '该稿尚无独立历史记录'; });
  }
  window.CreativeContext = {init, showResult, storeId: () => activeStore};
})();
