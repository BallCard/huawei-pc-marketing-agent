# 网页生图私有链路

2026-10-20：用户选择用本人 ChatGPT Plus 网页会话试接，并授权使用 network-infra 管理的美国 VPS。工作台继续部署在魔搭，无需迁移到 Vercel。本人已提供短期网页凭据，VPS 已读取模型列表并完成一次真实参考图生图，约 29.1 秒。成图继续保留待复核，不等同于产品事实全部通过。

## 当前方案

采用 MIT 项目 [5yu4n/gptweb2api](https://github.com/5yu4n/gptweb2api)，固定提交 `985f4f45a49fbfdb2f8524686ab25759fd5195bb`。Go 服务只监听 VPS 的 `127.0.0.1:17889`，Python worker 主动通过 HTTPS 向魔搭领取任务、回传 PNG。没有新增 VPS 公网端口、域名、证书或防火墙规则。

VPS 只有约 1 GB 内存，因此使用不含浏览器的轻量路径，不安装 Docker、Chrome 或 Node。两项服务使用独立无登录用户，程序由 root 持有，配置权限 0600，systemd 限制内存与 CPU；既有网络服务与端口保持原配置。会话只存于 VPS 专用目录，魔搭不保存 ChatGPT 会话。

工作台用独立 `X-Poster-Worker-Key` 验证 worker，仅开放心跳、领取、结果交付三个接口；该密钥不能访问知识库、历史作品等工作台接口。工作台登录 Cookie 也不能调用 worker 接口。魔搭入口会拦截 Bearer 并按平台 SDK Token 处理，不能把它当作普通反代鉴权透传，因此任务链路采用独立请求头。

产品图与去文字风格图通过本机 Go 接口 `/v1/images/edits` 作为两个 `image` multipart 字段提交。只请求一张，返回 `b64_json` 后校验格式、大小、尺寸与摘要，再进行独立成图审核。`chatgpt-web` 是工作台记录名，不能据此断言网页实际使用了某个 GPT Image 版本。

任务领取不重新分配；worker 提交前保存本地回执，重启只回报中断或重传已有结果。等待超时可查询原任务，不能自动多生成一张。丢失的运行任务最终标记失败，避免永久堵住后续任务。图片交付可重复确认，不能覆盖已完成图片。

## 部署与账号

材料在 `deploy/gpt-direct/`：两个 systemd 单元、出站 worker、安装脚本和固定源码的就绪检查补丁。补丁让缺失凭据时 `/readyz` 返回未就绪，而不是仅因配置了文件路径就报告成功。凭据刷新已关闭，只接收本人提供的短期 access token，不上传其他应用的登录文件。

先在本机从固定上游提交应用 `patch_gateway.py`，运行 Go 测试，再以 `GOOS=linux GOARCH=amd64 CGO_ENABLED=0` 构建。把构建产物、worker、单元、两份私有环境文件上传到 0700 临时目录，再由 `install.sh` 安装。网关环境文件必须指定专用 `GPTWEB_OAUTH_TOKEN_FILE=/var/lib/huazhang-gpt/auth.json`、`GPTWEB_OAUTH_REFRESH_DISABLED=1`、`GPTWEB_TRANSPORT_MODE=direct`、`GPTWEB_UPSTREAM_MAX_RETRIES=0` 和本地访问密钥。worker 环境文件只含魔搭地址、任务密钥及本地网关访问密钥。

本人将短期网页 access token 放进本机已忽略的 `deploy/gpt-direct/auth.json`，支持 `{"access_token":"…"}` 或网页会话 JSON 的 `accessToken` 字段。只传必要字段，不传密码、Cookie、refresh token 或其他个人资料。`scripts/connect_gpt_account.py` 从该文件读取，使用已验证主机密钥的 SSH 安全安装到 VPS 的 0600 专用文件，只重启新建的 Go 服务，不回显凭据。目标主机与 SSH 私钥路径只在 `deploy/gpt-direct/.env` 本地配置。

工作台使用以下配置；账号令牌只在 VPS 专用服务中保存，魔搭只持有任务密钥：

```dotenv
POSTER_IMAGE_PROVIDER=private_worker
POSTER_IMAGE_MODEL=chatgpt-web
POSTER_WORKER_TOKEN=独立随机任务密钥
POSTER_REVIEW_BASE_URL=https://api-inference.modelscope.cn/v1
POSTER_REVIEW_API_KEY=魔搭推理令牌
```

`GET /api/info` 需工作台登录，仅返回连接与账号已配置的布尔状态，不提供密钥。心跳成功证明控制链路可达；真实账号出图、两张参考图是否生效和成图质量仍须实测。配置凭据不等于账号额度或上游网络已验证可用。

## 网络与备选

独立免费测试空间 `BallCard/huazhang-gpt-network-check` 实测普通 HTTPS 可用；ChatGPT 主站和图片域请求失败，认证域返回 Cloudflare 403。测试没有上传会话或产品资料，已请求停止。不能根据一次失败断言永久封锁，也不能把普通 HTTPS 成功算作完整 GPT 生图已通。结果保存在本机忽略目录 `data/qa/network-check/`。

VPS 的普通 HTTPS 探测也遇到 Cloudflare 403，但真实账号的模型列表与带参考图生图成功；不能用匿名主站探测代替实际接口验证。若以后上游要求交互式浏览器，需调整资源或使用浏览器方案，不能自动处理验证码。

备选 [stufently/gpt-web-gateway](https://github.com/stufently/gpt-web-gateway) 固定提交 `893f553be358210a5c045aa9f62b56ba1edc5c78`，材料在 `deploy/gpt-web/`，支持浏览器登录、`reference_images[]` 和实际上传数量确认；本机鉴权验证通过，尚未登录或出图。已补强强制鉴权、静态图片保护、监听地址和人工验证码处理。其浏览器内存需求不适合当前 VPS。

Gemini 仅为备选，材料在 `deploy/gemini-web/`，不是当前方案的凭据前置条件。网页模型别名不能证明实际图像模型版本。

Vercel 已支持[容器函数](https://vercel.com/kb/guide/docker-on-vercel-vs-render)，但无状态并随流量缩容；[执行时长](https://vercel.com/docs/functions/configuring-functions/duration)受套餐约束。[Daemons](https://vercel.com/kb/guide/vercel-functions-containers-daemons)可运行后台进程，但没有入站 HTTP/TCP 或持久本地磁盘。已有美国 VPS 时，保留魔搭加出站 worker 更直接。

这是网页内部协议的实验接法。官方 [Sign in with ChatGPT 预览限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)尚不支持图像生成，不能把这条链路描述为官方套餐生图接口。短期令牌到期后需本人更新；不持有 refresh token。会话与上游协议变化可能使其失效。

## 本次验收边界

本机完成 100 项 Python 与 26 项 JavaScript 测试。线上魔搭健康检查和登录成功，worker 心跳表明私有连接及凭据已配置；未授权领取返回 401，工作台 Cookie 不能领取，worker 密钥不能读取工作台接口。VPS 仅新增回环监听，原网络进程及端口未改，两个新服务闲时合计约 37 MB 内存。

真实样张使用本型号产品图＋A 风格图，返回 1,654,537 字节图片。独立转录保留了中文、约 1.31 kg 与重量适用条件。成图改变了产品视角并补画参考图看不到的接口，需要人工核对；审核模型还提出了一条两边写成同一字的“简繁”意见，不能据此认定有错字。保留原始自动结论，不强行改成通过。已收紧后续生图与审核提示词，本次不自动重生。样张和审核记录在本机忽略目录 `data/qa/gpt-direct-sample/`。
