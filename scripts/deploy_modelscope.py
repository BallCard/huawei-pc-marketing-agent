"""发布到指定的魔搭创空间，保持代码隐藏。凭据只从 .env.deploy 读取。"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TARGET = json.loads((ROOT / "deploy/modelscope/target.json").read_text(encoding="utf-8"))
REPO = TARGET["repo_id"]
OWNER, NAME = REPO.split("/")
BASE = "https://modelscope.cn/openapi/v1"


def config():
    return dict(line.split("=", 1) for line in (ROOT / ".env.deploy").read_text(encoding="utf-8-sig").splitlines()
                if "=" in line and not line.strip().startswith("#"))


def api(method, path, *, payload=None, allow_missing=False):
    response = CLIENT.request(method, BASE + path, json=payload)
    result = response.json()
    if allow_missing and response.status_code == 404:
        return None
    if response.status_code >= 400 or result.get("success") is False:
        raise RuntimeError(f"ModelScope {method} {path}: HTTP {response.status_code}; {result.get('message', 'request failed')}")
    return result.get("data", result)


def git(args, cwd, env=None):
    result = subprocess.run(["git", *args], cwd=cwd, env=env, text=True, encoding="utf-8",
                            errors="replace", capture_output=True)
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr[-1500:]}")
    return result.stdout.strip()


def show_status():
    detail = api("GET", f"/studios/{REPO}")
    folder = ROOT / "data" / "deploy"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "modelscope-status.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    # Studio details contain no secret values; keep console output focused on runtime state.
    print(json.dumps(detail, ensure_ascii=False)[:8000], flush=True)


def deploy():
    cfg = config()
    source_commit = git(["rev-parse", "HEAD"], ROOT)
    visibility = TARGET["visibility"]
    if visibility not in ("private", "protected"):
        raise RuntimeError("带资料包的部署仅允许 private 或 protected，不能公开代码仓库")
    if not cfg.get("AUTH_USERNAME") or not cfg.get("AUTH_PASSWORD"):
        raise RuntimeError("部署前必须配置演示访问账号和密码")
    user = api("GET", "/users/me")
    if user.get("username", "").lower() != OWNER.lower():
        raise RuntimeError("魔搭登录账号与 target.json 的 owner 不一致")
    hardware = api("GET", "/studios/hardware?sdk_type=docker").get("hardware", [])
    free = next((item for item in hardware if item.get("resource_type") == "free"), None)
    if not free:
        raise RuntimeError("当前没有免费 Docker 资源；未选择任何付费资源")
    detail = api("GET", f"/studios/{REPO}", allow_missing=True)
    if detail is None:
        detail = api("POST", "/studios", payload={"owner": OWNER, "repo_name": NAME,
                     "sdk_type": "docker", "visibility": visibility, "hardware": free["name"],
                     "display_name": "华章有据", "description": "基于产品知识库的华为电脑营销图文工作台"})
        print("已创建代码隐藏的 Docker 创空间，资源：" + free["name"], flush=True)
    elif detail.get("visibility") != visibility:
        api("PATCH", f"/studios/{REPO}/settings", payload={"visibility": visibility})
        print("创空间访问模式：" + visibility + "（代码保持隐藏）", flush=True)
    # Never copy credentials, task results, or unrelated files into the Studio source checkout.
    tools_dir = ROOT / "data" / "deploy" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    askpy = tools_dir / "git_askpass.py"
    askpy.write_text("import os,sys\nprint('oauth2' if 'username' in ' '.join(sys.argv[1:]).lower() else os.environ['MODELSCOPE_GIT_TOKEN'])\n", encoding="utf-8")
    askcmd = tools_dir / "git_askpass.cmd"
    askcmd.write_text(f'@echo off\r\n"{sys.executable}" "{askpy}" %*\r\n', encoding="utf-8")
    env = {**os.environ, "MODELSCOPE_GIT_TOKEN": cfg["MODELSCOPE_API_KEY"].strip(),
           "GIT_ASKPASS": str(askcmd), "GIT_TERMINAL_PROMPT": "0",
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": ""}
    checkout = ROOT / "data" / "deploy" / "modelscope"
    remote = f"https://oauth2@modelscope.cn/studios/{REPO}.git"
    if not checkout.exists():
        git(["clone", remote, str(checkout)], ROOT, env)
    else:
        if git(["remote", "get-url", "origin"], checkout) != remote:
            raise RuntimeError("部署工作目录的远端与目标不一致，已停止")
        git(["pull", "--ff-only"], checkout, env)
    # Deploy the recorded commit, even when another chat is editing this checkout.
    archive = subprocess.run(["git", "archive", "--format=zip", source_commit], cwd=ROOT,
                             capture_output=True, check=True)
    with zipfile.ZipFile(io.BytesIO(archive.stdout)) as source:
        source.extractall(checkout)
    shutil.copy2(checkout / "deploy/modelscope/Dockerfile", checkout / "Dockerfile")
    shutil.copy2(checkout / "deploy/modelscope/README.md", checkout / "README.md")
    (checkout / ".dockerignore").write_text(".git\n.env*\nmodel.txt\ndata\n**/__pycache__\n", encoding="utf-8")
    bundle = checkout / "deployment-data"
    kb_dir = Path(cfg.get("KB_DIR") or ROOT / "data/kb")
    cache_dir = Path(cfg.get("CACHE_DIR") or ROOT / "data/cache")
    shutil.copytree(kb_dir, bundle / "kb", dirs_exist_ok=True)
    (bundle / "cache").mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_dir / "vision.json", bundle / "cache/vision.json")
    (checkout / "deployment-source.json").write_text(json.dumps({"source_commit": source_commit}, indent=2), encoding="utf-8")
    git(["add", "--all"], checkout)
    git(["add", "--force", "deployment-data"], checkout)
    # Reject any accidentally tracked secret files, independently of gitignore.
    tracked = git(["ls-files"], checkout).splitlines()
    if any(Path(name).name.startswith(".env") and Path(name).name != ".env.example" or Path(name).name == "model.txt" for name in tracked):
        raise RuntimeError("部署清单包含本地凭据文件，已停止")
    if git(["status", "--porcelain"], checkout):
        git(["-c", "user.name=BallCard", "-c", "user.email=BallCard@users.noreply.github.com",
             "commit", "-m", f"Deploy Huazhang Youju {source_commit[:8]}"], checkout)
    git(["push", "origin", "HEAD:master"], checkout, env)
    print("私有源码与资料包已同步，源代码版本：" + source_commit[:8], flush=True)
    variables = {k: v for k, v in cfg.items() if k.startswith(("LLM_", "FAST_", "WRITER_", "JUDGE_"))
                 or k in ("AUTH_USERNAME", "AUTH_PASSWORD", "MAX_CONCURRENT_JOBS")}
    variables.update(HOST="0.0.0.0", PORT="7860", COOKIE_SECURE="1", KB_BACKEND="local",
                     KB_DIR="/app/data/kb", CACHE_DIR="/app/data/cache",
                     JOB_DB="/mnt/workspace/huazhang-youju/jobs.sqlite3")
    for kind in ("variables", "secrets"):
        current = api("GET", f"/studios/{REPO}/{kind}")
        entries = current.get(kind, current.get("items", [])) if isinstance(current, dict) else current
        existing = {item.get("key") for item in (entries or []) if isinstance(item, dict)}
        for key, value in variables.items():
            secret = key.endswith("API_KEY") or key == "AUTH_PASSWORD"
            if secret != (kind == "secrets"):
                continue
            api("PUT" if key in existing else "POST", f"/studios/{REPO}/{kind}", payload={"key": key, "value": value})
    print("运行变量与 Secrets 已配置（未打印密钥）。", flush=True)
    print(json.dumps(api("POST", f"/studios/{REPO}/deploy"), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "status", "inspect"))
    args = parser.parse_args()
    cfg = config()
    CLIENT = httpx.Client(headers={"Authorization": "Bearer " + cfg["MODELSCOPE_API_KEY"].strip()}, timeout=60)
    try:
        if args.action == "deploy":
            deploy()
        elif args.action == "inspect":
            print(json.dumps(api("GET", f"/studios/{REPO}", allow_missing=True), ensure_ascii=False))
        else:
            show_status()
    finally:
        CLIENT.close()
