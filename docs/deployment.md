# v1.2 部署与配置

华章有据是 FastAPI + 原生网页的单实例应用，生成任务运行在后台线程，任务与结果存 SQLite。面向本人及小范围展示，使用共享访问账号。只运行一个进程，不能使用多个 worker 或多个副本。

## 本次发布记录

v1.2.0（version1.2，2026-10-21）统一文字模型为魔搭 DeepSeek 1017，需求问询最多两轮；加入重要争议交叉核对、轻微意见与确定错误分流，以及固定的“提交评审结果”按钮。同版收录整图海报、私有出图通道、慢速图片回传和手机布局改进。完整更新内容见 [版本记录](../CHANGELOG.md)。对应源提交以 Git 标签 `v1.2.0` 和创空间 `deployment-source.json` 为准。

本版发布前 140 项 Python 与 32 项前端测试通过，并在 320、390、1440 像素宽度验证两轮问询、七项修改直接提交、失败重试及答案恢复，另通过 152 项页面适配检查。部署配置的三个文字角色均通过真实模型连接检查。发布后的运行版本通过 `/api/info` 核对。性能与质量边界见 [验收记录](editorial-validation.md)，未将自动检查通过视为人工盲评结论。

以下保留 v1.0 的首次部署记录：

2026-10-19 首次部署：应用代码 `5f7dda9` 已推送 GitHub，创空间 [BallCard/huazhang-youju](https://modelscope.cn/studios/BallCard/huazhang-youju) 返回 **Running**。初始配置为魔搭 Qwen 与 DeepSeek 官方 API，线上样例约 23 秒。

后续按作者选择改为全魔搭：`Qwen/Qwen3.5-35B-A3B` 负责解析与提取，`deepseek-ai/DeepSeek-V4.1-Flash-1017` 负责写作与独立审核。v1.0 应用提交 `8ca62d3` 曾在创空间运行；线上完整小红书样例 31 秒，事实规则与独立审核通过，三张图片可访问，缺输入返回补充提示。本机完整样例约 30 秒，其真实界面截图已收录到 README，作品图已更新为新版电脑布局。

v1.0 发布时的 13 项 Python 检查与 9 项前端接力检查通过。首发混合接口配置下完成 8 种真实流程（四平台、缺输入、自动推荐、缺整机图、修改），全魔搭配置另验证了本机与线上完整小红书生成，以及线上缺输入流程。内容仍可能有审核异议或篇幅超限，保留待人工复核提示，未将生成成功当作所有稿件审核通过。资料包缺少 D 16 2024 等型号的整机图，已验证缺图提示。

当前访问目标为 `protected`（保护模式）：应用入口可访问，代码仓库隐藏。访问者只需工作台演示账号，不需要魔搭账号；管理令牌不会放进浏览器 URL。

## 给队友和评委访问

建议发送[体验入口](https://ballcard-huazhang-youju.ms.show)。魔搭会自动跳转到全屏创空间页面；已在未登录魔搭的浏览器中验证演示账号登录、开屏与进入工作台。由作者单独告知 `.env.deploy` 中的 `AUTH_USERNAME` 和 `AUTH_PASSWORD`；不要把模型密钥或魔搭管理令牌发给访问者。

最终版本已核对：介绍页与五张截图可匿名访问，源码 Git 匿名读取返回 401，任务、产品图片与接口登录前返回 401；登录后模型、知识库与生成正常。验证摘要保存在本机忽略的 `data/acceptance/protected-access.json`。

可复制的邀请说明（密码单独填写，不提交仓库）：

```text
华章有据体验：https://ballcard-huazhang-youju.ms.show
使用我单独发送的演示账号登录，无需注册魔搭或配置 API。
进入后可点「试试示例」→「开始创作」，然后看图文作品与事实核验。
```

魔搭可见性三种模式：`public` 是代码与应用都公开；`protected` 是应用可访问、代码隐藏；`private` 是两者都不公开。本项目带资料包，发布工具仅接受 `private` 或 `protected`，禁止直接改成 `public`。

截图是明确挑选的展示资源，可以匿名读取；[图文介绍页](https://ballcard-huazhang-youju.ms.show/about) 无需登录，适合先给评委了解项目。魔搭保护模式下不对访客展示仓库 README，介绍页和登录页入口承接公开介绍。任务、产品资料接口和其他代码资源仍需工作台登录。共享演示账号适用于小范围展示，不具备用户间数据隔离；任务并发上限为 1。

## 平台选择（2026-10-19 核对）

| 平台 | 适配判断 | 本版安排 |
| --- | --- | --- |
| 魔搭 Docker 创空间 | 能运行现有 Python 和原生网页，端口为 7860；需绑定阿里云并实名 | `BallCard/huazhang-youju` 使用保护模式，代码隐藏；只使用实际返回的免费 CPU 资源 |
| 普通服务器 / Docker 主机 | 单实例服务与持久卷适配当前后台线程 | 提供 Dockerfile 与 compose.yaml；对外接 HTTPS 代理 |
| Vercel | 支持 FastAPI；函数实例自动扩缩，当前后台线程和本地 SQLite 不能直接作为可靠的跨请求任务系统 | 需改为持久队列、共享数据库和对象存储，或单请求流式生成 |
| GPT Sites | 服务端使用 Cloudflare Workers，原生网页可复用；Python 编排不能直接照搬 | 需移植后端到 Worker，或另建容器后端，本版不做拆分 |
| Google Cloud Run | 支持容器，但默认只在请求期间分配 CPU，本地文件不作为持久库 | 需调整后台 CPU 和持久存储；本版先用魔搭 |

Vercel 的主要障碍是任务和存储方式，并非不能运行 Python。GPT Sites 的运行方式来自本机 Sites 插件说明。

## 已实现与边界

- 独立开屏、四个平台生成、场景示例、一句话输入、自动选型、事实溯源、核验和审核、按指令重新生成、复制正文、离线 HTML 导出。
- 网页账号登录；HttpOnly Cookie，有效期 12 小时；退出清除当前浏览器会话。对外监听强制要求账号和密码。
- 默认最多一个任务，超限返回 429，限制展示期间的模型用量。
- SQLite 保存每步快照和结果；完成作品刷新可恢复，重启时将运行任务标记为中断。新建任务时清理较早完成结果，保留最近约 30 个。
- `/healthz` 只返回固定健康状态；资料、任务和接口要求登录，接口与作品页不缓存。
- 独立审核针对最终展示稿；有异议时标记 `ok_with_flags`，不会显示核验全部通过。

尚不支持 IMA 实时读取、网页上传 ZIP、管理员配置面板、多用户账号与数据隔离、自动向小红书/微信发布。资料基准日为 2026-10-17，参数与销售条件应在发布前人工复核。

## 环境变量

本机开发 `.env` 保持原配置。`.env.deploy` 是忽略的部署专用配置，包含演示账号的随机密码；不要提交 Git、截图或发到聊天。

| 配置 | 本次用途 |
| --- | --- |
| `LLM_BASE_URL` | `https://api-inference.modelscope.cn/v1` |
| `LLM_API_KEY` | 魔搭推理令牌，存创空间 **Secret** |
| `FAST_MODEL` / `WRITER_MODEL` / `JUDGE_MODEL` | `deepseek-ai/DeepSeek-V4.1-Flash-1017`；独立请求与审核上下文 |
| `LLM_THINKING` | `disabled`，展示优先响应速度 |
| `FAST_LLM_BASE_URL` | `https://api-inference.modelscope.cn/v1` |
| `FAST_LLM_API_KEY` | 魔搭推理令牌，存创空间 **Secret** |
| `FAST_LLM_THINKING` / `FAST_LLM_EXTRA_BODY` | `disabled` / `{}`，统一沿用 DeepSeek 配置 |
| `IMAGE_VERIFY_MODEL` / `IMAGE_VERIFY_BASE_URL` | `Qwen/Qwen3.5-35B-A3B` / 魔搭推理接口，保留视觉输入能力 |
| `IMAGE_VERIFY_API_KEY` | 魔搭推理令牌，存创空间 **Secret**；留空复用 `LLM_API_KEY` |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | 演示访问账号 / 随机密码；密码存 **Secret** |
| `COOKIE_SECURE` | HTTPS 为 `1`，仅本机 HTTP 验证时为 `0` |
| `HOST` / `PORT` | 魔搭为 `0.0.0.0` / `7860` |
| `KB_BACKEND` / `KB_DIR` | `local` / `/app/data/kb` |
| `CACHE_DIR` | `/app/data/cache`，需匹配资料包的 `vision.json` |
| `JOB_DB` | `/mnt/workspace/huazhang-youju/jobs.sqlite3`，使用魔搭持久目录 |
| `MAX_CONCURRENT_JOBS` | `1` |
| `GENERATION_BUDGET_SECONDS` | 默认 `240` 秒上限，为质量模型评审及一次修订/复审留出时间；旧配置若显式设为 `90` 需同步调整，预算不足不会宣称审核通过 |
| `MODELSCOPE_API_KEY` | 仅本机部署工具使用的魔搭管理令牌，不整份上传本机配置 |

未配置单独角色接口时复用 `LLM_*`；写作和审核同样支持 `WRITER_LLM_*`、`JUDGE_LLM_*` 覆盖。没有静默切换供应商的回退。2026-10-21 起三个文字角色统一使用魔搭 DeepSeek 1017，已有简报中的质量与快速档位也调用同一模型。DeepSeek 官方密钥仅保留在本机忽略的 `model.txt`，部署版不再调用官方接口，消耗魔搭推理配额或资源。

其他可评测候选包括 `Qwen/Qwen3.5-122B-A10B`（写作/审核候选）和 `ZhipuAI/GLM-5.2`（复杂任务候选）。模型列表可见不代表适合本任务：需单独验证 JSON、思考模式、延迟和事实审核表现。本版文字角色统一为 DeepSeek 1017，图片核验独立使用视觉模型；连接小样不是文案质量排名。

图片标签已离线预计算，上线不需再次调用视觉模型。重新分析图片时需单独选择支持视觉的模型。资料包与视觉缓存必须配套。

## 魔搭发布

目标固定在 `deploy/modelscope/target.json`，当前为 `protected`。发布工具使用官方 OpenAPI，同步该访问模式、查询实际免费硬件，拒绝公开代码或自动选择付费资源。

```powershell
python -X utf8 scripts/deploy_modelscope.py inspect
python -X utf8 scripts/deploy_modelscope.py deploy
python -X utf8 scripts/deploy_modelscope.py status
```

先提交主项目代码。工具固定读取启动时的 Git 提交，在忽略的 `data/deploy/modelscope` 准备独立检出，将代码与产品资料同步到代码隐藏的创空间；`deployment-source.json` 记录源提交，工作区内尚未提交的编辑不会混入部署。同步时移除上次源提交中已删除的代码文件；仅复制产品资料与 `vision.json`，不上传本机历史作品。密钥经 Secret API 写入，Git 认证通过进程环境和 askpass，远端 URL 不含令牌。

不要把带资料包的创空间改为 `public`。对他人展示时单独告知演示账号；调整 `AUTH_PASSWORD` 并重新部署可以使旧会话失效。免费 CPU 资源与模型推理配额不是一回事，推理资源与并发限制以账号当前规则为准。改名或迁移可能影响持久目录，重要结果请导出或备份。

## 其他 Docker 主机

准备 `.env`、`data/kb` 和 `data/cache/vision.json`，填入可从容器访问的模型接口与访问账号：

```bash
docker compose config --quiet
docker compose up -d --build
```

Compose 只绑定主机 `127.0.0.1:7860`，由 HTTPS 代理转发；知识库和缓存只读挂载，SQLite 使用独立卷。容器中的 `127.0.0.1:8045` 指容器自身，不能直接复用电脑上的反代。

## 验证入口

```powershell
python -X utf8 -m unittest discover -s tests -v
node --test tests/test_process_state.cjs tests/test_stage_rotation.cjs tests/test_process_activity.cjs tests/test_process_clock.cjs tests/test_review_status.cjs tests/test_agent_ask.cjs
python -X utf8 scripts/preflight.py --check-model
# 另启本机部署配置服务后执行真实生成验收：
python -X utf8 scripts/acceptance.py --base http://127.0.0.1:7880
```

部署配置本机验证时设 `APP_ENV_FILE=.env.deploy`、`HOST=127.0.0.1`、`COOKIE_SECURE=0`、`PORT=7880`，再运行 `python -X utf8 -m src.mvp.app`。真实验收包含四平台、缺输入、自动推荐、缺整机图和修改指令，结果保存在忽略的 `data/acceptance/latest.json`。`ok_with_flags` 表示仍需人工复核。

## 官方依据

- [魔搭 Docker 与持久目录](https://github.com/modelscope/modelscope-skills/blob/main/skills/ms-studio-deploy/references/docker-templates.md)、[部署 OpenAPI](https://github.com/modelscope/modelscope-skills/blob/main/skills/ms-studio-deploy/SKILL.md)。
- [魔搭 API 推理](https://modelscope.cn/docs/model-service/API-Inference/intro)；本次使用实际账号取得模型列表并验证 JSON 返回。
- [魔搭三种可见性定义](https://github.com/modelscope/modelscope_hub/blob/main/src/modelscope_hub/constants.py)、[官方 SDK 的保护模式说明](https://github.com/modelscope/modelscope_hub)。
- [DeepSeek 模型与接口](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。
- [Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi)、[函数限制](https://vercel.com/docs/functions/limitations)。
- [Cloud Run CPU 与容器约定](https://docs.cloud.google.com/run/docs/container-contract)。
