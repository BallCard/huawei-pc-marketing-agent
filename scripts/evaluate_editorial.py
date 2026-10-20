"""12 组 × 三版本真实对照；独立进程隔离缓存，生成匿名文稿与人工评分表。

python -X utf8 scripts/evaluate_editorial.py --variants baseline,prompts,full
基线取当前提交（未提交修改之前），只读导出到忽略的 data/evaluation；不修改工作区。
"""
from __future__ import annotations

import argparse
import csv
import copy
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def worker(args):
    sys.path.insert(0, str(Path(args.source).resolve()))
    from src.mvp import llm, pipeline
    task = json.loads(Path(args.task_file).read_text(encoding="utf-8"))
    calls, lock = [], threading.Lock()
    original = llm.httpx.post

    def measured(*a, **kw):
        started = time.monotonic()
        entry = {"model": kw.get("json", {}).get("model"), "status": "running", "ms": 0}
        with lock:
            calls.append(entry)
        try:
            response = original(*a, **kw)
            entry["status"] = response.status_code
            if response.status_code == 200:
                entry["usage"] = response.json().get("usage", {})
            return response
        except Exception:
            entry["status"] = "error"
            raise
        finally:
            entry["ms"] = int((time.monotonic() - started) * 1000)

    llm.httpx.post = measured
    started = time.monotonic()
    try:
        if args.worker_variant == "baseline":
            result = pipeline.run(task)
        else:
            result = pipeline.run(task, enable_revision=args.worker_variant == "full")
        row = {"result": result}
    except Exception as exc:
        row = {"error": f"{type(exc).__name__}: {exc}"}
    row.update(ms=int((time.monotonic() - started) * 1000), calls=copy.deepcopy(calls))
    Path(args.worker_out).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")


def baseline_source(ref, destination):
    archive = subprocess.run(["git", "archive", "--format=zip", ref], cwd=ROOT, check=True, capture_output=True).stdout
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(destination)
    return destination


def blind_package(rows, output):
    rng = random.Random(4381)
    groups = {}
    for row in rows:
        groups.setdefault(row["case"], []).append(row)
    mapping, ratings = {}, []
    lines = ["# 匿名成稿盲评", "", "按切入点、平台感、自然度、说服力各评 1–5 分；事实错误单独记录。评分前不要打开 unblind.json。", ""]
    n = 0
    for case, samples in groups.items():
        rng.shuffle(samples)
        for row in samples:
            n += 1
            code = f"sample-{n:03d}"
            mapping[code] = {"case": case, "variant": row["variant"]}
            art = row.get("result", {}).get("article") or {}
            lines += [f"## {code} · {case}", "", "原始简报：" + json.dumps(row["task"], ensure_ascii=False), "",
                      "### " + art.get("title", "（无完整稿件）"), "", art.get("lead", ""), ""]
            lines += [b["text"] + "\n" for b in art.get("blocks", []) if b.get("type") == "text"]
            lines += [art.get("cta", ""), " ".join(art.get("tags", [])), ""]
            ratings.append(dict(sample=code, angle="", platform="", naturalness="", persuasion="", factual_errors="", notes=""))
    (output / "blind.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "unblind.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    if ratings:
        with (output / "blind-ratings.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ratings[0].keys())
            writer.writeheader()
            writer.writerows(ratings)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variants", default="baseline,prompts,full")
    p.add_argument("--cases", default="", help="逗号分隔 case id；留空跑全 12 组")
    p.add_argument("--baseline-ref", default="HEAD")
    p.add_argument("--output", default="data/evaluation/editorial")
    p.add_argument("--timeout", type=float, default=150)
    p.add_argument("--source")
    p.add_argument("--task-file")
    p.add_argument("--worker-variant")
    p.add_argument("--worker-out")
    args = p.parse_args()
    if args.worker_variant:
        return worker(args)
    variants = args.variants.split(",")
    if set(variants) - {"baseline", "prompts", "full"}:
        p.error("variants 只能是 baseline,prompts,full")
    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = {v: ROOT for v in variants}
    if "baseline" in variants:
        sources["baseline"] = baseline_source(args.baseline_ref, output / "baseline-source")
    cases = json.loads((ROOT / "tests/fixtures/editorial_cases.json").read_text(encoding="utf-8"))
    selected = set(args.cases.split(",")) if args.cases else None
    rows = []
    env = {**os.environ, "KB_DIR": str(ROOT / "data/kb"), "PYTHONUTF8": "1"}
    # Load existing local configuration safely in each process, including the baseline checkout.
    env["APP_ENV_FILE"] = os.environ.get("APP_ENV_FILE", str(ROOT / ".env"))
    for case in cases:
        if selected and case["id"] not in selected:
            continue
        task = {k: v for k, v in case.items() if k not in ("id", "kind")}
        task_file = output / f"{case['id']}-task.json"
        task_file.write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
        for variant in variants:
            path = output / f"{case['id']}-{variant}.json"
            started = time.monotonic()
            try:
                subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--source", str(sources[variant]),
                                "--task-file", str(task_file), "--worker-variant", variant, "--worker-out", str(path)],
                               cwd=sources[variant], env=env, timeout=args.timeout, check=True, capture_output=True)
                row = json.loads(path.read_text(encoding="utf-8"))
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
                row = {"error": type(exc).__name__, "ms": int((time.monotonic() - started) * 1000), "calls": []}
            row.update(case=case["id"], kind=case["kind"], variant=variant, task=task)
            rows.append(row)
            path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"case": row["case"], "variant": variant, "ms": row["ms"], "calls": len(row["calls"]),
                              "status": row.get("result", {}).get("status"), "error": row.get("error")}, ensure_ascii=False), flush=True)
    blind_package(rows, output)
    print(f"对照结果与匿名评分包：{output}", flush=True)


if __name__ == "__main__":
    main()
