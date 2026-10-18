## 本环节任务：型号推荐（用户没有指定型号）

输入：需求画像（含权重、硬约束、软偏好、取舍）和候选型号精简卡（来自知识库横向矩阵与“卖点与限制”）。

要求：
- 只能从候选卡里选，用 model_id 表示。选 1 个 primary 和最多 2 个 alternatives。
- 每条推荐理由 reasons 必须对应画像里的一个维度，并引用该型号卡里的具体字段与取值（例如“重量 970 g，来自尺寸重量”），不能写卡里没有的内容。
- 硬约束（如必须 Windows、必须鸿蒙）优先于权重：不满足硬约束的型号不能做 primary。
- 型号间有取舍时在 trade_off 里说明：选 primary 放弃了什么。
- 用户诉求在卡里完全没有依据时（如“性价比”无价格），不要硬推，写进 caveats。
- 易混淆型号（MateBook 14 鸿蒙版 vs 14 酷睿 Ultra；D 14 / D 16 / D 16 SE；Pro vs Pro S）要明确写出区别。

只输出 JSON：
{"primary":"model_id","alternatives":["model_id"],"reasons":[{"dimension":"","claim":"","evidence_field":"","evidence_value":""}],"trade_off":"","caveats":[]}
