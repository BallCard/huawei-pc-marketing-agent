"""命令行跑一次任务，便于调试：python -X utf8 -m src.mvp.cli --product ... --platform xiaohongshu"""
import argparse
import json
import sys

from . import pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="")
    ap.add_argument("--audience", default="")
    ap.add_argument("--scenario", default="")
    ap.add_argument("--platform", default="xiaohongshu")
    ap.add_argument("--goal", default="")
    ap.add_argument("--constraints", default="")
    ap.add_argument("--extra", default="")
    ap.add_argument("--instruction", default="")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    a = ap.parse_args()
    task = {"product": a.product, "audience": a.audience, "scenario": a.scenario, "platform": a.platform,
            "goal": a.goal, "extra": a.extra,
            "constraints": [c for c in a.constraints.replace("，", ",").split(",") if c.strip()]}

    def cb(u):
        event = (u.get("events") or [{}])[-1]
        if event.get("label"):
            print(f"  · {event['label']}", file=sys.stderr)

    r = pipeline.run(task, a.instruction or None, on_update=cb)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        return
    print("STATUS:", r["status"])
    if r["status"] in ("need_info", "budget_exceeded"):
        print("追问:", r["questions"])
        return
    art = r["article"]
    print("型号:", r["model"]["name"], r["model"]["mode"])
    print("权重:", r["scene_judgement"]["weights"])
    print("\n# ", art["title"])
    print(art["lead"])
    for b in art["blocks"]:
        print(b["text"] if b["type"] == "text" else f"[图 {b['image_id']}: {b['caption']}]")
    print("CTA:", art["cta"], art["tags"])
    print("\n核验剩余:", r["verification"]["remaining"])
    print("修订轮次:", [(x["round"], len(x["issues"])) for x in r["verification"]["repair_rounds"]])
    print("待确认:", r["verification"]["pending_confirm"])
    print("总耗时 ms:", r["total_ms"])


if __name__ == "__main__":
    main()
