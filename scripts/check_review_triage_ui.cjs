// 用实际后端分流结果验证手机/桌面人工问卷与自动修订入口。
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.UI_BASE || 'http://127.0.0.1:7884';
const out = 'data/ui-checks/review-triage';
fs.mkdirSync(out, {recursive:true});
const fixture = JSON.parse(fs.readFileSync(process.env.REVIEW_FIXTURE || 'tests/fixtures/review_triage.json', 'utf8'));

(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  const report = [];
  try {
    for (const [width,height] of [[320,568],[390,844],[1440,900]]) {
      const page = await browser.newPage({viewport:{width,height}, reducedMotion:'reduce'});
      const errors = [], sent = [];
      page.on('pageerror', e => errors.push(e.message));
      let form = structuredClone(fixture.form);
      const result = {...fixture.result, job_id:'review-fixture'};
      await page.route('**/api/job/review-fixture/review', async route => {
        if (route.request().method() === 'GET') return route.fulfill({json:form});
        sent.push(route.request().postDataJSON());
        await route.fulfill({json:{result,job:null}});
      });
      await page.goto(base);
      if (await page.locator('#enter-studio').isVisible()) await page.locator('#enter-studio').click();
      await page.waitForFunction(() => window.ReviewQuestions && !document.querySelector('.site-header').inert);
      await page.evaluate(r => window.ReviewQuestions.open(r), result);
      await page.getByText('重要未决 · 1 / 1', {exact:true}).waitFor();
      assert.ok((await page.locator('.review-triage').innerText()).includes('需人工确认 1 项'));
      assert.equal(await page.locator('.review-choice').count(), 3);
      await page.getByText('查看涉及的 2 处原文', {exact:true}).click();
      const bounds = await page.locator('#review-dialog').boundingBox();
      assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.x+bounds.width <= width+1 && bounds.y+bounds.height <= height+1);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1), true);
      await page.screenshot({path:`${out}/human-${width}.png`});
      await page.getByText('暂时无法确认', {exact:true}).click();
      await page.locator('#review-next').click();
      assert.equal(await page.locator('#review-next').innerText(), '提交评审结果 →');
      assert.ok((await page.locator('.review-submit-effect').innerText()).includes('1 项继续保留待确认'));
      await page.locator('#review-back').click();
      assert.ok(await page.locator('#review-next').isVisible());
      await page.locator('#review-next').click();
      await page.locator('#review-next').click();
      await page.waitForFunction(() => !document.querySelector('#review-dialog').open);
      assert.equal(sent[0].answers.length, 1);
      assert.equal(sent[0].resolution, 'hold');
      form = {...form, questions:[], automatic_issues:[{type:'model', detail:'型号文字有误，按登记名称修正后复核。', origin:'rules'}],
        summary:{human:0,automatic:1,optional:4,dismissed:3,merged:1}};
      await page.evaluate(r => window.ReviewQuestions.open(r), result);
      await page.getByText('继续处理审核结果', {exact:true}).waitFor();
      assert.ok(!/\bnull\b/.test(await page.locator('#review-question-body').innerText()));
      assert.equal(await page.locator('.review-choice').count(), 0);
      assert.equal(await page.getByRole('button', {name:/人工采用当前稿/}).count(), 0);
      await page.screenshot({path:`${out}/automatic-${width}.png`});
      await page.getByRole('button', {name:/自动修订或重试/}).click();
      await page.waitForFunction(() => !document.querySelector('#review-dialog').open);
      assert.deepEqual(sent[1].answers, []);
      assert.equal(sent[1].resolution,'continue');

      // 复现截图：七项全部接受修改，汇总后可直接提交，按钮固定可见。
      form = {...structuredClone(fixture.form), token:'seven-fixes', summary:{human:7,automatic:0,optional:0,dismissed:0,merged:0},
        questions:Array.from({length:7}, (_, i) => ({...fixture.form.questions[0], id:`fix-${i}`, detail:`第 ${i+1} 条意见需修改`}))};
      await page.evaluate(r => window.ReviewQuestions.open(r), result);
      for (let i=0;i<7;i++) {
        await page.getByText('接受意见，按建议修改', {exact:true}).click();
        await page.locator('#review-next').click();
      }
      await page.getByText('评审已答完，可以提交了', {exact:true}).waitFor();
      assert.ok((await page.locator('.review-submit-effect').innerText()).includes('7 项按建议修改'));
      assert.equal(await page.getByRole('button', {name:/人工采用当前稿/}).count(), 0);
      await page.locator('.review-summary-details').first().locator('summary').click();
      await page.locator('#review-question-body').evaluate(el => {el.scrollTop=el.scrollHeight;});
      const submitBounds=await page.locator('#review-next').boundingBox();
      assert.ok(submitBounds.y>=0 && submitBounds.y+submitBounds.height<=height);
      await page.screenshot({path:`${out}/submit-seven-${width}.png`});
      await page.locator('#review-next').click();
      await page.waitForFunction(() => !document.querySelector('#review-dialog').open);
      assert.equal(sent[2].resolution,'continue');
      assert.equal(sent[2].answers.length,7);
      assert.ok(sent[2].answers.every(a=>a.choice==='fix'));

      // 保存失败可以重试，返回上一步也不丢选择。
      form = {...structuredClone(fixture.form),token:'submit-retry'};
      let rejectOnce=true;
      await page.route('**/api/job/retry-fixture/review', async route => {
        if(route.request().method()==='GET') return route.fulfill({json:form});
        if(rejectOnce) {rejectOnce=false;return route.fulfill({status:503,json:{detail:'保存暂时失败，请重试'}});}
        sent.push(route.request().postDataJSON());
        return route.fulfill({json:{result,job:null}});
      });
      await page.evaluate(r=>window.ReviewQuestions.open(r),{...result,job_id:'retry-fixture'});
      await page.getByText('接受意见，按建议修改',{exact:true}).click();
      await page.locator('#review-next').click();
      await page.locator('#review-next').click();
      await page.getByText('保存暂时失败，请重试',{exact:true}).waitFor();
      assert.ok(await page.locator('#review-next').isEnabled());
      await page.locator('#review-dialog [data-close-dialog]').click();
      await page.evaluate(r=>window.ReviewQuestions.open(r),{...result,job_id:'retry-fixture'});
      await page.getByText('评审已答完，可以提交了',{exact:true}).waitFor();
      await page.locator('#review-back').click();
      assert.ok(await page.locator('input[value="fix"]').isChecked());
      await page.locator('#review-next').click();
      await page.locator('#review-next').click();
      await page.waitForFunction(()=>!document.querySelector('#review-dialog').open);
      assert.equal(sent[3].answers[0].choice,'fix');
      assert.deepEqual(errors, []);
      report.push({width,height,humanQuestions:1,automaticQuestionnaire:false,sevenFixesSubmitted:true,retryPreservesAnswers:true,errors});
      await page.close();
    }
    fs.writeFileSync(`${out}/ui-report.json`,JSON.stringify(report,null,2));
    console.log('PASS: 3 个视口；合并风险、自动修订、7 项评审直接提交、固定提交按钮、失败重试和返回保留答案');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
