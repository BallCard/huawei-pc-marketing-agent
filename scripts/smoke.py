"""本地冒烟测试：启动服务后运行一次极速任务，检查结果结构。

用法：python -X utf8 scripts/smoke.py [port]
"""
import json
import sys
import time
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7880
BASE = f"http://127.0.0.1:{PORT}"


def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=30))


def main():
    info = get("/api/info")
    print("knowledge base:", info["kb"]["models"], "models;", "writer", info["writer_model"], "judge", info["judge_model"])
    job = post("/api/run", {
        "product": "HUAWEI MateBook 14（鸿蒙版）", "audience": "大学新生", "scenario": "开学季",
        "platform": "xiaohongshu", "goal": "种草", "constraints": [], "extra": "", "speed": "fast",
    })["job"]
    started = time.time()
    while time.time() - started < 150:
        time.sleep(3)
        data = get("/api/job/" + job)
        if data["state"] == "running":
            continue
        result = data.get("result") or {}
        print("state:", data["state"], "| ms:", result.get("total_ms"), "| error:", data.get("error"))
        print("title:", (result.get("article") or {}).get("title"))
        print("images:", [(i.get("kind"), i.get("shows_device")) for i in result.get("images", [])])
        print("models:", result.get("models_used"))
        return 0 if data["state"] == "done" else 1
    print("timeout")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
