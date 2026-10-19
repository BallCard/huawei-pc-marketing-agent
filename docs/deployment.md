# v1.0 部署与配置

华章有据是 FastAPI + 原生网页的单实例应用，生成任务运行在后台线程，任务与结果存 SQLite。面向本人及小范围展示，使用共享访问账号。只运行一个进程，不能使用多个 worker 或多个副本。

## 本次发布记录

2026-10-19：应用代码 `5f7dda9` 已推送 GitHub，私有创空间 [BallCard/huazhang-youju](https://modelscope.cn/studios/BallCard/huazhang-youju) 已返回 **Running**。使用平台 API 专用地址验证了 HTTPS 登录、鉴权、10 个型号读取、真实生成与登记图片访问；线上样例约 23 秒，实际使用 Qwen 解析与 DeepSeek 写作、审核。

13 项 Python 检查与 9 项前端接力检查通过；8 种真实流程完成（四平台、缺输入、自动推荐、缺整机图、修改）。内容仍可能有审核异议或篇幅超限，保留待人工复核提示，未将生成成功当作所有稿件审核通过。资料包缺少 D 16 2024 等型号的整机图，已验证缺图提示。

创空间保持私有。浏览器需登录有权限的魔搭账号，再使用 `.env.deploy` 内的演示账号进入工作台；不会将管理令牌放进浏览器 URL。自动化核查使用网关返回的 API 专用地址和令牌，仅在本机进程中传递。

## 平台选择（2026-10-19 核对）

| 平台 | 适配判断 | 本版安排 |
| --- | --- | --- |
| 魔搭 Docker 创空间 | 能运行现有 Python 和原生网页，端口为 7860；需绑定阿里云并实名 | 首选私有空间 `BallCard/huazhang-youju`，只使用实际返回的免费 CPU 资源 |
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
| `LLM_BASE_URL` | `https://api.deepseek.com` |
| `LLM_API_KEY` | DeepSeek 密钥，存创空间 **Secret** |
| `WRITER_MODEL` / `JUDGE_MODEL` | `deepseek-flash`；独立请求与审核上下文 |
| `LLM_THINKING` | `disabled`，展示优先响应速度 |
| `FAST_MODEL` | `Qwen/Qwen3.5-35B-A3B` |
| `FAST_LLM_BASE_URL` | `https://api-inference.modelscope.cn/v1` |
| `FAST_LLM_API_KEY` | 魔搭推理令牌，存创空间 **Secret** |
| `FAST_LLM_THINKING` / `FAST_LLM_EXTRA_BODY` | `auto` / `{"enable_thinking":false}` |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | 演示访问账号 / 随机密码；密码存 **Secret** |
| `COOKIE_SECURE` | HTTPS 为 `1`，仅本机 HTTP 验证时为 `0` |
| `HOST` / `PORT` | 魔搭为 `0.0.0.0` / `7860` |
| `KB_BACKEND` / `KB_DIR` | `local` / `/app/data/kb` |
| `CACHE_DIR` | `/app/data/cache`，需匹配资料包的 `vision.json` |
| `JOB_DB` | `/mnt/workspace/huazhang-youju/jobs.sqlite3`，使用魔搭持久目录 |
| `MAX_CONCURRENT_JOBS` | `1` |
| `MODELSCOPE_API_KEY` | 仅本机部署工具使用的魔搭管理令牌，不整份上传本机配置 |

未配置单独角色接口时复用 `LLM_*`；写作和审核同样支持 `WRITER_LLM_*`、`JUDGE_LLM_*` 覆盖。没有静默切换供应商的回退。“质量优先”按三个角色配置运行；“快速创作”写作和审核也使用 FAST 模型。

图片标签已离线预计算，上线不需再次调用视觉模型。重新分析图片时需单独选择支持视觉的模型。资料包与视觉缓存必须配套。

## 魔搭发布

目标固定在 `deploy/modelscope/target.json`。发布工具使用官方 OpenAPI，创建时默认私有，查询实际免费硬件，不主动改成公开或付费。

```powershell
python -X utf8 scripts/deploy_modelscope.py inspect
python -X utf8 scripts/deploy_modelscope.py deploy
python -X utf8 scripts/deploy_modelscope.py status
```

先提交主项目代码。工具在忽略的 `data/deploy/modelscope` 准备独立 Git 检出，将代码与产品资料同步到私有创空间；在 `deployment-source.json` 记录源提交。仅复制产品资料与 `vision.json`，不上传本机历史作品。密钥经 Secret API 写入，Git 认证通过进程环境和 askpass，远端 URL 不含令牌。

不要把带资料包的创空间改为公开源码。对他人展示前配置创空间允许的访问范围，再单独告知演示账号。免费资源有额度和生命周期限制，改名或迁移可能影响持久目录；重要结果请导出或备份。

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
node --test tests/test_flow_playback.cjs
python -X utf8 scripts/preflight.py --check-model
# 另启本机部署配置服务后执行真实生成验收：
python -X utf8 scripts/acceptance.py --base http://127.0.0.1:7880
```

部署配置本机验证时设 `APP_ENV_FILE=.env.deploy`、`HOST=127.0.0.1`、`COOKIE_SECURE=0`、`PORT=7880`，再运行 `python -X utf8 -m src.mvp.app`。真实验收包含四平台、缺输入、自动推荐、缺整机图和修改指令，结果保存在忽略的 `data/acceptance/latest.json`。`ok_with_flags` 表示仍需人工复核。

## 官方依据

- [魔搭 Docker 与持久目录](https://github.com/modelscope/modelscope-skills/blob/main/skills/ms-studio-deploy/references/docker-templates.md)、[部署 OpenAPI](https://github.com/modelscope/modelscope-skills/blob/main/skills/ms-studio-deploy/SKILL.md)。
- [魔搭 API 推理](https://modelscope.cn/docs/model-service/API-Inference/intro)；本次使用实际账号取得模型列表并验证 JSON 返回。
- [DeepSeek 模型与接口](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。
- [Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi)、[函数限制](https://vercel.com/docs/functions/limitations)。
- [Cloud Run CPU 与容器约定](https://docs.cloud.google.com/run/docs/container-contract)。
