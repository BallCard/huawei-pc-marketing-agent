"""整图海报：内置审核参考、可切换生图提供方、实际成图独立核验。"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import time
import unicodedata
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw, ImageOps, ImageFilter

from . import llm, settings
from .kb import get_kb
from .progress import Trace

REFERENCES = settings.PKG / "web" / "poster-references"


def references() -> list[dict]:
    rows = json.loads((REFERENCES / "manifest.json").read_text(encoding="utf-8"))
    for row in rows:
        path = REFERENCES / row["file"]
        if path.parent != REFERENCES or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("内置参考图与用户审核版本不一致。")
    return rows


def text_approved(result: dict) -> bool:
    return ((result.get("verification") or {}).get("state") == "passed" or
            (result.get("human_review") or {}).get("state") == "adopted" or
            (result.get("text_human_review") or {}).get("state") == "adopted")


def visible_copy(result: dict) -> list[str]:
    article = result["article"]
    lines = ["HUAWEI", result["model"]["name"], article.get("title", ""), article.get("lead", "")]
    lines.extend(b["text"] for b in article.get("blocks", []) if b.get("type") == "text")
    lines.append(article.get("cta") or "到店体验真机")
    # 本版本不接入真实门店二维码，CTA 必须是能执行的到店动作。
    lines = [re.sub(r"扫码或向店员咨询|扫码咨询|扫码了解(?:更多)?", "向店员咨询", line) for line in lines]
    return list(dict.fromkeys(line.strip() for line in lines if line.strip()))


def prepare(result: dict, folder: Path) -> dict:
    from . import verify, web_images
    kb = get_kb()
    doc = kb.load(result["model"]["id"])
    candidates = doc.images + web_images.cached_images(doc, require_fresh=False)
    candidates = [im for im in candidates if im.kind in ("device", "device_scene") and
                  im.shows_device is not False and verify.image_model_ok(im, doc)]
    if not candidates:
        raise ValueError("该型号暂无已核验的整机图，补充产品参考后才能生图。")
    candidates.sort(key=lambda im: (bool(re.search(r"手写笔|标语|文字|宣传|悬停", im.vision)), im.kind != "device"))
    product = candidates[0]
    task = result.get("task") or {}
    scene = result.get("scene_judgement") or {}
    wants_green = bool(re.search(r"学生|校园|开学|教室|图书馆|宿舍", " ".join(str(task.get(k) or "") for k in ("audience", "scenario", "extra"))))
    ref = next(row for row in references() if row["id"] == ("fresh-green" if wants_green else "minimal-product"))
    folder.mkdir(parents=True, exist_ok=True)
    board = Image.new("RGB", (960, 1280), "#f8f8f5")
    draw = ImageDraw.Draw(board)
    for label, path, box in (("STYLE", REFERENCES / ref["file"], (25, 140, 425, 1100)),
                             ("PRODUCT", product.path, (460, 140, 935, 1100))):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((box[2] - box[0], box[3] - box[1]))
        x = box[0] + (box[2] - box[0] - image.width) // 2
        y = box[1] + (box[3] - box[1] - image.height) // 2
        board.paste(image, (x, y), image)
        draw.text((box[0], 95), label, fill="#25241f", font_size=25)
    board_path = folder / "reference-board.png"
    board.save(board_path)
    # 原参考完整留存；模型只收到模糊的色彩/构图参考，减少旧文字和旧机型泄漏。
    style_path = folder / "style-reference.png"
    with Image.open(REFERENCES / ref["file"]) as original:
        style = original.convert("RGB")
    style.thumbnail((320, 480))
    style = style.filter(ImageFilter.GaussianBlur(radius=18))
    style.save(style_path)
    copy_lines = visible_copy(result)
    payload = {"逐字文案": copy_lines, "场景": scene.get("user_problem") or task.get("scenario", ""), "参考风格": ref["style"]}
    old = (result.get("poster") or {}).get("review") or {}
    if old.get("problems"):
        payload["重生要求"] = [str(p.get("direction") or p.get("detail", ""))[:60] for p in old["problems"][:2]]
    prompt = ((settings.PKG / "prompts" / "poster-image.md").read_text(encoding="utf-8") + "\n" + json.dumps(payload, ensure_ascii=False) +
              "\n图1是唯一产品外观依据，保持其配色、形态、接口和视角。图2只借鉴配色与留白，把旧海报的所有文字、日期、Logo及产品全部替换。" +
              "不要拼贴两张图，不要广告牌、灯箱、照片外框或街景；画布本身就是最终海报。不要新增文字、价格、二维码、配件或未获证实的能力。")
    return {"reference": ref, "reference_path":style_path, "product_path": product.path, "product_image": product.id,
            "style_input_sha256":hashlib.sha256(style_path.read_bytes()).hexdigest(),
            "board_path": board_path, "copy": copy_lines, "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


def data_url(path: Path, max_side=1600) -> str:
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    image.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=94)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def save_image(content: bytes, folder: Path) -> dict:
    if len(content) > 20 * 1024 * 1024:
        raise llm.LLMError("生成图片超过大小限制。")
    try:
        with Image.open(io.BytesIO(content)) as original:
            if original.width * original.height > 20_000_000:
                raise llm.LLMError("生成图片尺寸超过限制。")
            image = ImageOps.exif_transpose(original).convert("RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        raise llm.LLMError("生成服务返回的图片无法解析。") from exc
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / "poster.png"
    temporary = folder / "poster.tmp"
    image.save(temporary, format="PNG")
    temporary.replace(output)
    return {"sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "width":image.width, "height":image.height}


def generate_web_proxy(prepared: dict, folder: Path, on_activity, deadline: float) -> dict:
    """两个网页反代的参考图字段独立适配，输出都使用 b64_json。"""
    if not settings.POSTER_IMAGE_API_KEY:
        raise llm.LLMError("尚未配置生图反代访问密钥，请配置 POSTER_IMAGE_API_KEY。")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise llm.BudgetExceeded("海报生成等待已超时。")
    refs = [data_url(prepared["product_path"]), data_url(prepared["reference_path"])]
    body = {"model":settings.POSTER_IMAGE_MODEL, "prompt":prepared["prompt"], "n":1, "size":"960x1280",
            "response_format":"b64_json"}
    chatgpt = settings.POSTER_IMAGE_PROVIDER == "chatgpt_web_proxy"
    if chatgpt:
        body.update(reference_images=refs, aspect_ratio="3:4", thinking_mode="instant")
    else:
        body["image"] = refs
    on_activity({"provider_status":"RUNNING", "label":"正在等待网页生图反代返回图片"})
    authorization = f"Bearer {settings.POSTER_IMAGE_API_KEY}"
    if settings.POSTER_IMAGE_AUTH_MODE == "basic":
        authorization = "Basic " + base64.b64encode(("api:" + settings.POSTER_IMAGE_API_KEY).encode()).decode()
    try:
        # 同步接口只提交一次；超时也不盲目重发，不声称能恢复未提供 ID 的上游任务。
        with httpx.Client(follow_redirects=False) as client:
            with client.stream("POST", settings.POSTER_IMAGE_BASE_URL + "/images/generations", json=body,
                               headers={"Authorization":authorization}, timeout=remaining) as response:
                if not response.is_success:
                    raise llm.LLMError(f"网页生图反代未成功（HTTP {response.status_code}），请检查会话、网络或额度。")
                encoded_response = bytearray()
                for chunk in response.iter_bytes():
                    encoded_response.extend(chunk)
                    if len(encoded_response) > 29 * 1024 * 1024:
                        raise llm.LLMError("反代返回图片超过大小限制。")
        result = json.loads(encoded_response)
        rows = result.get("data") or []
        encoded_image = rows[0].get("b64_json") if rows and isinstance(rows[0], dict) else None
        if not isinstance(encoded_image, str) or not encoded_image:
            raise llm.LLMError("网页反代没有返回 b64_json 图片，不能将文字回复视为出图成功。")
        content = base64.b64decode(encoded_image, validate=True)
    except httpx.TimeoutException as exc:
        raise llm.BudgetExceeded("网页生图请求已超时；上游可能仍在生成，请确认后手动重试。") from exc
    except (ValueError, TypeError) as exc:
        raise llm.LLMError("网页反代返回的图片数据无法解析。") from exc
    generated = save_image(content, folder)
    if chatgpt:
        applied = result.get("applied") or {}
        generated["provider_applied"] = {k:applied[k] for k in ("references_attached", "aspect_ratio", "quality", "thinking_mode") if k in applied}
        if applied.get("references_attached") != len(refs):
            # 保留已消耗额度获得的图，但不能把无参考图生成静默算作正常完成。
            generated["reference_upload_warning"] = "网页反代未确认两张参考图均已上传，成图需人工复核。"
    on_activity({"provider_status":"SUCCEED", "label":"网页生图图片已返回"})
    return generated


def generate_private_worker(prepared: dict, folder: Path, on_activity, deadline: float, existing_task_id=None) -> dict:
    from .poster_channel import PosterChannel
    channel = PosterChannel(settings.JOB_DB)
    if not settings.POSTER_WORKER_TOKEN:
        raise llm.LLMError("生图服务尚未配置私有连接。")
    if not existing_task_id and not channel.worker_ready():
        raise llm.LLMError("生图账号连接尚未就绪，请完成账号连接后重试。")
    task_id = existing_task_id or channel.create(folder.name, {"prompt":prepared["prompt"], "model":"auto",
        "images":[data_url(prepared["product_path"]),data_url(prepared["reference_path"])]},
        time.time() + max(0, deadline-time.monotonic()))
    previous = None
    on_activity({"task_id":task_id, "provider_status":"PENDING", "label":"海报任务已进入私有生图队列"})
    while time.monotonic() < deadline:
        task = channel.get(task_id)
        if not task:
            raise llm.LLMError("原生图任务已不可用，请手动重试。")
        if task["state"] != previous:
            on_activity({"task_id":task_id, "provider_status":task["state"].upper(), "label":"正在生成整张海报" if task["state"] == "running" else "正在等待私有生图服务"})
            previous = task["state"]
        if task["state"] == "done":
            original = settings.POSTER_DIR / task["job_id"] / "poster.png"
            if not original.exists() or hashlib.sha256(original.read_bytes()).hexdigest() != task["result"]["sha256"]:
                raise llm.LLMError("已交付图片与任务摘要不一致。")
            folder.mkdir(parents=True, exist_ok=True)
            if original != folder / "poster.png":
                shutil.copyfile(original, folder / "poster.png")
            return {"task_id":task_id, **task["result"]}
        if task["state"] == "error":
            raise llm.LLMError(task["error"])
        time.sleep(min(3,max(0,deadline-time.monotonic())))
    raise llm.BudgetExceeded("海报生成等待已超时，可继续查询原任务；本次不会自动重新提交。")


def generate(prepared: dict, folder: Path, on_activity, deadline: float, existing_task_id: str | None = None) -> dict:
    if settings.POSTER_IMAGE_PROVIDER == "private_worker":
        return generate_private_worker(prepared, folder, on_activity, deadline, existing_task_id)
    if settings.POSTER_IMAGE_PROVIDER in ("gemini_web_proxy", "chatgpt_web_proxy"):
        return generate_web_proxy(prepared, folder, on_activity, deadline)
    if not settings.POSTER_IMAGE_API_KEY:
        raise llm.LLMError("尚未配置魔搭生图凭据，请配置 POSTER_IMAGE_API_KEY 后重试。")
    base = settings.POSTER_IMAGE_BASE_URL
    headers = {"Authorization": f"Bearer {settings.POSTER_IMAGE_API_KEY}", "Content-Type": "application/json"}
    multi_reference = settings.POSTER_IMAGE_MODEL != "Qwen/Qwen-Image-Edit"
    image_input = ([data_url(prepared["product_path"]), data_url(prepared["reference_path"])] if multi_reference else data_url(prepared["board_path"]))
    body = {"model": settings.POSTER_IMAGE_MODEL, "prompt": prepared["prompt"], "image_url": image_input, "size": "960x1280"}

    def left():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise llm.BudgetExceeded("海报生成等待已超时。已保留文案，可手动重新生图。")
        return min(30, seconds)

    with httpx.Client(follow_redirects=True) as client:
        # 提交只执行一次，响应丢失时也不盲目重发，避免重复生成。
        task_id = existing_task_id
        if not task_id:
            response = client.post(base + "/images/generations", json=body,
                                   headers={**headers, "X-ModelScope-Async-Mode": "true"}, timeout=left())
            if not response.is_success:
                raise llm.LLMError(f"魔搭生图提交未成功（HTTP {response.status_code}），请核对模型权限或配额。")
            task_id = response.json().get("task_id")
        if not task_id:
            raise llm.LLMError("魔搭未返回有效的生图任务 ID。")
        previous = None
        on_activity({"task_id": task_id, "provider_status": "SUBMITTED", "label": "继续查询已有生图任务" if existing_task_id else "海报任务已提交"})
        while True:
            try:
                response = client.get(base + f"/tasks/{task_id}", headers={**headers, "X-ModelScope-Task-Type": "image_generation"}, timeout=left())
                if response.status_code in (429, 500, 502, 503, 504):
                    time.sleep(min(5, left())); continue
                if not response.is_success:
                    raise llm.LLMError(f"无法读取魔搭生图任务（HTTP {response.status_code}）。")
                result = response.json()
            except (httpx.TimeoutException, httpx.NetworkError):
                time.sleep(min(5, left())); continue
            status = result.get("task_status", "UNKNOWN")
            if status != previous:
                on_activity({"task_id": task_id, "provider_status": status,
                             "label": {"PENDING":"模型任务等待中", "RUNNING":"正在生成整张海报", "SUCCEED":"海报已生成"}.get(status, "正在等待模型结果")})
                previous = status
            if status == "SUCCEED":
                urls = result.get("output_images") or []
                if not urls:
                    raise llm.LLMError("魔搭任务已结束，但没有返回海报图片。")
                url = urls[0]
                if urlsplit(url).scheme != "https":
                    raise llm.LLMError("魔搭返回的图片地址格式不受支持。")
                # 图片下载不携带模型接口的 Authorization。
                with client.stream("GET", url, timeout=left()) as download:
                    download.raise_for_status()
                    buf = io.BytesIO()
                    for chunk in download.iter_bytes():
                        buf.write(chunk)
                        if buf.tell() > 20 * 1024 * 1024:
                            raise llm.LLMError("生成图片超过大小限制。")
                return {"task_id": task_id, **save_image(buf.getvalue(), folder)}
            if status in ("FAILED", "CANCELED", "CANCELLED"):
                raise llm.LLMError("魔搭未能生成这张海报。文案已保留，可手动重新生图。")
            time.sleep(min(5, left()))


def normalized(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", unicodedata.normalize("NFKC", text)).lower()


def inspect_image(result: dict, prepared: dict, path: Path, feedback: list[str] | None = None) -> dict:
    # 第一轮不给型号、目标文案或产品事实，避免模型把提示词抄成“已识别文字”。
    transcription = llm.parse_json(llm.chat([{"role":"user", "content":[
        {"type":"text", "text":"只识别这张图片中实际可见的营销文字，逐行原样转录。不要推测、补字或补全产品型号。忽略键盘按键和微小系统图标。看不清的行写入 unreadable。只输出 JSON：{\"observed_texts\":[\"实际原文\"],\"unreadable\":[\"无法辨认的位置\"]}"},
        {"type":"image_url", "image_url":{"url":data_url(path)}}]}], model=settings.POSTER_REVIEW_MODEL,
        role="poster_review", json_mode=True, max_tokens=1800, retries=0, timeout=settings.POSTER_REVIEW_TIMEOUT))
    if not isinstance(transcription, dict) or not isinstance(transcription.get("observed_texts"), list) or not all(isinstance(t,str) for t in transcription["observed_texts"]):
        raise llm.LLMError("成图审核未返回实际文字转录。")
    payload = {"批准文案": prepared["copy"], "原始需求": result.get("task"), "型号": result["model"],
               "产品事实": result.get("evidence", {}).get("facts", []), "独立文字转录":transcription}
    if feedback:
        payload["用户反馈（不是产品事实依据）"] = feedback
    raw = llm.chat([{"role":"system", "content":(settings.PKG / "prompts" / "poster-review.md").read_text(encoding="utf-8")},
                    {"role":"user", "content":[{"type":"text", "text":json.dumps(payload, ensure_ascii=False)},
                     {"type":"image_url", "image_url":{"url":data_url(path)}},
                     {"type":"image_url", "image_url":{"url":data_url(prepared["product_path"])}}]}],
                   model=settings.POSTER_REVIEW_MODEL, role="poster_review", json_mode=True,
                   max_tokens=3000, retries=0, timeout=settings.POSTER_REVIEW_TIMEOUT)
    review = llm.parse_json(raw)
    if not isinstance(review, dict):
        raise llm.LLMError("成图审核未返回有效结论。")
    problems = review.get("problems")
    if not isinstance(problems, list) or not all(isinstance(p, dict) and p.get("detail") for p in problems):
        raise llm.LLMError("成图审核问题记录不完整。")
    texts = transcription["observed_texts"]
    review["observed_texts"] = texts
    for position in transcription.get("unreadable") or []:
        problems.append({"where":"poster", "index":-1, "type":"readability", "quote":str(position),
                         "detail":"独立文字识别未能辨认此处，不能视为文案完整。", "direction":"提高文字可读性后重新核验。"})
    actual = normalized("".join(texts))
    for expected in prepared["copy"]:
        if normalized(expected) not in actual:
            problems.append({"where":"poster", "index":-1, "type":"text", "quote":expected,
                             "detail":"成图文字转录未完整匹配这句批准文案，需检查错字、缺字或可读性。", "direction":"确保原句与限定条件完整清晰地呈现。"})
    with Image.open(path) as image:
        width, height = image.size
    if abs(width / height - .75) > .06 or width < 720 or height < 960:
        problems.append({"where":"poster", "index":-1, "type":"readability", "quote":"海报尺寸",
                         "detail":"成图比例或清晰度未达到竖版预览要求。", "direction":"生成至少 720×960、接近 3:4 的竖版海报，不裁切文字。"})
    review["overall"] = ("needs_fix" if problems else "pass" if review.get("overall") == "pass" else "incomplete")
    review["model"] = settings.POSTER_REVIEW_MODEL
    return review


def attach(source: dict, jid: str, on_update=None, *, review_only=False, decision=None) -> dict:
    result = copy.deepcopy(source)
    previous_ms = source.get("total_ms", 0)
    started = time.monotonic()
    tr = Trace(on_update, budget_seconds=settings.POSTER_IMAGE_TIMEOUT)
    tr.started -= previous_ms / 1000
    tr.started_at -= previous_ms / 1000
    tr.steps = copy.deepcopy(source.get("trace", []))
    tr.events = copy.deepcopy(source.get("events", []))
    tr.artifacts = copy.deepcopy(source.get("artifacts", {}))
    folder = settings.POSTER_DIR / jid
    candidate = {"status":"preparing", "provider":settings.POSTER_IMAGE_PROVIDER,
                 "model":settings.POSTER_IMAGE_MODEL, "source_type":"ai_generated", "job_id":jid}
    prepared = None
    if not text_approved(source):
        candidate.update(status="blocked", error="文案仍有待核对项，请先在问题详情中修订或作出人工裁定，再继续生图。")
    else:
        if result.get("human_review"):
            result["text_human_review"] = result.pop("human_review")
        try:
            prepared = tr.run("poster_prepare", "准备已审核参考与产品图", lambda: prepare(source, folder),
                              view=lambda p: {"reference":p["reference"]["name"], "product_image":p["product_image"]})
            candidate.update(reference={k:prepared["reference"][k] for k in ("id", "name", "source_url", "sha256")},
                             style_input_sha256=prepared["style_input_sha256"], style_processing="blurred_palette_layout",
                             product_image=prepared["product_image"], copy=prepared["copy"], prompt_sha256=prepared["prompt_sha256"], status="generating")
            tr.publish("poster", candidate, "poster_image", "正在生成整张海报")
            def activity(data):
                candidate.update({k:v for k,v in data.items() if k != "label"})
                tr.publish("poster", candidate, "poster_image", data["label"])
            if review_only:
                previous = source.get("poster") or {}
                candidate.update(provider=previous.get("provider", "modelscope"), model=previous.get("model", ""))
                previous_id = previous.get("job_id", "")
                if not re.fullmatch(r"[a-f0-9]{32}", previous_id):
                    raise ValueError("原海报尚未生成，无法只复审图片，请选择重新生图。")
                previous_path = settings.POSTER_DIR / previous_id / "poster.png"
                if not previous_path.exists() or hashlib.sha256(previous_path.read_bytes()).hexdigest() != previous.get("sha256"):
                    raise ValueError("原海报文件无法核对，请重新生图。")
                shutil.copyfile(previous_path, folder / "poster.png")
                generated = {k:previous[k] for k in ("sha256", "width", "height", "task_id", "provider_applied", "reference_upload_warning") if k in previous}
                tr.skip("poster_image", "重新生图", "用户要求复审同一张成图，本次没有提交生图任务")
            else:
                old = source.get("poster") or {}
                same_provider = (settings.POSTER_IMAGE_PROVIDER in ("modelscope", "private_worker") and
                                 old.get("provider", "modelscope") == settings.POSTER_IMAGE_PROVIDER and
                                 old.get("model") == settings.POSTER_IMAGE_MODEL)
                resume_id = old.get("task_id") if same_provider and (old.get("resume_available") or
                             (old.get("status") == "error" and "超时" in old.get("error", ""))) else None
                generated = tr.run("poster_image", "继续等待本次海报" if resume_id else "模型生成整张海报",
                                   lambda: generate(prepared, folder, activity, tr.deadline, existing_task_id=resume_id))
            candidate.update(**generated, image_url=f"/api/job/{jid}/poster/image", status="reviewing")
            tr.publish("poster", candidate, "poster_image", "海报已返回，正在审核实际成图")
            tr.deadline = time.monotonic() + settings.POSTER_REVIEW_TIMEOUT
            from .review import instructions
            checked = tr.run("poster_review", "核对成图文字、外观与场景", lambda: inspect_image(source, prepared, folder / "poster.png",
                             feedback=instructions(decision) if decision else None))
            if candidate.get("reference_upload_warning"):
                checked["problems"].append({"where":"poster", "index":-1, "type":"reference", "detail":candidate["reference_upload_warning"],
                                            "direction":"确认产品图和风格图上传成功后，再由用户决定是否重新生图。"})
                checked["overall"] = "needs_fix"
            candidate.update(review=checked, status="passed" if checked["overall"] == "pass" else "needs_review")
        except Exception as exc:
            has_image = (folder / "poster.png").exists()
            candidate.update(status="needs_review" if has_image else "error",
                             error=str(exc) if isinstance(exc, (ValueError, llm.LLMError)) else "海报生成或成图审核连接未完成，请稍后手动重试。")
            if settings.POSTER_IMAGE_PROVIDER in ("modelscope", "private_worker") and isinstance(exc, llm.BudgetExceeded) and candidate.get("task_id") and not has_image:
                candidate["resume_available"] = True
            if has_image:
                candidate.setdefault("review", {"overall":"incomplete", "problems":[{"where":"poster", "index":-1,
                    "type":"uncertain", "detail":candidate["error"], "direction":"重新核对实际成图后再采用。"}]})
    result["poster"] = candidate
    if decision and any(a["choice"] == "defer" for a in decision["answers"]):
        candidate["status"] = "needs_review"
        candidate["error"] = "用户仍有未确认的问题，请查看终审反馈后继续处理。"
    if candidate["status"] != "passed":
        result["status"] = "ok_with_flags"
    else:
        result["status"] = "ok" if (source.get("verification") or {}).get("state") == "passed" else "ok_with_flags"
    tr.publish("poster", candidate, "poster_review", "海报流程已结束")
    tr.publish("final", {"article":result["article"], "state":"passed" if result["status"] == "ok" else "needs_review",
                         "remaining":result["verification"].get("remaining", []),
                         "version":result["verification"].get("article_version", 1)}, "controller", "本次作品已就绪")
    tr.emit("workflow_finished", "controller", label="海报流程已结束", status=result["status"])
    snapshot = tr.snapshot()
    result.update(trace=snapshot["steps"], events=snapshot["events"], artifacts=snapshot["artifacts"],
                  total_ms=previous_ms + int((time.monotonic() - started) * 1000))
    result["llm_calls"] = result.get("llm_calls", []) + tr.calls
    tr.closed = True
    return result
