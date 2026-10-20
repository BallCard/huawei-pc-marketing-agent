## 本环节任务：场景解析（结构化先验 + 自由文本推理）

输入包含：任务（产品/人群/场景/平台/目标/限制/补充）、可用需求维度、结构化先验权重（由“人群×场景”规则表给出）。

请做三件事：
只从用户实际输入提取需求；不要把某类人群的常见诉求伪装成用户已说的要求。用户只说便携或接口时，不自行升级为软件兼容、续航或性能承诺。未知事项单列，不占主切入点。保留用户给定的行动目标，不擅自改成更复杂的多步动作。
1. 把用户的自由描述（goal、constraints、extra、audience、scenario）拆成：
   - hard_constraints：硬约束（例如“必须能装 Windows 软件”“预算不超过 X”“不要提价格”）
   - soft_preferences：软偏好，每条标注最相关的维度（dims，可多个，取自可用维度；映射不上就给空数组）
   - tradeoffs：用户在哪些属性之间要取舍（例如“便携 vs 性能”）
2. 在先验权重的基础上，给出你推理后的 weights（对每个维度给 0-1 数值，总和约为 1）。
   “性价比/划算”对应 value 维度，但它不是产品事实，只能落在“配置价值”：靠内存/存储/接口/配件/系统生态是否满足任务来体现，价格要有官方快照才能提。
3. 找出“知识库大概率没有直接依据”的诉求，放进 unmappable（例如“好看显气质”“比 xx 品牌更好”），不要强行映射。

其他字段：
- user_problem：这类读者在这个场景里最真实的一个问题（一句话，不要写产品）
- goal：这篇内容要促成的单一动作
- stage：认知 / 比较 / 决策 / 到店 之一
- strategy_notes：为什么这样切入、卖点为什么这样排序（2-3 句，可解释，给评审看）
- need_info：{"blocking": bool, "questions": []}。只有在人群或场景无法从已有文字推断、且会改变内容方向时，blocking 才为 true；追问要具体（使用软件、预算区间、携带频率、系统习惯），最多 4 条。

只输出 JSON，字段：
{"audience":"","scenario":"","user_problem":"","goal":"","stage":"","hard_constraints":[],"soft_preferences":[{"text":"","dims":[]}],"tradeoffs":[],"weights":{},"unmappable":[],"strategy_notes":"","need_info":{"blocking":false,"questions":[]}}
