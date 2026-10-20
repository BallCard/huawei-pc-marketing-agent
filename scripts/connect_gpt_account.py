"""将本人提供的短期网页 access token 安全安装到指定 VPS；不读取 Codex 或浏览器凭据。"""
import argparse
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        # 不回显凭据文件或网络响应正文。
        raise SystemExit("账号文件安装失败，请检查 SSH 连接与目标文件权限。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", type=Path, default=ROOT/"deploy/gpt-direct/auth.json")
    args = parser.parse_args()
    config = dict(line.split("=",1) for line in (ROOT/"deploy/gpt-direct/.env").read_text(encoding="utf-8-sig").splitlines()
                  if "=" in line and not line.strip().startswith("#"))
    host = config["GPT_DEPLOY_HOST"]
    if host.startswith("-") or any(c.isspace() for c in host):
        raise SystemExit("无效的 SSH 目标。")
    ssh = ["-i",config["GPT_DEPLOY_SSH_KEY"],"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=12"]
    raw = args.file.read_text(encoding="utf-8-sig").strip()
    if len(raw) > 65536:
        raise SystemExit("账号文件过大。只需要 access token，不需要 Cookie 或完整浏览器资料。")
    doc = json.loads(raw) if raw.startswith("{") else {"access_token":raw}
    token = doc.get("access_token") or doc.get("accessToken")
    if not isinstance(token,str) or len(token)<80 or any(c.isspace() for c in token):
        raise SystemExit("账号文件没有有效的 access token。")
    # 不传 refresh token、密码、Cookie、个人资料或其他程序的登录文件。
    credential = {"access_token":token}
    remote = "/tmp/huazhang-auth-"+secrets.token_hex(12)
    with tempfile.TemporaryDirectory(prefix="huazhang-auth-") as folder:
        local = Path(folder)/"auth.json"
        fd = os.open(local, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(credential,stream)
        run(["ssh",*ssh,host,f"umask 077; mkdir {remote}"])
        try:
            run(["scp",*ssh,str(local),host+":"+remote+"/auth.json"])
            run(["ssh",*ssh,host,
                 f"sudo install -o huazhang-gpt -g huazhang-gpt -m 600 {remote}/auth.json /var/lib/huazhang-gpt/auth.json && sudo systemctl restart huazhang-gpt-web.service"])
        finally:
            run(["ssh",*ssh,host,f"rm -f {remote}/auth.json; rmdir {remote}"])
    print("短期网页凭据已安装；仅重启独立生图服务。尚需真实海报验收。")


if __name__ == "__main__":
    main()
