"""离线给知识库里的产品图打视觉标签，写入 data/cache/vision.json（不入库）。

用法：python -X utf8 -m src.mvp.tag_images [--force] [--model gemini-3.8-flash-high]
选图只看文字图注会选到 logo、示意图；标签让选图能区分“整机/局部/场景/示意/logo”，
并在型号根本没有整机图时明确告警，而不是静默出一篇没有电脑的图文。
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from . import llm, settings
from .kb import get_kb

KINDS = ("device", "device_scene", "detail", "screen_ui", "diagram", "logo", "people", "other")

PROMPT = """你在为华为笔记本电脑的营销图库做标注。只描述画面里真实可见的内容，不要猜型号、参数或颜色名之外的信息。
只输出一个 JSON 对象：
{"kind": "device|device_scene|detail|screen_ui|diagram|logo|people|other",
 "shows_device": true/false,
 "angle": "front|three_quarter|top|side|open|closed|none",
 "desc": "一句话中文描述画面",
 "color": "机身主色，没有则空串"}
kind 取值：device=干净背景下的笔记本整机；device_scene=笔记本出现在真实使用场景/人物手持；detail=机身局部特写；
screen_ui=主要是屏幕里的界面或壁纸；diagram=功能示意图/信息图；logo=芯片或品牌标志；people=以人物为主、看不清设备；other=其他。
shows_device 表示画面里能清楚看到笔记本电脑整机或其大部分。"""


def tag_one(path, model: str) -> dict:
    raw = llm.describe_image(path, PROMPT, model=model)
    try:
        d = llm.parse_json(raw)
    except Exception:  # noqa: BLE001
        d = {"kind": "other", "shows_device": False, "angle": "none", "desc": raw.strip()[:80], "color": ""}
    if d.get("kind") not in KINDS:
        d["kind"] = "other"
    d["shows_device"] = bool(d.get("shows_device"))
    d["consistent"] = True
    d["model"] = model
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default=settings.WRITER_MODEL)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    kb = get_kb()
    f = settings.CACHE_DIR / "vision.json"
    cache = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    todo = []
    for m in kb.models():
        for im in kb.load(m.id).images:
            if a.force or im.id not in cache:
                todo.append(im)
    print(f"待标注 {len(todo)} 张（已有 {len(cache)}）")

    def work(im):
        try:
            return im.id, tag_one(im.path, a.model)
        except Exception as e:  # noqa: BLE001
            return im.id, {"error": str(e)}

    f.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for n, (k, v) in enumerate(ex.map(work, todo), 1):
            if "error" not in v:
                cache[k] = v
            print(f"[{n}/{len(todo)}] {k[:48]} -> {v.get('kind', v.get('error'))}")
            f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print("完成，写入", f)


if __name__ == "__main__":
    main()
