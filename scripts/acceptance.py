"""对运行中的服务执行真实生成验收；结果留在忽略的 data/acceptance 中。"""
import argparse
import json
import sys
import time
from urllib.parse import quote
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mvp import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:7880")
    parser.add_argument("--quick", action="store_true", help="仅验证一个平台及缺少输入")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base, timeout=30)
    if settings.AUTH_PASSWORD:
        response = client.post("/api/login", json={"username": settings.AUTH_USERNAME, "password": settings.AUTH_PASSWORD})
        response.raise_for_status()
    base_task = dict(product="HUAWEI MateBook 14（鸿蒙版）", audience="大学新生", scenario="开学季",
                     platform="xiaohongshu", constraints=["不要提价格"], goal="到店体验", speed="quality")
    cases = [("xiaohongshu", base_task), ("missing-input", {})]
    if not args.quick:
        cases += [(platform, {**base_task, "platform": platform}) for platform in ("wechat_article", "moments", "poster")]
        cases += [("sentence-auto-recommend", {"product": "", "platform": "xiaohongshu", "speed": "quality",
                   "extra": "为经常带电脑去图书馆的大学新生推荐一款华为笔记本，写小红书种草内容，重点便携与接口，不要提价格。"}),
                  ("missing-hero", {**base_task, "product": "HUAWEI MateBook D 16 2024"}),
                  ("revision", {**base_task, "instruction": "写得更生活化，突出背电脑去图书馆的场景，不要提价格。"})]
    report = []
    out = settings.ROOT / "data" / "acceptance" / "latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    for name, task in cases:
        response = client.post("/api/run", json=task)
        response.raise_for_status()
        jid = response.json()["job"]
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            response = client.get("/api/job/" + jid)
            response.raise_for_status()
            snapshot = response.json()
            if snapshot["state"] != "running":
                break
            time.sleep(1)
        else:
            raise TimeoutError(f"{name} 超过 300 秒")
        result = snapshot.get("result") or {}
        assert snapshot["state"] == "done", f"{name}: {snapshot.get('error')}"
        if name == "missing-input":
            assert result.get("status") == "need_info"
        else:
            assert result.get("article", {}).get("title"), f"{name}: missing article"
            assert result.get("evidence", {}).get("facts"), f"{name}: missing evidence"
            assert result.get("verification", {}).get("judge", {}).get("overall"), f"{name}: missing review"
            for image in result.get("images", []):
                url = image.get("url") or image.get("src") or f"/img/{quote(result['model']['id'])}/{quote(image['name'])}"
                if url:
                    assert client.get(url).status_code == 200, f"{name}: inaccessible image"
        row = {"case": name, "job": jid, "status": result.get("status"), "ms": result.get("total_ms"),
               "title": result.get("article", {}).get("title"), "models": result.get("models_used"),
               "flags": result.get("verification", {}).get("remaining", []),
               "judge": result.get("verification", {}).get("judge", {}).get("overall"),
               "image_notice": result.get("image_notice"), "images": len(result.get("images", []))}
        report.append(row)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=False), flush=True)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
