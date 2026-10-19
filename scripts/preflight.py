"""启动前检查。默认不调用模型；--check-model 验证三个角色的真实 JSON 响应。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mvp import __version__, llm, settings
from src.mvp.kb import get_kb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-model", action="store_true")
    args = parser.parse_args()
    try:
        settings.validate_runtime()
        endpoint = urlsplit(settings.LLM_BASE_URL)
        if endpoint.scheme not in ("http", "https") or not endpoint.hostname:
            raise ValueError("LLM_BASE_URL 必须是完整的 HTTP(S) 接口地址")
        if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError("接口地址不能包含凭据、查询参数或片段；密钥请放 LLM_API_KEY")
        kb = get_kb()
        models = kb.models()
        if not models:
            raise ValueError("资料包中没有可用产品型号")
        no_hero = []
        for model in models:
            doc = kb.load(model.id)
            if not doc.snippets:
                raise ValueError(f"{model.name} 没有产品事实")
            if not any(image.is_hero for image in doc.images):
                no_hero.append(model.name)
        settings.JOB_DB.parent.mkdir(parents=True, exist_ok=True)
        # Verify state storage without creating or changing the real task database.
        import tempfile
        with tempfile.TemporaryFile(dir=settings.JOB_DB.parent) as test_file:
            test_file.write(b"ok")
        print(f"华章有据 {__version__}：配置与资料包检查通过，{len(models)} 个型号。")
        print("访问账号：", "已配置" if settings.AUTH_PASSWORD else "未配置（仅本机）")
        print("模型密钥：", "已配置" if settings.LLM_API_KEY else "未配置（依赖无需密钥的接口）")
        if endpoint.hostname in ("127.0.0.1", "localhost", "::1"):
            print("注意：当前模型接口在本机；容器或云部署必须修改 LLM_BASE_URL。")
        if no_hero:
            print("缺少已确认整机图（生成时会提示）：", "、".join(no_hero))
        if args.check_model:
            for role, label, model in (("fast", "解析", settings.FAST_MODEL), ("writer", "写作", settings.WRITER_MODEL),
                                      ("judge", "审核", settings.JUDGE_MODEL)):
                raw = llm.chat([{"role": "user", "content": 'Reply with the JSON object {"ok":true}.'}],
                               model=model, json_mode=True, max_tokens=300, retries=0, role=role)
                if llm.parse_json(raw).get("ok") is not True:
                    raise ValueError(f"{label}模型没有返回预期 JSON")
                print(f"{label}模型 JSON 连接通过：{model}")
        return 0
    except Exception as exc:
        # Provider exception strings can contain private endpoint details.
        if isinstance(exc, llm.LLMError):
            print("检查失败：模型连接或 JSON 响应异常，请核对接口、密钥、模型及服务端日志。")
        else:
            print(f"检查失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
