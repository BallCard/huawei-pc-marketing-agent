(function () {
  'use strict';

  const STAGES = [
    { id: 'scene', title: '场景解析', kind: 'llm', note: '规则先验 × 模型推理，得到需求维度权重' },
    { id: 'model', title: '确定型号', kind: 'llm', note: '指定则校验；留空则按画像从知识库推荐' },
    { id: 'strategy', title: '平台策略', kind: 'rule', note: '平台策略表：结构 / 字数 / 图数 / 价格政策' },
    { id: 'retrieve', title: '知识库检索', kind: 'code', note: '读取该型号的事实片段与登记图片；图片按画面类型排序' },
    { id: 'extract', title: '事实点提取', kind: 'llm', note: '按画像权重从片段中选出可引用的事实' },
    { id: 'compose', title: '图文编排', kind: 'llm', note: '按平台版式写稿并选图（首图必须含整机）' },
    { id: 'verify', title: '确定性核验', kind: 'rule', note: '数字 / 型号 / 图片 / 价格 / 合规规则表，不调用模型；未过则修订' },
    { id: 'judge', title: '独立审核', kind: 'llm', note: '另一套提示词审终稿，意见交给人确认，不自动重写' }
  ];

  const KIND_LABELS = { llm: 'LLM', rule: '规则', code: '代码' };
  const STATUS_LABELS = { done: '完成', running: '执行中', error: '异常', wait: '等待', skip: '未执行' };
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function svgNode(tag, attrs) {
    const n = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  // 机器人图标：每个环节都是 Agent 流水线上的一个节点
  function botIcon() {
    const svg = svgNode('svg', {
      viewBox: '0 0 24 24', class: 'ft-bot', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor',
      'stroke-width': '1.6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'
    });
    svg.appendChild(svgNode('path', { d: 'M12 5.2V3.4' }));
    svg.appendChild(svgNode('circle', { cx: '12', cy: '2.6', r: '1.1', fill: 'currentColor', stroke: 'none' }));
    svg.appendChild(svgNode('rect', { x: '3.8', y: '5.2', width: '16.4', height: '12.4', rx: '3.2' }));
    svg.appendChild(svgNode('circle', { cx: '9', cy: '11.2', r: '1.35', fill: 'currentColor', stroke: 'none' }));
    svg.appendChild(svgNode('circle', { cx: '15', cy: '11.2', r: '1.35', fill: 'currentColor', stroke: 'none' }));
    svg.appendChild(svgNode('path', { d: 'M9.4 14.6h5.2' }));
    svg.appendChild(svgNode('path', { d: 'M1.8 10.5v3.4M22.2 10.5v3.4' }));
    return svg;
  }

  function buildFlow(steps, running) {
    const UI = window.UI;
    const safeSteps = Array.isArray(steps) ? steps : [];
    const root = UI.el('div', { class: 'flow flow-v' });

    if (safeSteps.length === 0 && !running) {
      root.appendChild(UI.el('div', { class: 'muted small', style: 'padding: 12px 4px;' }, '尚未运行'));
      root.summary = '尚未运行';
      return root;
    }

    root.appendChild(UI.el('div', { class: 'flow-legend' },
      UI.el('span', { class: 'lg k-llm', text: 'LLM 推理' }),
      UI.el('span', { class: 'lg k-rule', text: '确定性规则' }),
      UI.el('span', { class: 'lg k-code', text: '本地代码' }),
      UI.el('span', { class: 'lg-hint', text: '点任一环节展开该步输入输出' })
    ));

    const map = {};
    let totalMs = 0;
    for (const st of STAGES) map[st.id] = { stage: st, steps: [], totalMs: 0, repairCount: 0, status: 'skip' };

    for (const item of safeSteps) {
      const key = item.step === 'repair' ? 'verify' : item.step;
      const target = map[key];
      if (!target) continue;
      target.steps.push(item);
      if (typeof item.ms === 'number' && item.ms > 0) {
        target.totalMs += item.ms;
        totalMs += item.ms;
      }
      if (item.step === 'repair') target.repairCount += 1;
    }

    let foundRunning = false;
    STAGES.forEach((st, i) => {
      const data = map[st.id];
      if (data.steps.length) {
        if (data.steps.some((s) => s.status === 'error')) data.status = 'error';
        else if (data.steps.some((s) => s.status === 'running')) { data.status = 'running'; foundRunning = true; }
        else data.status = 'done';
      } else if (running) {
        if (!foundRunning && i > 0 && map[STAGES[i - 1].id].status === 'done') {
          data.status = 'running';
          foundRunning = true;
        } else data.status = 'wait';
      } else data.status = 'skip';
    });

    let slowestId = null;
    let slowestMs = 0;
    for (const st of STAGES) {
      if (map[st.id].totalMs > slowestMs) { slowestMs = map[st.id].totalMs; slowestId = st.id; }
    }

    const list = UI.el('ol', { class: 'ftl' });
    let openRow = null;

    STAGES.forEach((st, i) => {
      const data = map[st.id];
      const isSlow = Boolean(slowestId === st.id && slowestMs > 0);
      const pct = totalMs > 0 && data.totalMs > 0 ? Math.max(3, Math.min(100, Math.round((data.totalMs / totalMs) * 100))) : 0;
      const item = UI.el('li', { class: `ftl-item ${data.status} k-${st.kind}` + (isSlow ? ' slow' : '') });

      // 左侧轨道：bot 图标 + 连接线
      const rail = UI.el('div', { class: 'ftl-rail' });
      const icon = UI.el('span', { class: 'ftl-icon', title: `${st.title} · ${STATUS_LABELS[data.status] || data.status}` });
      icon.appendChild(botIcon());
      rail.appendChild(icon);
      if (i < STAGES.length - 1) rail.appendChild(UI.el('span', { class: 'ftl-line', 'aria-hidden': 'true' }));
      item.appendChild(rail);

      // 右侧主体
      const main = UI.el('div', { class: 'ftl-main' });
      const head = UI.el('button', {
        type: 'button', class: 'ftl-head', 'aria-expanded': 'false',
        'aria-label': `${st.title}，状态：${STATUS_LABELS[data.status] || data.status}，耗时：${UI.fmtMs(data.totalMs)}`
      });
      head.appendChild(UI.el('b', { class: 'ftl-title', text: `${i + 1}. ${st.title}` }));
      head.appendChild(UI.el('span', { class: `ftl-kind k-${st.kind}`, text: KIND_LABELS[st.kind] || st.kind }));
      if (isSlow) head.appendChild(UI.el('span', { class: 'ftl-slow', text: '最慢' }));
      head.appendChild(UI.el('span', { class: 'ftl-status ' + data.status, text: STATUS_LABELS[data.status] || data.status }));
      const cacheHit = data.steps.some((s) => s.detail && s.detail.cache_hit === true);
      const timeText = data.totalMs > 0
        ? UI.fmtMs(data.totalMs)
        : data.steps.length
          ? (cacheHit ? '缓存' : '即时')
          : '—';
      head.appendChild(UI.el('span', { class: 'ftl-ms mono', text: timeText }));
      head.appendChild(UI.el('span', { class: 'ftl-caret', text: '▾', 'aria-hidden': 'true' }));
      main.appendChild(head);

      main.appendChild(UI.el('div', { class: 'ftl-note muted small', text: st.note }));

      if (data.totalMs > 0) {
        const bar = UI.el('div', { class: 'ftl-bar', title: `占本次总耗时 ${pct}%` });
        const fill = UI.el('u');
        fill.style.width = pct + '%';
        bar.appendChild(fill);
        main.appendChild(bar);
      }
      if (data.repairCount > 0) {
        main.appendChild(UI.el('span', { class: 'ftl-loop', text: `↺ 修订 ${data.repairCount} 次` }));
      }

      const detail = UI.el('div', { class: 'ftl-detail', hidden: true });
      renderDetail(UI, detail, st, data);
      main.appendChild(detail);
      item.appendChild(main);

      head.addEventListener('click', () => {
        const same = openRow === item;
        if (openRow) {
          openRow.classList.remove('open');
          openRow.querySelector('.ftl-head').setAttribute('aria-expanded', 'false');
          openRow.querySelector('.ftl-detail').hidden = true;
        }
        openRow = same ? null : item;
        if (!same) {
          item.classList.add('open');
          head.setAttribute('aria-expanded', 'true');
          detail.hidden = false;
        }
      });

      list.appendChild(item);
    });

    root.appendChild(list);

    let summary = `${safeSteps.length} 步 · 共 ${UI.fmtMs(totalMs)}`;
    if (slowestId && slowestMs > 0) {
      const s = STAGES.find((x) => x.id === slowestId);
      if (s) summary += ` · 最慢：${s.title} ${UI.fmtMs(slowestMs)}`;
    }
    root.summary = summary;
    return root;
  }

  function renderDetail(UI, box, stage, data) {
    if (!data.steps.length) {
      box.appendChild(UI.el('div', { class: 'muted small', text: '本次运行没有走到这一步。' }));
      return;
    }
    data.steps.forEach((stepItem) => {
      const head = UI.el('div', { class: 'ftl-dhead' });
      head.appendChild(UI.el('b', { text: stepItem.label || stage.title }));
      let cls = 'warn';
      let text = stepItem.status || '未知';
      if (stepItem.status === 'done') { cls = 'ok'; text = '完成'; }
      else if (stepItem.status === 'error') { cls = 'bad'; text = '异常'; }
      else if (stepItem.status === 'running') { cls = 'warn'; text = '执行中'; }
      head.appendChild(UI.tag(text, cls));
      head.appendChild(UI.el('span', { class: 'muted small mono', text: UI.fmtMs(stepItem.ms) }));
      box.appendChild(head);
      if (stepItem.detail !== undefined && stepItem.detail !== null) {
        const text = typeof stepItem.detail === 'string' ? stepItem.detail : JSON.stringify(stepItem.detail, null, 1);
        box.appendChild(UI.el('pre', { text }));
      }
    });
  }

  window.buildFlow = buildFlow;
})();
