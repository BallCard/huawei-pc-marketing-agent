// 使用确定的接口快照检查问答交互；真实模型流程另行验证。
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.UI_BASE || 'http://127.0.0.1:7884';
const out = 'data/ui-checks/clarification';
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const report = [];
  try {
    for (const [width, height] of [[320, 568], [390, 844], [1440, 900]]) {
      const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'reduce' });
      const errors = [], requests = [], jobs = new Map();
      page.on('pageerror', e => errors.push(e.message));
      const specs = [
        { id: 'software', field: 'software', question: '主要会用哪些编程或设计软件？',
          options: ['编程开发，如 VS Code、Python', '平面设计，如 Photoshop', 'CAD 或三维建模软件', '还没确定'],
          placeholder: '填写软件名称；有明确版本要求再补充' },
        { id: 'runtime', field: 'system', question: '这些软件需要在 Windows 本机直接运行吗？',
          options: ['必须在本机 Windows 运行', '可以接受云电脑', '暂时不确定，兼容性待确认'] }
      ];
      await page.route('**/api/run', async route => {
        const task = route.request().postDataJSON();
        requests.push(task);
        const round = task.clarify_round || 0;
        const id = String(requests.length).padStart(32, '0');
        const result = round < 2 ? {
          status: 'need_info', task, questions: [specs[round].question], question_specs: [specs[round]],
          // 即使旧接口误带型号，前端也不能把它套到软件题中。
          candidates: ['HUAWEI MateBook 14（鸿蒙版）', 'HUAWEI MateBook Fold 非凡大师'],
          clarification: { round: round + 1, max_rounds: 2 }
        } : {
          status: 'input_required', task, questions: [], question_specs: [],
          message: '现有资料还不能验证软件兼容性，请在简报中明确型号或调整条件。',
          clarification: { round: 2, max_rounds: 2, exhausted: true }
        };
        jobs.set(id, { id, state: 'done', steps: [], artifacts: {}, events: [], result: { ...result, total_ms: 1200 } });
        await route.fulfill({ json: { job: id } });
      });
      await page.route('**/api/job/*', async route => {
        await route.fulfill({ json: jobs.get(route.request().url().split('/').pop()) });
      });
      await page.goto(base);
      if (await page.locator('#enter-studio').isVisible()) await page.locator('#enter-studio').click();
      await page.waitForFunction(() => !document.querySelector('.site-header').inert);
      await page.locator('#go').click();
      await page.locator('#agent-ask').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#agent-ask-progress').innerText(), '第 1 / 2 轮');
      assert.equal(await page.locator('.ask-option').count(), 4);
      assert.ok(!(await page.locator('#agent-ask-options').innerText()).includes('MateBook'));
      assert.equal(await page.locator('#agent-ask-input').getAttribute('list'), null);
      await page.locator('.ask-option').first().click();
      await page.reload();
      await page.locator('.ask-submit').waitFor({ state: 'visible' });
      assert.equal(await page.locator('.ask-answer').innerText(), '编程开发，如 VS Code、Python');
      await page.locator('.ask-submit').click();
      await page.waitForFunction(() => document.querySelector('#agent-ask-progress').textContent === '第 2 / 2 轮');
      assert.equal(requests[1].clarify_round, 1);
      assert.equal(requests[1].clarify_answers[0].field, 'software');
      assert.equal(requests[1].clarify_answers[0].answer, '编程开发，如 VS Code、Python');
      assert.equal(await page.locator('.ask-option').count(), 3);
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#agent-ask-progress').textContent === '第 2 / 2 轮');
      assert.equal(await page.locator('#agent-ask-question').innerText(), specs[1].question);
      const bounds = await page.locator('#agent-ask').boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width && bounds.y >= 0 && bounds.y + bounds.height <= height);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      await page.screenshot({ path: `${out}/round-two-${width}.png` });
      await page.locator('#agent-ask-input').fill('必须在本机 Windows 运行，学校不能联网考试');
      await page.locator('.ask-send').click();
      await page.locator('.ask-submit').click();
      await page.locator('#need').getByRole('heading', { name: '暂时无法确定合适型号', exact: true }).waitFor();
      assert.equal(requests[2].clarify_round, 2);
      assert.equal(requests[2].clarify_answers.length, 2);
      assert.ok(requests[2].extra.includes('学校不能联网考试'));
      assert.equal(await page.locator('#agent-ask').isVisible(), false);
      assert.equal(await page.locator('#agent-ask-pill').isVisible(), false);
      assert.equal(await page.locator('#process-live').innerText(), '暂未生成作品');
      assert.equal(requests.length, 3, '初次提交加两次回答，没有第三轮问询');
      assert.deepEqual(errors, []);
      report.push({ width, height, requests: requests.length, restored: true, errors });
      await page.close();
    }
    fs.writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 2));
    console.log('PASS: 两轮递进、逐题选项、自填、刷新恢复和停止问询；3 种屏幕尺寸');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
