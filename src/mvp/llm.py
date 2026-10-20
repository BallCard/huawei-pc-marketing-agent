"""LLM 调用：OpenAI 兼容 chat/completions，含 JSON 解析、重试、视觉输入。"""
import base64
import io
import json
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from . import settings


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    pass


_deadline = ContextVar("generation_deadline", default=None)
_recorder = ContextVar("generation_call_recorder", default=None)


@contextmanager
def budget(deadline, recorder=None):
    token = _deadline.set(deadline)
    record_token = _recorder.set(recorder)
    try:
        yield
    finally:
        _deadline.reset(token)
        _recorder.reset(record_token)


def remaining() -> float:
    end = _deadline.get()
    seconds = settings.LLM_TIMEOUT if end is None else end - time.monotonic()
    if seconds <= 0:
        raise BudgetExceeded("已达到创作时间预算，未完成的审核不能视为通过。")
    return min(settings.LLM_TIMEOUT, seconds)


def _headers(api_key: str | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    key = settings.LLM_API_KEY if api_key is None else api_key
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def chat(messages: list, model: str | None = None, json_mode: bool = False,
         max_tokens: int = 8000, retries: int = 2, role: str = "writer", timeout: float | None = None) -> str:
    config = settings.llm_config(role)
    body = {"model": model or settings.WRITER_MODEL, "messages": messages,
            "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if config["thinking"] != "auto":
        body["thinking"] = {"type": config["thinking"]}
    body.update(config["extra"])
    last = None
    for i in range(retries + 1):
        started = time.monotonic()
        usage, status = {}, "error"
        entry = None
        try:
            request_timeout = min(remaining(), timeout) if timeout is not None else remaining()
            entry = {"role": role, "model": body["model"], "status": "running", "ms": 0,
                     "prompt_tokens": None, "completion_tokens": None}
            recorder = _recorder.get()
            if recorder:
                recorder(entry)
            r = httpx.post(f"{config['base_url']}/chat/completions", json=body,
                           headers=_headers(config["api_key"]), timeout=request_timeout)
            r.raise_for_status()
            response = r.json()
            usage = response.get("usage") or {}
            text = response["choices"][0]["message"].get("content") or ""
            if not text.strip():
                raise LLMError("模型返回空内容")
            status = "ok"
            return text
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            left = remaining()
            if i < retries:
                time.sleep(min(1.5 * (i + 1), left))
        finally:
            if entry is not None:
                entry.update(status=status, ms=int((time.monotonic() - started) * 1000),
                             prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
    raise LLMError(f"LLM 调用失败：{last}")


def parse_json(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


def ask_json(system: str, user: str, model: str | None = None, retries: int = 2, role: str = "writer"):
    """要求模型输出 JSON 对象；解析失败会带着报错重试。"""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = None
    for _ in range(retries + 1):
        raw = chat(msgs, model=model, json_mode=True, role=role)
        try:
            out = parse_json(raw)
            if not isinstance(out, dict):
                raise ValueError("模型必须返回 JSON 对象")
            return out
        except json.JSONDecodeError as e:
            last = e
            msgs += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "上一条不是合法 JSON，请只输出一个 JSON 对象。"}]
    raise LLMError(f"JSON 解析失败：{last}")


def describe_image(path, prompt: str, model: str | None = None, *, role: str = "writer",
                   retries: int = 2, timeout: float | None = None) -> str:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((896, 896))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return chat([{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": url}}]}], model=model, max_tokens=600,
        role=role, retries=retries, timeout=timeout)
