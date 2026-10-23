"""检查美国 VPS 上的 ChatGPT 生图反代：服务、就绪状态与上游鉴权。

只读取本机忽略的 `deploy/gpt-direct/.env` 和 VPS 上的私有环境文件；
不打印 access token，也不修改远端配置。刷新短期令牌后先跑这个脚本，
再跑一次真实海报，避免把“心跳正常”当成“上游可出图”。
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "deploy" / "gpt-direct" / ".env"

REMOTE = r'''
import base64, json, time, urllib.error, urllib.request
key = ""
for line in open("/etc/huazhang-gpt/gateway.env", encoding="utf-8"):
    if line.startswith("GPTWEB_API_KEY="):
        key = line.split("=", 1)[1].strip()
        break

def call(path, auth=False):
    headers = {"Authorization": "Bearer " + key} if auth else {}
    request = urllib.request.Request("http://127.0.0.1:17889" + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status, response.read(500).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(500).decode("utf-8", "replace")
    except Exception as exc:
        return 0, type(exc).__name__

def token_expiry():
    try:
        token = json.load(open("/var/lib/huazhang-gpt/auth.json", encoding="utf-8")).get("access_token") or ""
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=" * (-len(token.split(".")[1]) % 4)))
        return int(payload.get("exp") or 0)
    except Exception:
        return 0

print(json.dumps({
    "health": call("/healthz"),
    "ready": call("/readyz"),
    "upstream": call("/v1/models", True),
    "token_exp": token_expiry(),
    "now": int(time.time()),
}, ensure_ascii=False))
'''


def config() -> dict:
    if not CONFIG.exists():
        raise SystemExit("缺少 deploy/gpt-direct/.env，无法连接 VPS。")
    return dict(line.split("=", 1) for line in CONFIG.read_text(encoding="utf-8-sig").splitlines()
                if "=" in line and not line.strip().startswith("#"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    cfg = config()
    host = cfg.get("GPT_DEPLOY_HOST", "")
    ssh_key = cfg.get("GPT_DEPLOY_SSH_KEY", "")
    if not host or not ssh_key:
        raise SystemExit("deploy/gpt-direct/.env 需要 GPT_DEPLOY_HOST 与 GPT_DEPLOY_SSH_KEY。")
    encoded = base64.b64encode(REMOTE.encode("utf-8")).decode("ascii")
    remote = f'sudo python3 -c "import base64; exec(base64.b64decode(\'{encoded}\').decode())"'
    command = ["ssh", "-i", ssh_key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=15", host, remote]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        print(f"FAIL 无法连接 VPS 或读取反代状态：{result.stderr.strip()[-300:]}", file=sys.stderr)
        return 1
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print("FAIL 反代返回了无法解析的状态。", file=sys.stderr)
        return 1

    health_status, health_body = data["health"]
    ready_status, ready_body = data["ready"]
    upstream_status, upstream_body = data["upstream"]
    ready = False
    try:
        ready = bool(json.loads(ready_body).get("ready"))
    except ValueError:
        pass
    print(f"gateway  /healthz  HTTP {health_status}")
    print(f"gateway  /readyz   HTTP {ready_status}  ready={ready}")
    print(f"upstream /v1/models HTTP {upstream_status}")
    if upstream_status == 200:
        print("PASS ChatGPT 上游鉴权通过，可以继续验证真实海报。")
        return 0
    message = upstream_body.strip()[:300]
    print(f"FAIL 上游未通过：{message}")
    exp = int(data.get("token_exp") or 0)
    if exp:
        days = (exp - int(data.get("now") or 0)) / 86400
        print(f"令牌 JWT 到期剩余约 {days:.1f} 天；即使未到期，上游仍可能已吊销。")
    print("处理：重新取短期 access token → 写入 deploy/gpt-direct/auth.json → "
          "运行 scripts/connect_gpt_account.py → 再跑本脚本。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
