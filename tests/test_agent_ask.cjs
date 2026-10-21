const test = require('node:test');
const assert = require('node:assert/strict');
const { suggestAnswers, applyAnswers } = require('../src/mvp/web/agent-ask.js');

test('常见维度给出能直接回答题目的场景选项', () => {
  const samples = [
    ['您所在专业或课程是否指定了必须运行的特定软件（如编程环境、设计软件等）？', '编程开发，如 VS Code、Python'],
    ['您的预算大致区间是多少（例如：4000-5000元）？', '5000 元以内'],
    ['您每天携带电脑的频率和距离大概是多少（如仅宿舍到教室，还是全天通勤）？', '每天通勤/上课都带着'],
    ['您对电脑的操作系统有偏好吗（Windows/macOS/鸿蒙等）？', '用惯了 Windows'],
    ['请提供需要运行的具体编程/设计类软件的名称及版本号。', '编程开发，如 VS Code、Python'],
    ['您期望的设备重量上限是多少千克？', '不超过 1.5 kg'],
    ['该机型的具体机身重量是多少千克？', '按知识库资料为准']
  ];
  for (const [question, expected] of samples) {
    const options = suggestAnswers(question, {});
    assert.ok(options.length >= 2 && options.length <= 4, question);
    assert.ok(options.includes(expected), `${question} -> ${options.join(' / ')}`);
  }
});

test('只有型号选择题使用候选型号，未知问题保留自由填写', () => {
  const models = ['HUAWEI MateBook 14（鸿蒙版）', 'HUAWEI MateBook 14 酷睿 Ultra', 'HUAWEI MateBook D 14'];
  assert.deepEqual(suggestAnswers('“MateBook 14” 对应知识库里的多个型号，请确认具体型号', { candidates: models }),
    [...models, '按需求帮我推荐']);
  assert.deepEqual(suggestAnswers('还有其他需要说明的吗？', {}), []);
});

test('截图中的软件问题不能被候选电脑型号覆盖', () => {
  const question = "用户所需的‘编程与设计类专业软件’具体名称及版本是什么？（用于确认对CPU架构、GPU类型、内存容量及操作系统的硬性要求）";
  const candidates = ['HUAWEI MateBook 14（鸿蒙版）', 'HUAWEI MateBook Fold 非凡大师'];
  const options = suggestAnswers(question, { candidates });
  assert.ok(options.includes('编程开发，如 VS Code、Python'));
  assert.ok(options.every(option => !candidates.includes(option)));
  assert.ok(suggestAnswers('这款电脑需要适配哪些具体软件？', {candidates}).every(option=>!option.includes('知识库')));
  assert.ok(suggestAnswers({field:'system',question:'这些软件需要 Windows 本机环境吗？'}, {candidates}).includes('必须在本机使用 Windows'));
});

test('优先使用每题自带选项，过滤误配机型；不为软件题改写产品字段', () => {
  const spec = {id:'software', field:'software', question:'要用哪些软件？', options:['Python', 'CAD', 'HUAWEI MateBook 14']};
  assert.deepEqual(suggestAnswers(spec, {}), ['Python', 'CAD']);
  const merged = applyAnswers({product:'原机型', clarify_round:1}, [{...spec, answer:'HUAWEI MateBook 14'}], {candidates:['HUAWEI MateBook 14']});
  assert.equal(merged.product, '原机型');
  assert.equal(merged.clarify_round, 2);
  assert.equal(merged.clarify_answers[0].id, 'software');
});

test('自填型号写回产品，型号选择和场景提问都计入两轮上限', () => {
  const first = applyAnswers({}, [{field:'product',question:'具体型号？',answer:'自填型号'}]);
  assert.equal(first.product, '自填型号');
  assert.equal(first.clarify_round, 1);
  const second = applyAnswers(first, [{field:'system',question:'系统要求？',answer:'Windows'}]);
  assert.equal(second.clarify_round, 2);
  assert.equal(second.clarify_answers.length, 2);
});

test('回答写回型号与平台，其余作为补充文本保留原输入', () => {
  const task = { product: '', platform: 'xiaohongshu', extra: '想轻一点', constraints: ['不提价格'] };
  const merged = applyAnswers(task, [
    { question: '选哪个型号', answer: 'HUAWEI MateBook 14（鸿蒙版）' },
    { question: '准备发布到哪个平台', answer: '公众号' },
    { question: '预算区间', answer: '4000–5000 元' }
  ], { candidates: ['HUAWEI MateBook 14（鸿蒙版）'] });
  assert.equal(merged.product, 'HUAWEI MateBook 14（鸿蒙版）');
  assert.equal(merged.platform, 'wechat_article');
  assert.equal(merged.extra, '想轻一点\n\n问：选哪个型号\n答：HUAWEI MateBook 14（鸿蒙版）\n\n问：准备发布到哪个平台\n答：公众号\n\n问：预算区间\n答：4000–5000 元');
  assert.deepEqual(merged.constraints, ['不提价格']);
  assert.deepEqual(task.constraints, ['不提价格'], '不修改原任务');
  assert.equal(task.product, '');
});

test('人群、场景与平台回答直接写回简报字段，便于下一次运行继续', () => {
  const task = { product: '', audience: '', scenario: '', platform: 'xiaohongshu', extra: '', constraints: [] };
  const merged = applyAnswers(task, [
    { question: '目标人群是谁？', answer: '大学新生' },
    { question: '使用场景是什么？', answer: '开学季' },
    { question: '准备发布到哪个平台？', answer: '小红书' }
  ]);
  assert.equal(merged.audience, '大学新生');
  assert.equal(merged.scenario, '开学季');
  assert.equal(merged.platform, 'xiaohongshu');
  assert.ok(merged.extra.includes('问：目标人群是谁？\n答：大学新生'));
});
