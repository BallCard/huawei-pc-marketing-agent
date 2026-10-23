(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (...args) => UI.el(...args);
  let timer, busy = false, generation = 0;
  async function api(url, body) {
    const r = await fetch(url, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '对照请求未完成，请检查简报。');
    return data;
  }
  function status(message) { $('compare-status').textContent = message; }
  function lock(value) {
    busy = value;
    $('compare-prompts').disabled = value;
    $('go').disabled = value;
    if ($('redo')) $('redo').disabled = value;
  }
  function render(data) {
    const body = $('compare-body');
    body.replaceChildren();
    body.append(el('p', {}, data.scope || ''));
    if (data.shared?.digest) body.append(el('p', {}, `共同输入 ${data.shared.digest} · 写作模型 ${data.shared.writer_model} · 审核模型 ${data.shared.judge_model} · 结构 ${data.shared.planning?.format || '未记录'}`));
    if (data.variants?.preparation) {
      body.append(el('p', {}, `尚未生成对照：${data.variants.preparation.error || (data.variants.preparation.questions || []).map(q => typeof q === 'string' ? q : q.text || q.question || JSON.stringify(q)).join('；') || '需求尚未明确'}`));
    }
    const grid = el('div', {class: 'compare-grid'});
    ['baseline', 'differentiated'].forEach(key => {
      const result = data.variants?.[key];
      if (!result) return;
      const col = el('section', {class: 'compare-column'});
      col.append(el('h3', {}, result.prompt_version.label));
      col.append(el('small', {}, `${result.prompt_version.digest} · ${(result.total_ms / 1000).toFixed(1)} 秒`));
      if (result.article) {
        const a = result.article;
        (a.disclosures || []).forEach(label => col.append(el('p', {class: 'concept-disclosure'}, label)));
        col.append(el('h4', {}, a.title), el('p', {}, a.lead));
        (a.blocks || []).forEach(b => col.append(el('p', {class: b.type === 'image' ? 'compare-caption' : ''}, b.type === 'text' ? b.text : `[配图] ${b.caption || b.image_id}`)));
        col.append(el('p', {}, a.cta), el('p', {}, (a.tags || []).join(' ')));
        col.append(el('b', {}, `${result.chars} 字 · ${result.verification?.state === 'passed' ? '审核通过' : '待复核'}`));
        (result.verification?.remaining || []).forEach(v => col.append(el('p', {class: 'compare-issue'}, v)));
        col.append(el('p', {}, `近期历史字面重合 ${result.similarity?.matches.length || 0} 处；不代表原创率或语义差异。`));
      }
      if (result.error) col.append(el('p', {class: 'compare-issue'}, result.error));
      grid.append(col);
    });
    body.append(grid);
    const facts = el('details', {}, el('summary', {}, '查看双方共同事实与策划'));
    facts.append(el('pre', {}, JSON.stringify(data.shared?.planning || {}, null, 2)));
    body.append(facts, el('p', {}, '此处对照首次写作输出；未自动修订，不生成海报，不自动记入门店历史。单组结果受采样影响，不能证明新版稳定更好。'));
    if (data.prompt_snapshots) {
      const snapshots = el('details', {}, el('summary', {}, '查看生成这两篇时的提示词快照'));
      const texts = el('div', {class: 'compare-grid'});
      Object.entries(data.prompt_snapshots).forEach(([id, steps]) => {
        const col = el('div', {class: 'compare-column'}, el('h3', {}, data.prompt_versions[id].label));
        Object.entries(steps).forEach(([name, text]) => col.append(el('details', {}, el('summary', {}, name + '.md'), el('pre', {}, text))));
        texts.append(col);
      });
      snapshots.append(texts); body.append(snapshots);
    }
    const save = el('button', {type: 'button', class: 'text-button'}, '下载对照结果 JSON');
    save.addEventListener('click', () => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
      const a = el('a', {href: url, download: 'prompt-comparison.json'}); a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    body.append(save);
  }
  async function poll(jid, token, failures = 0) {
    if (token !== generation) return;
    try {
      const job = await api(`/api/job/${encodeURIComponent(jid)}`);
      if (token !== generation) return;
      if (job.state === 'done') {
        render(job.result); status('对照完成，审核疑点与失败结果均保留。'); lock(false);
        sessionStorage.removeItem('prompt-comparison-active');
        sessionStorage.setItem('prompt-comparison-last', jid);
        return;
      }
      if (job.state === 'error') {
        status(job.error || '对照任务出错'); lock(false);
        sessionStorage.removeItem('prompt-comparison-active');
        return;
      }
      const running = (job.steps || []).find(s => s.status === 'running');
      status(running?.label || '正在准备共同输入…');
      timer = setTimeout(() => poll(jid, token), 1500);
    } catch (e) {
      status(e.message);
      if (failures < 3) timer = setTimeout(() => poll(jid, token, failures + 1), 2500);
      else { lock(false); status(e.message + '。刷新页面可恢复任务。'); }
    }
  }
  async function prompts() {
    const box = $('compare-prompt-texts');
    if (box.childNodes.length) return;
    try {
      const versions = await Promise.all(['baseline', 'differentiated'].map(v => api('/api/prompts/' + v)));
      const grid = el('div', {class: 'compare-grid'});
      versions.forEach(v => {
        const col = el('div', {class: 'compare-column'}, el('h3', {}, v.version.label));
        Object.entries(v.steps).forEach(([name, text]) => col.append(el('details', {}, el('summary', {}, name + '.md'), el('pre', {}, text))));
        grid.append(col);
      });
      box.append(grid);
    } catch (e) { status(e.message); }
  }
  function init(readTask) {
    if (!$('compare-prompts')) return;
    $('compare-prompts').addEventListener('click', async () => {
      if (busy || $('go').disabled) return;
      $('compare-dialog').showModal();
      prompts();
      $('compare-body').replaceChildren();
      lock(true); status('正在固定门店资料与共同输入…');
      try {
        const data = await api('/api/compare', readTask());
        sessionStorage.setItem('prompt-comparison-active', data.job);
        clearTimeout(timer); poll(data.job, ++generation);
      } catch (e) { status(e.message); lock(false); }
    });
    $('view-prompts').addEventListener('click', async () => {
      $('compare-dialog').showModal(); await prompts();
      const jid = sessionStorage.getItem('prompt-comparison-last');
      if (jid && !busy) try { render((await api('/api/job/' + encodeURIComponent(jid))).result); } catch (e) { status(e.message); }
    });
    const active = sessionStorage.getItem('prompt-comparison-active');
    if (active) { lock(true); $('compare-dialog').showModal(); poll(active, ++generation); }
  }
  function show(data) {
    $('compare-dialog').showModal(); render(data); prompts();
    status('已载入保存的对照结果。');
  }
  window.PromptCompare = {init, show};
})();
