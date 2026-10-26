# 前五名产品与代码实测：PC-Studio 对比报告

评测日期：2026-10-26。

> **版本标注（2026-10-26 增补）**：本文为 **v1 初评**（公开检索 + 仓库初查）。经仓库深读与线上实测复核，部分结论已修正——"蒸馏 / 共创 / 连续性"逐队证据与修正清单见 [复盘深化/3_竞品证据档案_四队.md](复盘深化/3_竞品证据档案_四队.md)。

排名和奖项以最终成绩截图为准；GitHub 与魔搭入口来自《浙大黑客松华为赛道 决赛入围名单》。名单中的入围顺序不是最终排名。名单和截图在队名、项目名上有少量差异，本报告保留来源差异。

## 前五名入口

| 最终排名 | 队伍 / 项目 | 分数 / 奖项 | 入口 |
| ---: | --- | ---: | --- |
| 1 | 振宁队 / 稿研 | 80.62 / 一等奖 | [产品](https://blog.oppenheimer123.xyz/huawei-pc/) · [GitHub 链接](https://github.com/Feynman724/huawei-pc-marketing-agent-hackathon) |
| 2 | byai / 华为PC营销图文工作台 | 79.07 / 一等奖 | [ModelScope](https://www.modelscope.cn/studios/cangyuyi/huawei-pc-marketing-agent) · [应用](https://cangyuyi-huawei-pc-marketing-agent.ms.show/) · [GitHub](https://github.com/cangyuyi/huawei-pc-marketing-agent) |
| 3 | Elsechord / MateQuill1 | 77.13 / 二等奖 | [ModelScope](https://www.modelscope.cn/studios/Shuuyou/MateQuill) · [应用](https://shuuyou-matequill.ms.show/) · [GitHub](https://github.com/Shuuyou/MateQuill) |
| 4 | 金风塘的虾（名单 PDF 写作避风塘的虾）/ 华为PC门店图文助手 | 77.13 / 二等奖 | [ModelScope](https://www.modelscope.cn/studios/Xxxxcxc/Huawei-Marketing) · [应用](https://xxxxcxc-huawei-marketing.ms.show/) · [GitHub](https://github.com/xxxxdxc/Huawei-Marketing) |
| 5 | ZJUshaaa / PC-Studio | 74.22 / 二等奖 | [应用](https://ballcard-huazhang-youju.ms.show/) · [GitHub](https://github.com/BallCard/huawei-pc-marketing-agent) |

## 在线实测

- 稿研：页面可访问；/huawei-pc/api/health 返回 200、status=ok、knowledge_source=local、demo_available=true。页面主路径清楚：选题、产品、受众、平台、写法、来源、核验、导出。GitHub 链接返回 404 或不可访问，代码无法复核。
- byai：/healthz 返回 200；/api/v1/readiness 返回 deployment_ready=true 但 business_ready=false；资料源是本地官方导出，competition_ready=false，逐条语义核验未实现。应用 HTML 能打开，线上 readiness 没有把底座冒充成完整业务。
- MateQuill：HTML 壳可返回 200，但 /api/status 和 /api/runtime/status 返回 401，需要先登录工作空间。产品主张覆盖多租户、企业活动、门店协作、语音/图片/文字、可编辑海报，公开评委入口却被登录挡住。
- 华为PC门店图文助手：/api/settings 返回 200，显示 knowledge_source=ima、ima_ready=true、Writer/Reviewer 已配置；/api/catalog 返回 200 并返回华为 PC 产品目录。配置状态仍不等于真实模型任务已完成。
- PC-Studio：/healthz 和 /api/info 都返回 200，匿名可访问，本地知识库连接成功，10 个型号可读；入口最顺滑，但资料源是本地副本，不是实时 IMA。

## 代码实测

| 项目 | 约源码行数 | 测试文件 | 当前本机结果 |
| --- | ---: | ---: | --- |
| byai | 39,093 | 40 | 测试收集被 ModuleNotFoundError: aiosqlite 阻断 |
| MateQuill1 | 79,284 | 184 | 测试收集被 argon2.exceptions.InvalidHashError 导入阻断 |
| 华为PC门店图文助手 | 19,545 | 28 | 测试收集被 content-strategy 源文件 SHA-256 不匹配阻断 |
| PC-Studio | 约 18,494 | 232 项本地测试 | 197 Python + 35 前端全部通过 |

三个对手仓库的收集阻断不直接等于上游 CI 失败，但说明拿到仓库后不能在当前环境直接复现；这本身是代码交付摩擦。

## 各队锐评

### 稿研

它是前五里最像现场成品的产品：输入顾客问题，选择产品、受众、平台和写法，跑完资料、写作、核验和导出。它的优势是评委无需理解架构就能完成一次任务。缺点是代码不可审查，知识库、模型、任务持久化和异常恢复都没有公开证据。

### byai

它的工程底子很强：对话、热点、候选选品、三篇文案、图文工作室、规则扫描和导出都在仓库里，README 还明确承认本地知识库和未完成语义核验。问题是体量大、业务 readiness 仍为 false，现场很容易让评委分不清已完成能力和底座能力。

### MateQuill1

它的架构上限最高：多租户、企业与门店协作、PostgreSQL、任务租约、额度、素材账本、独立审校和海报编辑都做了。问题是复杂度明显超过黑客松现场的解释预算，公开入口还要求登录；如果评委不能马上体验，工程优势就会折损成展示负担。

### 华为PC门店图文助手

它的后端治理最稳：Planner 与 Writer 分离，策略确认、规划确认、编辑后重新核验、服务端授权导出都写成了硬门槛。问题是大量验证使用合成证据、模型桩和隔离数据库；ima_ready=true 只是配置状态，不能替代一次真实模型成稿和人工质量验收。

### PC-Studio

你的优势是匿名入口最完整、现场动线最清楚、流程和状态测试扎实。本地 232 项测试全部通过，健康接口也能证明部署可用。

但真正拖分的是兑现链：ImaKB 仍是占位实现，实际使用本地资料；三组真实任务仍有 ok_with_flags、超字数和能力暗示；提交材料使用“华章有据”，成绩身份却是 ZJUshaaa / PC-Studio；单实例、SQLite、本地资料和单任务并发也不支持直接讲规模化。

## 我的非官方判断

PC-Studio 的工程质量不输前四，产品证据却没有把工程优势转化成现场分数。稿研赢在一条路径讲透；门店图文助手赢在证据门控；MateQuill 赢在产品化架构；byai 赢在广度和工程潜力。你现在最需要学的是收窄承诺和降低解释成本。

下一版优先级：统一 ZJUshaaa / PC-Studio 身份；把资料源明确写成本地官方副本；做一条没有 ok_with_flags 的单型号、单场景、单平台演示；用人工修改时间和可发布率做对照；最后再考虑增加 Agent 或门店看板。

本轮只做只读检查：没有提交线上任务、没有写入对手数据、没有使用任何密钥。
