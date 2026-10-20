# 网站字体规范

保留暖纸色与编辑式排版，通过真实字重、字号和对比度建立层级。字体资源随站点发布，不以设备是否安装微软雅黑、苹方或宋体决定外观。

| 角色 | 字体 | 默认字重 | 大小与用途 |
| --- | --- | --- | --- |
| 主标题、品牌、章节标题 | Noto Serif SC Variable | 650 | 延续纸感，保留各页面原有标题尺寸与响应式范围 |
| 正文、输入内容 | Noto Sans SC Variable | 450 | 正文 15px；平台作品保留各自的阅读字号与节奏 |
| 操作、字段和重点标签 | Noto Sans SC Variable | 600–700 | 标签 13–14px；选中导航与主要操作加重 |
| 来源、说明、时间 | Sans / Noto Sans Mono Variable | 450–550 | 一般 12–13px，紧凑元信息最低约 11px |

三个字体变量由 `src/mvp/web/fonts.css` 统一声明，`typography.css` 定义界面层级。平台预览使用同一组本地字体，保留原来的平台排版。Logo 字标转为矢量轮廓，SVG 独立打开也不需要本机字体。

## 字体资源

字体来自 Fontsource 的 Noto 变量字体包，版本和 SHA-512 完整性值固定在 `scripts/vendor_fonts.py`。来源、版本与文件清单见 `src/mvp/web/fonts/manifest.json`，每个目录保留 SIL Open Font License。

- Noto Sans SC / Noto Serif SC：5.3.1。
- Noto Sans Mono：5.3.0。
- 共 209 个 WOFF2 字符分片，资源约 10.4 MiB；浏览器根据实际出现的字符按需获取，首次简报页本机实测约 0.90 MiB 字体。
- 页面不请求外部字体服务，也不通过 `local()` 选择用户安装的字体。登录页可公开读取字体与字体样式，产品资料及 API 权限保持原样。
- HTML 导出只嵌入作品需要的字体分片，并附带对应许可证；离线打开依然使用这些字体。

更新字体时执行 `python -X utf8 scripts/vendor_fonts.py`，并同步更新样式资源版本。脚本校验下载包完整性，字体为静态资源，无运行时 npm 依赖。

## 验证

`scripts/check_typography.cjs` 使用已有任务结果，不调用生成模型。覆盖开屏、简报、过程、四平台作品、核验、登录、介绍与品牌页，检查 1440/1280/390 视口；通过 Chromium 的实际渲染字体信息确认文字使用网站字体，检查真实字重，并在离线浏览器中打开导出的 HTML。

```powershell
node scripts/check_typography.cjs
node scripts/check_process_ui.cjs --job <已完成任务ID>
python -X utf8 -m unittest discover -s tests -q
```
