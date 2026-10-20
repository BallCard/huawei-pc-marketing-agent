"""Outbound-only poster worker. Account credentials stay in the local Go gateway."""
import base64
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ["POSTER_WORKER_URL"].rstrip("/")
KEY = os.environ["POSTER_WORKER_TOKEN"]
LOCAL_KEY = os.environ["GPTWEB_API_KEY"]
LOCAL = "http://127.0.0.1:17889"
STATE = Path(os.environ.get("POSTER_WORKER_STATE", "/var/lib/huazhang-poster-worker")) / "delivery.json"
READY = False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect())
parsed = urllib.parse.urlsplit(BASE)
if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path:
    raise RuntimeError("POSTER_WORKER_URL must be an HTTPS origin")


def request(url, data=None, headers=None, timeout=25, limit=29*1024*1024):
    req = urllib.request.Request(url, data=data, headers={"User-Agent":"Huazhang-Poster-Worker/1", **(headers or {})})
    with OPENER.open(req, timeout=timeout) as response:
        raw = response.read(limit+1)
        if len(raw) > limit:
            raise ValueError("oversized response")
        return json.loads(raw)


def remote(path, body):
    return request(BASE+"/api/poster-worker/"+path, json.dumps(body).encode(),
                   {"Content-Type":"application/json", "X-Poster-Worker-Key":KEY})


def ready():
    try:
        request(LOCAL+"/readyz", headers={"Authorization":"Bearer "+LOCAL_KEY}, timeout=8, limit=65536)
        return True
    except Exception:
        return False


def heartbeat():
    while True:
        try:
            remote("heartbeat", {"ready":READY})
        except Exception:
            pass
        time.sleep(10)


def persist(delivery):
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(delivery, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(STATE)


def generate(task):
    payload = task["payload"]
    refs = payload.get("images")
    if not isinstance(refs,list) or len(refs) != 2 or not isinstance(payload.get("prompt"),str):
        raise ValueError("invalid poster payload")
    boundary = "poster-"+secrets.token_hex(12)
    parts = []
    for key,value in {"prompt":payload["prompt"], "model":"auto", "n":"1", "response_format":"b64_json"}.items():
        parts.append(("--"+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n').encode())
    for index,ref in enumerate(refs):
        if not isinstance(ref,str) or not ref.startswith("data:image/jpeg;base64,") or len(ref)>8*1024*1024:
            raise ValueError("invalid reference")
        data=base64.b64decode(ref.split(",",1)[1],validate=True)
        parts.append(("--"+boundary+'\r\nContent-Disposition: form-data; name="image"; filename="reference-'+str(index)+'.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode()+data+b"\r\n")
    parts.append(("--"+boundary+"--\r\n").encode())
    result=request(LOCAL+"/v1/images/edits", b"".join(parts),
        {"Authorization":"Bearer "+LOCAL_KEY, "Content-Type":"multipart/form-data; boundary="+boundary}, timeout=570)
    rows=result.get("data") or []
    image=rows[0].get("b64_json") if rows and isinstance(rows[0],dict) else None
    if not isinstance(image,str) or not image or len(image)>28*1024*1024:
        raise ValueError("no image returned")
    return image


def main():
    global READY
    reported = None
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        try:
            if STATE.exists():
                delivery=json.loads(STATE.read_text())
                body={"claim_token":delivery["claim_token"]}
                if delivery.get("image"):
                    body["image"]=delivery["image"]
                else:
                    body["error"]=delivery.get("error") or "generation_failed"
                try:
                    remote(delivery["id"]+"/result", body)
                except urllib.error.HTTPError as exc:
                    if exc.code == 400 and delivery.get("image"):
                        persist({"id":delivery["id"], "claim_token":delivery["claim_token"], "error":"invalid_image"})
                    raise
                STATE.unlink()
                print("Poster result receipt accepted", flush=True)
                continue
            READY=ready()
            remote("heartbeat", {"ready":READY})
            if READY != reported:
                print("Private channel connected; account configured="+str(READY).lower(), flush=True)
                reported = READY
            if not READY:
                time.sleep(10); continue
            task=remote("claim", {}).get("task")
            if not task:
                time.sleep(3); continue
            # Save receipt before submitting. On restart, report interruption, never regenerate.
            delivery={"id":task["id"], "claim_token":task["claim_token"], "error":"generation_failed"}
            persist(delivery)
            try:
                delivery={"id":task["id"], "claim_token":task["claim_token"], "image":generate(task)}
            except TimeoutError:
                delivery["error"]="generation_timeout"
            except ValueError:
                delivery["error"]="invalid_image"
            except Exception:
                delivery["error"]="generation_failed"
            persist(delivery)
        except Exception:
            # Only connection/receipt delivery is retried. generate() is never retried.
            time.sleep(10)


if __name__ == "__main__":
    main()
