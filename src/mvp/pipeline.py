"""证据约束的策划、写作与独立评审，由 Python 控制依赖和一次定向修订。

有序事件与完整产物随任务快照持久化，界面只消费真实结果；终稿复核失败不标通过。
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable

import yaml

from . import llm, settings, verify, web_images
from .kb import Image, ModelDoc, Snippet, get_kb
from .progress import Trace

PLATFORMS = ["wechat_article", "xiaohongshu", "moments", "poster"]
TODAY_NOTE = f"事实基准日 {settings.KB_BASE_DATE}；发布前须以华为官方页面和实际销售 SKU 复核。"
WORKFLOW_VERSION = "evidence-editorial-v2"


def context_version(doc=None) -> str:
    digest = hashlib.sha256(WORKFLOW_VERSION.encode())
    for path in sorted((settings.PKG / "prompts").glob("*.md")) + sorted((settings.PKG / "config").glob("*.yaml")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    if doc:
        digest.update(jdump([[s.id, s.kind, s.text, s.path, s.label, s.title] for s in doc.snippets]).encode())
    return digest.hexdigest()[:20]


# ---------- 配置与提示词 ----------
def scenes_cfg() -> dict:
    return _config("scenes")


def platforms_cfg() -> dict:
    return _config("platforms")


def _config(name):
    path = settings.PKG / "config" / f"{name}.yaml"
    return _config_version(path, path.stat().st_mtime_ns)


@lru_cache(maxsize=8)
def _config_version(path, version):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def prompt(name: str) -> str:
    base = (settings.PKG / "prompts" / "base.md").read_text(encoding="utf-8")
    step = (settings.PKG / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    return f"{base}\n\n---\n\n{step}"


def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1)


# ---------- 同一组输入的重复运行缓存 ----------
# 重复输入可复用需求理解与内容策划，缓存键同时约束需求、资料与提示词版本。
# 缓存后这两步可从几十秒降到毫秒；写作与独立审核不缓存，保证每次出稿都是真实调用。
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 24


def _cache_get(key: str):
    with _CACHE_LOCK:
        return copy.deepcopy(_CACHE[key]) if key in _CACHE else None


def _cache_put(key: str, value) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = copy.deepcopy(value)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))


def parse_scene_cached(task: dict, instruction: str | None) -> dict:
    key = "scene|" + json.dumps([context_version(), settings.FAST_MODEL, settings.KB_BASE_DATE, task.get("product"), task.get("audience"),
                                 task.get("scenario"), task.get("platform"), task.get("goal"),
                                 task.get("constraints") or [], task.get("extra"), instruction or ""],
                                ensure_ascii=False, sort_keys=True)
    hit = _cache_get(key)
    if hit is not None:
        hit["cache_hit"] = True
        return hit
    out = parse_scene(task, instruction)
    if not out.get("need_info", {}).get("blocking"):
        _cache_put(key, out)
    out["cache_hit"] = False
    return out


def plan_content_cached(doc, scene, strat, task, instruction=None):
    stable_scene = {k: v for k, v in scene.items() if k != "cache_hit"}
    key = "plan|" + json.dumps([context_version(doc), doc.id, stable_scene, _strategy_view(strat), task, instruction,
                                settings.FAST_MODEL], ensure_ascii=False, sort_keys=True)
    hit = _cache_get(key)
    if hit is not None:
        return hit, True
    plan = plan_content(doc, scene, strat, task, instruction)
    _cache_put(key, plan)
    return plan, False


# ---------- 输入检查 ----------
def check_task(task: dict) -> dict | None:
    """缺关键信息 → 返回 need_info 结果；否则 None。"""
    qs = []
    if task.get("platform") not in PLATFORMS:
        qs.append("请选择发布平台：公众号 / 小红书 / 门店朋友圈 / 门店海报")
    if not (task.get("audience") or "").strip() and not (task.get("extra") or "").strip():
        qs.append("目标人群是谁？（例如：大学新生、需要出差的职场人、内容创作者、家里换电脑的家长）")
    if not (task.get("scenario") or "").strip() and not (task.get("extra") or "").strip():
        qs.append("使用场景是什么？（例如：开学季、职场办公、内容创作、家庭换新、企业采购、门店到访）")
    if qs:
        return {"status": "need_info", "questions": qs}
    return None


# ---------- 场景解析 ----------
def prior_weights(task: dict) -> dict:
    cfg = scenes_cfg()
    dims = list(cfg["dimensions"])
    w = {d: 0.0 for d in dims}
    scen = task.get("scenario") or ""
    hit = next((k for k in cfg["scenarios"] if k in scen or scen in k and scen), None)
    if hit:
        for d, v in cfg["scenarios"][hit]["weights"].items():
            w[d] += v
    else:
        for d in dims:
            w[d] = 1 / len(dims)
    aud = task.get("audience") or ""
    for k, inc in cfg["audiences"].items():
        if k in aud:
            for d, v in inc.items():
                w[d] += v
    return _norm_w(w)


def _norm_w(w: dict) -> dict:
    t = sum(max(v, 0) for v in w.values()) or 1
    return {k: round(max(v, 0) / t, 3) for k, v in w.items()}


def parse_scene(task: dict, instruction: str | None) -> dict:
    cfg = scenes_cfg()
    prior = prior_weights(task)
    hit = next((k for k in cfg["scenarios"] if k in (task.get("scenario") or "")), None)
    payload = {
        "任务": {k: task.get(k) for k in ("product", "audience", "scenario", "platform", "goal", "constraints", "extra")},
        "修改指令": instruction or "",
        "可用维度": cfg["dimensions"],
        "先验权重": prior,
        "场景库命中": hit,
        "场景常见痛点": cfg["scenarios"][hit]["pain_points"] if hit else [],
        "购买阶段先验": cfg["scenarios"][hit]["stage"] if hit else "",
        "配置价值定义": cfg["value_definition"],
    }
    out = llm.ask_json(prompt("scene"), jdump(payload), model=settings.FAST_MODEL, role="fast")
    dims = set(cfg["dimensions"])
    lw = {d: float(out.get("weights", {}).get(d, 0) or 0) for d in dims}
    lw = _norm_w(lw) if sum(lw.values()) > 0 else prior
    mix = cfg.get("prior_mix", 0.4)
    final = _norm_w({d: mix * prior[d] + (1 - mix) * lw[d] for d in dims})
    out["prior_weights"] = prior
    out["llm_weights"] = lw
    out["weights"] = final
    out["top_dims"] = [d for d, _ in sorted(final.items(), key=lambda x: -x[1])[:4]]
    out["audience"] = out.get("audience") or task.get("audience") or ""
    out["scenario"] = out.get("scenario") or task.get("scenario") or ""
    out["matched_scenario_rule"] = hit
    out.setdefault("need_info", {"blocking": False, "questions": []})
    return out


# ---------- 平台策略 ----------
def price_policy(task: dict, spec: dict, kb, model_id: str) -> tuple[str, list[Snippet]]:
    cons = " ".join(task.get("constraints") or []) + " " + (task.get("extra") or "")
    if re.search(r"不要?提?价|不写价|不报价|别提价|不提价格|不要价格", cons):
        return "forbid", []
    policy = spec.get("price_default", "forbid")
    if policy == "conditional":
        ps = kb.prices(model_id)
        return ("conditional", ps) if ps else ("none_in_kb", [])
    return policy, []


def plan_strategy(task: dict, scene: dict, kb, model_id: str) -> dict:
    spec = platforms_cfg()[task["platform"]]
    policy, prices = price_policy(task, spec, kb, model_id)
    return {
        "platform": task["platform"], "platform_name": spec["name"],
        "reader": spec["reader"], "structure": spec["structure"], "tone": spec["tone"],
        "cta_style": spec["cta_style"], "images": spec["images"], "chars": spec["chars"],
        "writing_limits": spec.get("writing_limits", {}),
        "max_facts": spec["max_facts"], "tags": spec["tags"],
        "price_policy": policy, "price_snippets": prices,
        "priority_dims": scene["top_dims"], "user_problem": scene.get("user_problem", ""),
        "stage": scene.get("stage", ""),
    }


def _strategy_view(st: dict) -> dict:
    return {k: v for k, v in st.items() if k != "price_snippets"} | {
        "price_snippets": [s.text for s in st["price_snippets"]]}


# ---------- 型号确定 / 推荐 ----------
def decide_model(task: dict, scene: dict, kb) -> dict:
    """返回 {"status":"ok","model_id",...} 或 {"status":"need_info",...}。"""
    product = (task.get("product") or "").strip()
    if product:
        st, ids = kb.resolve(product)
        if st == "ok":
            return {"status": "ok", "model_id": ids[0], "mode": "given", "matched": product}
        names = [kb.info(i).name for i in ids]
        if st == "ambiguous":
            return {"status": "need_info", "candidates": names, "candidate_ids": ids,
                    "questions": [f"“{product}” 对应知识库里的多个型号，请确认具体型号：" + "；".join(names)]}
        return {"status": "need_info", "candidates": [m.name for m in kb.models()],
                "candidate_ids": [m.id for m in kb.models()],
                "questions": [f"知识库里没有找到“{product}”。请从已收录型号中选择，或留空让我按需求推荐。"]}
    cards = [kb.matrix_card(m.id) for m in kb.models()]
    payload = {"需求画像": {k: scene.get(k) for k in (
        "audience", "scenario", "user_problem", "stage", "hard_constraints", "soft_preferences",
        "tradeoffs", "weights", "unmappable")}, "候选型号": cards}
    rec = llm.ask_json(prompt("recommend"), jdump(payload), model=settings.FAST_MODEL, role="fast")
    valid = {m.id for m in kb.models()}
    primary = rec.get("primary")
    if primary not in valid:
        st, ids = kb.resolve(str(primary or ""))
        primary = ids[0] if st == "ok" else None
    if not primary:
        return {"status": "need_info", "questions": ["暂时无法从需求判断合适的型号，请补充使用的软件、系统习惯、预算区间或指定型号。"],
                "candidates": [m.name for m in kb.models()], "candidate_ids": [m.id for m in kb.models()]}
    alts = [a for a in rec.get("alternatives", []) if a in valid and a != primary][:2]
    rec["primary"], rec["alternatives"] = primary, alts
    return {"status": "ok", "model_id": primary, "mode": "recommended", "recommendation": rec,
            "alt_names": [kb.info(a).name for a in alts]}


# ---------- 检索与事实点提取 ----------
def retrieve(kb, model_id: str, strat: dict, on_activity=None) -> dict:
    def activity(**data):
        if on_activity:
            on_activity(data)
    activity(operation="knowledge", resource=model_id, source_kind="knowledge", status="running", label="正在读取知识库型号资料")
    doc = kb.load(model_id)
    activity(operation="knowledge", resource=model_id, source_kind="knowledge", status="done", label="知识库型号资料已读取",
             documents=list(dict.fromkeys(s.path for s in doc.snippets if s.path)), snippets=len(doc.snippets))
    imgs = [i for i in doc.images if verify.image_model_ok(i, doc)]
    dropped = [i.id for i in doc.images if i not in imgs]
    lookup = {"status": "not_needed", "reason": "知识库已有整机图", "pages": []}
    if not any(i.is_hero for i in imgs):
        lookup = web_images.find_hero(doc, on_activity=on_activity) if on_activity else web_images.find_hero(doc)
        imgs = lookup.get("images", []) + imgs
    # 整机图排前面，logo/示意图等非产品图排后面；模型只会在“可用图片”里按语义挑，不会被图注带偏
    rank = {"device": 0, "device_scene": 1, "detail": 2, "screen_ui": 3, "diagram": 4, "other": 5, "people": 5, "logo": 6, "": 3}
    imgs.sort(key=lambda i: (0 if i.is_hero else 1, rank.get(i.kind, 5)))
    heroes = [i for i in imgs if i.is_hero and i.kind in ("device", "device_scene", "")]
    return {"doc": doc, "images": imgs, "dropped_images": dropped, "hero_count": len(heroes),
            "image_search": {k: v for k, v in lookup.items() if k != "images"}}


def plan_content(doc: ModelDoc, scene: dict, strat: dict, task: dict, instruction=None) -> dict:
    snippets: list[Snippet] = list(doc.snippets) + list(strat["price_snippets"])
    payload = {
        "原始需求": task,
        "需求画像": {k: scene.get(k) for k in ("audience", "scenario", "goal", "user_problem", "top_dims",
                                                      "hard_constraints", "soft_preferences", "tradeoffs", "unmappable")},
        "平台": {"name": strat["platform_name"], "max_facts": strat["max_facts"], "price_policy": strat["price_policy"]},
        "资料片段": [{"sid": s.id, "kind": s.kind, "text": s.text, "source": s.label,
                      "evidence_type": "parameter" if s.kind in ("spec", "price") else "editorial"}
                     for s in snippets],
        "修改指令": instruction or "",
    }
    out = llm.ask_json(prompt("extract"), jdump(payload), model=settings.FAST_MODEL, role="fast")
    by_id = {s.id: s for s in snippets}
    picked, seen = [], set()
    for it in out.get("selected", []):
        sid = it.get("sid")
        if sid in by_id and sid not in seen:
            seen.add(sid)
            picked.append((by_id[sid], it))
    # 限制与待确认资料不占主张额度；它们作为条件和风险单独管理。
    boundaries = [(s, it) for s, it in picked if s.kind in ("limit", "unfit", "ask")]
    picked = [(s, it) for s, it in picked if s.kind not in ("limit", "unfit", "ask")][:strat["max_facts"]]
    facts = []
    for n, (s, it) in enumerate(picked, 1):
        facts.append({
            "id": f"F{n}", "sid": s.id, "text": s.text, "kind": s.kind,
            "role": it.get("role", "proof"), "dimension": it.get("dimension", ""), "why": it.get("why", ""),
            "claim": it.get("claim", ""),
            "evidence_type": "parameter" if s.kind in ("spec", "price") else "editorial",
            "conditions": [{"sid": sid, "text": by_id[sid].text, "source": by_id[sid].label}
                           for sid in it.get("condition_sids", []) if sid in by_id],
            "source": {"title": s.title, "label": s.label, "path": s.path, "snippet": s.id, "model": doc.name}})
    if not facts:
        raise llm.LLMError("未选出可支持内容的本型号证据，请补充资料或调整需求。")
    angles = out.get("angles") or []
    if len(angles) != 2 or len({a.get("id") for a in angles}) != 2:
        raise llm.LLMError("策划必须给出两个可比较的切入点。")
    selected = out.get("selected_angle")
    if selected not in {a.get("id") for a in angles}:
        raise llm.LLMError("策划未选定有效切入点。")
    for angle in angles:
        angle["sids"] = [sid for sid in angle.get("sids", []) if sid in by_id]
    risks = [{"sid": s.id, "text": s.text, "source": s.label} for s, _ in boundaries]
    return {"facts": facts, "angles": angles, "selected_angle": selected,
            "decision_reason": out.get("decision_reason", ""), "reader_task": out.get("reader_task", ""),
            "goal": out.get("goal") or scene.get("goal") or task.get("goal", ""),
            "unsupported_requests": out.get("unsupported_requests") or [],
            "critical_gaps": out.get("critical_gaps") or [], "risks": risks}


def style_examples(platform):
    return _config("style_examples")[platform]


# ---------- 图文编排与生成 ----------
def image_catalog(images: list[Image]) -> list[dict]:
    return [{"id": f"I{n}", "name": i.id, "model": i.model, "官网图注": i.caption,
             "尺寸": f"{i.width}x{i.height}", "视觉描述": i.vision, "画面类型": i.kind, "含整机": i.shows_device,
             "建议用途": i.use, "来源类型": i.source_type, "来源页面": i.page, "核验时间": i.checked_at}
            for n, i in enumerate(images, 1)]


def compose(task: dict, scene: dict, strat: dict, facts: list[dict], images: list[Image],
            instruction: str | None, previous: dict | None = None, issues: list[str] | None = None,
            writer_model: str | None = None, plan: dict | None = None) -> dict:
    payload = {
        "需求画像": {k: scene.get(k) for k in ("audience", "scenario", "user_problem", "goal", "stage",
                                            "hard_constraints", "soft_preferences", "tradeoffs", "unmappable",
                                            )},
        "用户限制": task.get("constraints") or [],
        "补充": task.get("extra") or "",
        "平台策略": {k: strat[k] for k in ("platform_name", "reader", "structure", "tone", "cta_style", "images",
                                          "chars", "tags", "price_policy", "writing_limits")},
        "已选事实": facts,
        "可用图片": image_catalog(images),
        "修改指令": instruction or "",
    }
    if plan:
        payload["内容主张"] = {k: plan[k] for k in ("reader_task", "goal", "unsupported_requests", "critical_gaps", "risks")}
        payload["内容主张"]["选定切入点"] = next(a for a in plan["angles"] if a["id"] == plan["selected_angle"])
    payload["风格正反例（不是产品依据）"] = style_examples(strat["platform"])
    mdl = writer_model or settings.WRITER_MODEL
    if previous is not None:
        # 修订只接收定向问题、证据和须保留的主张，不重复作者自评。
        payload.pop("需求画像", None)
        payload["上一版"] = previous
        payload["核验意见"] = issues or []
        payload["必须保留"] = "选定立意、未被指出问题的句段、单一行动目标以及已有适用条件"
        sys_p = prompt("repair")
    else:
        sys_p = prompt("compose")
    return llm.ask_json(sys_p, jdump(payload), model=mdl,
                        role="fast" if mdl == settings.FAST_MODEL else "writer")


def normalize_article(raw: dict, facts: list[dict], images: list[Image]) -> dict:
    fids = {f["id"] for f in facts}
    id2img = {f"I{n}": i for n, i in enumerate(images, 1)}
    blocks, used = [], set()
    for b in raw.get("blocks", []):
        if b.get("type") == "image":
            iid = b.get("image_id")
            if iid in id2img and iid not in used:
                used.add(iid)
                blocks.append({"type": "image", "image_id": iid, "caption": (b.get("caption") or id2img[iid].caption).strip(),
                               "fact_refs": [r for r in b.get("fact_refs", []) if r in fids]})
        elif b.get("type") == "text" and (b.get("text") or "").strip():
            blocks.append({"type": "text", "text": b["text"].strip(),
                           "fact_refs": [r for r in b.get("fact_refs", []) if r in fids]})
    tags = [t if t.startswith("#") else f"#{t}" for t in (raw.get("tags") or []) if str(t).strip()]
    return {"title": (raw.get("title") or "").strip(), "title_options": raw.get("title_options") or [],
            "lead": (raw.get("lead") or "").strip(), "blocks": blocks, "cta": (raw.get("cta") or "").strip(),
            "tags": tags, "pending_confirm": [p for p in (raw.get("pending_confirm") or []) if str(p).strip()],
            "fact_refs": {k: [r for r in (raw.get("fact_refs") or {}).get(k, []) if r in fids]
                          for k in ("title", "lead", "cta")}}


# ---------- 核验 ----------
def deterministic_check(article: dict, facts: list[dict], doc: ModelDoc, strat: dict,
                        images: list[Image]) -> dict:
    by_id = {f["id"]: f for f in facts}
    all_text = " ".join(f["text"] + " " + " ".join(c["text"] for c in f.get("conditions", [])) for f in facts)
    all_nums = set(re.findall(r"\d+(?:\.\d+)?", all_text.replace(",", "")))
    issues: list[dict] = []   # {where, index, kind, detail}

    def scan(where: str, idx: int, text: str, refs: list[str] | None):
        if not text:
            return
        sup = all_nums if refs is None else set(re.findall(
            r"\d+(?:\.\d+)?", " ".join(by_id[r]["text"] + " " + " ".join(c["text"] for c in by_id[r].get("conditions", []))
                                          for r in refs if r in by_id).replace(",", "")))
        if refs is not None and not refs:
            sup = set()
        for h in verify.scan_compliance(text, all_text):
            issues.append({"where": where, "index": idx, "kind": "compliance", "rule": h["rule"], "detail": h["hit"]})
        bad = verify.check_numbers(text, sup)
        for n in bad:
            issues.append({"where": where, "index": idx, "kind": "number", "detail": f"数字 {n} 不在所引用事实中"})
        for m in verify.check_model_mentions(text, doc):
            issues.append({"where": where, "index": idx, "kind": "model", "detail": f"出现其他型号“{m}”"})
        if strat["price_policy"] in ("forbid", "none_in_kb"):
            for p in verify.price_leak(text):
                issues.append({"where": where, "index": idx, "kind": "price", "detail": f"本平台/本次不允许价格：{p}"})

    for where in ("title", "lead", "cta"):
        scan(where, -1, article[where], article.get("fact_refs", {}).get(where))
    for i, b in enumerate(article["blocks"]):
        if b["type"] == "text":
            scan("body", i, b["text"], b.get("fact_refs", []))
            if re.search(r"\d", b["text"]) and not b.get("fact_refs") and verify.unit_numbers(b["text"]):
                issues.append({"where": "body", "index": i, "kind": "no_ref", "detail": "含参数数字但没有 fact_refs"})
        else:
            scan("caption", i, b.get("caption", ""), b.get("fact_refs"))
    id2img = {f"I{n}": im for n, im in enumerate(images, 1)}
    img_checks = []
    img_at = []
    for i, b in enumerate(article["blocks"]):
        if b["type"] == "image":
            im = id2img[b["image_id"]]
            ok = verify.image_model_ok(im, doc)
            img_checks.append({"image_id": b["image_id"], "name": im.id, "model": im.model, "model_match": ok,
                               "kind": im.kind, "shows_device": im.shows_device})
            img_at.append((i, im))
            if not ok:
                issues.append({"where": "image", "index": i, "kind": "image_model", "detail": im.id})
    # 有整机图可选时，首图不能是 logo / 示意图：首图决定读者对“产品长什么样”的第一印象
    if img_at and any(im.is_hero for im in images) and not img_at[0][1].is_hero:
        issues.append({"where": "image", "index": img_at[0][0], "kind": "image_hero",
                       "detail": "首图应换成含整机的产品图（可用图片里有整机图）"})
    plat = verify.check_platform(article, platforms_cfg()[strat["platform"]])
    # 配图数少于下限、且知识库可用图本就不够时，这是资料限制，不是模型写错：不进修订循环，改在 image_notice 提示
    if len(images) < platforms_cfg()[strat["platform"]]["images"][0]:
        plat = [p for p in plat if not p.startswith("配图") or "多于" in p]
    return {"issues": issues, "platform_issues": plat, "images": img_checks}


def judge(article: dict, facts: list[dict], strat: dict, det: dict, judge_model: str | None = None,
          images: list[Image] | None = None, task: dict | None = None, risks: list[dict] | None = None) -> dict:
    payload = {
        "平台策略": {"name": strat["platform_name"], "price_policy": strat["price_policy"], "tone": strat["tone"],
                     "structure": strat["structure"], "chars": strat["chars"], "writing_limits": strat["writing_limits"]},
        "原始需求": task or {},
        "相关风险与待确认原文": risks or [],
        "已选事实": [{k: f.get(k) for k in ("id", "text", "conditions", "source", "evidence_type")} for f in facts],
        "配图资料": image_catalog(images or []),
        "软文": {"title": article["title"], "lead": article["lead"], "cta": article["cta"], "tags": article["tags"],
                "fact_refs": article.get("fact_refs", {}),
                "blocks": [{"index": i, "where": "body" if b["type"] == "text" else "caption", **b}
                           for i, b in enumerate(article["blocks"])]},
    }
    selected = judge_model or settings.JUDGE_MODEL
    result = llm.ask_json(prompt("judge"), jdump(payload), model=selected,
                         role="fast" if selected == settings.FAST_MODEL else "judge")
    # 旧格式仍兼容；表达意见最多两项，事实/需求问题不设截断。
    must = result.get("must_fix", result.get("problems", []))
    # 语义评审不负责心算长度。对明确的计数意见用本地同一口径验证，避免无效返修。
    dismissed, confirmed = [], []
    for p in must:
        where, index = p.get("where"), p.get("index", -1)
        key = "text_block" if where == "body" else where
        text = (article.get(where, "") if index < 0 else
                article["blocks"][index].get("text", article["blocks"][index].get("caption", ""))
                if 0 <= index < len(article["blocks"]) else "")
        limit = strat["writing_limits"].get(key)
        if p.get("type") == "platform" and re.search(r"字数|字符|字.{0,8}上限|单段", p.get("detail", "")) and limit and len(re.sub(r"\s+", "", text)) <= limit:
            dismissed.append({**p, "reason": f"代码计数 {len(re.sub(r'\s+', '', text))} 字，未超过 {limit} 字"})
        else:
            confirmed.append(p)
    must = confirmed
    improvements = (result.get("improvements") or [])[:2]
    result["must_fix"], result["improvements"] = must, improvements
    result["problems"] = must + improvements
    result["dismissed_counting_notes"] = dismissed
    if dismissed and not result["problems"]:
        result["overall"] = "pass"
    expected = {(key, -1) for key in ("title", "lead", "cta") if article.get(key)}
    expected.update(("body" if b["type"] == "text" else "caption", i) for i, b in enumerate(article["blocks"])
                    if b.get("text") or b.get("caption"))
    for claim in result.get("claims", []):
        index = claim.get("index", -1)
        if 0 <= index < len(article["blocks"]) and claim.get("where") in ("body", "caption", "image"):
            claim["where"] = "body" if article["blocks"][index]["type"] == "text" else "caption"
        if claim.get("verdict") in ("unsupported", "overclaim") and not any(
                p.get("where") == claim.get("where") and p.get("index", -1) == index for p in result["problems"]):
            issue = {"where": claim.get("where"), "index": index, "type": claim["verdict"],
                     "detail": "独立评审判定该句缺乏支持或超过原文支持范围。", "direction": "依据原文补回条件，不能成立就删除承诺。"}
            result["must_fix"].append(issue)
            result["problems"].append(issue)
            result["overall"] = "needs_fix"
    actual = {(c.get("where"), c.get("index", -1)) for c in result.get("claims", [])}
    if not expected.issubset(actual):
        result["overall"] = "incomplete"
        result.setdefault("pending_confirm", []).append("独立评审未覆盖全部可见句段，需人工复核。")
    return result


def collect_issues(det: dict, jd: dict | None) -> list[str]:
    msgs = []
    for it in det["issues"]:
        msgs.append(f"[{it['where']}#{it['index']}] {it.get('rule', it['kind'])}：{it['detail']}")
    msgs += [f"[平台] {p}" for p in det["platform_issues"]]
    if jd:
        for p in jd.get("problems", []):
            msgs.append(f"[{p.get('where', 'body')}#{p.get('index', -1)}] 审核模型（{p.get('type', '')}）："
                        f"{p.get('quote', '')} {p.get('detail', '')}；修改方向：{p.get('direction', '按原始证据修正')}")
        if jd.get("overall") not in ("pass", "ok") and not jd.get("problems"):
            msgs.append("独立评审未通过或未完成，需要复核。")
    return msgs


# ---------- 主流程 ----------
def run(task: dict, instruction: str | None = None, on_update: Callable[[dict], None] | None = None,
        *, enable_revision: bool = True) -> dict:
    tr = Trace(on_update, budget_seconds=settings.GENERATION_BUDGET_SECONDS)
    kb = get_kb()
    task = {**task, "constraints": list(task.get("constraints") or [])}
    fast = (task.get("speed") or "").strip().lower() == "fast"
    writer_model = settings.FAST_MODEL if fast else settings.WRITER_MODEL
    judge_model = settings.FAST_MODEL if fast else settings.JUDGE_MODEL
    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="editorial")
    article = None
    plan = None
    attempts, revisions = [], []
    det = {"issues": [], "platform_issues": [], "images": []}
    jd = {"overall": "not_reviewed", "problems": []}
    budget_hit = False

    def await_result(future):
        try:
            return future.result(timeout=max(.001, tr.deadline - time.monotonic()))
        except FutureTimeout:
            raise llm.BudgetExceeded(
                f"已达到 {settings.GENERATION_BUDGET_SECONDS:g} 秒总预算，尚未完成的审核保留待复核状态。") from None

    def parallel(*calls):
        futures = [pool.submit(call) for call in calls]
        return [await_result(f) for f in futures]

    def perform(*args, **kwargs):
        # Even a provider that ignores its socket timeout cannot hold the task snapshot open.
        return await_result(pool.submit(lambda: tr.run(*args, **kwargs)))

    def review(version):
        suffix = "" if version == 1 else "re"

        def check_rules():
            checks = tr.run(suffix + "verify", "规则检查" if version == 1 else "终稿规则复核",
                            lambda: deterministic_check(article, facts, doc, strat, images),
                            inputs=f"稿件 v{version} · 数字、型号、图片与平台规格", depends_on=[f"draft:{version}"])
            tr.publish(f"rules:{version}", checks, "verify", "规则检查已完成", version=version)
            return checks

        def check_semantics():
            review0 = tr.run("judge" if version == 1 else "rejudge", "独立评审" if version == 1 else "独立复审实际终稿",
                             lambda: judge(article, facts, strat, {}, judge_model, images, task, plan.get("risks", [])),
                             inputs=f"原始需求 · 稿件 v{version} · 完整证据 · 平台规则", depends_on=[f"draft:{version}"])
            tr.publish(f"review:{version}", review0, "reviewer", "独立评审已完成", version=version)
            return review0

        checks, review0 = parallel(check_rules, check_semantics)
        return checks, review0

    def fin(res: dict) -> dict:
        res["task"] = task
        res["total_ms"] = int((time.monotonic() - tr.started) * 1000)
        res["kb"] = kb.whoami()
        res["budget"] = {"limit_seconds": settings.GENERATION_BUDGET_SECONDS, "exhausted": budget_hit}
        res["llm_calls"] = copy.deepcopy(tr.calls)
        with tr.lock:
            tr.emit("workflow_finished", "controller", label="作品已就绪" if res.get("article") else "流程已结束",
                    status=res["status"])
            snapshot = tr.snapshot()
            res["trace"] = snapshot["steps"]
            res.update({k: snapshot[k] for k in ("events", "artifacts")})
            tr.closed = True
        pool.shutdown(wait=False, cancel_futures=True)
        return res

    miss = check_task(task)
    tr.publish("request", {k: task.get(k) for k in ("product", "audience", "scenario", "platform", "goal", "constraints", "extra")},
               "controller", "创作简报已接收")
    if miss:
        return fin(miss)

    try:
        # 平台规范和风格示范无需等待模型理解需求。
        prep = pool.submit(lambda: tr.run("style", "准备平台规范与风格样例", lambda: {
            "spec": platforms_cfg()[task["platform"]], "examples": style_examples(task["platform"])},
            inputs=task["platform"]))
        scene = perform("scene", "理解人群与具体任务", lambda: parse_scene_cached(task, instruction),
                       inputs=" · ".join(str(task.get(k) or "") for k in ("audience", "scenario", "extra", "goal") if task.get(k)))
        tr.publish("brief", scene, "planner", "需求已整理")
        if scene["need_info"].get("blocking"):
            return fin({"status": "need_info", "questions": scene["need_info"].get("questions", []), "scene_judgement": scene})
        dm = perform("model", "匹配指定型号" if task.get("product") else "按需求推荐型号",
                    lambda: decide_model(task, scene, kb), inputs=task.get("product") or scene.get("user_problem", ""))
        if dm["status"] != "ok":
            return fin({"status": "need_info", "questions": dm["questions"], "candidates": dm.get("candidates", []),
                        "candidate_ids": dm.get("candidate_ids", []), "scene_judgement": scene})
        model_id = dm["model_id"]
        if dm["mode"] == "given":
            tr.skip("recommend", "按需求推荐", "已指定并匹配型号，无需模型推荐")
        tr.publish("model", dm, "model", "型号已确定")
        strat, retrieved = parallel(
            lambda: tr.run("strategy", "应用平台规格与价格政策", lambda: plan_strategy(task, scene, kb, model_id),
                           view=_strategy_view, inputs=f"{task['platform']} · {model_id}"),
            lambda: tr.run("retrieve", "读取本型号资料与登记图片", lambda: retrieve(kb, model_id, {},
                           on_activity=lambda data: tr.emit("tool_activity", "retrieve", step="retrieve", **data)),
                           view=lambda r: {"model": model_id, "snippets": len(r["doc"].snippets), "images": len(r["images"]),
                                           "image_search": r.get("image_search")},
                           inputs=model_id, depends_on=["model"]))
        await_result(prep)
        doc, images = retrieved["doc"], retrieved["images"]
        tr.publish("sources", {"model": doc.name, "model_id": doc.id, "snippets": [{"sid": s.id, "text": s.text, "kind": s.kind,
            "source": {"label": s.label, "title": s.title, "path": s.path, "model": doc.name}} for s in doc.snippets],
            "images": image_catalog(images), "image_search": retrieved.get("image_search")}, "retrieve", "本型号资料已读取")
        plan, hit = perform("extract", "比较两个切入点并选择证据",
                           lambda: plan_content_cached(doc, scene, strat, task, instruction),
                           view=lambda r: {"selected_angle": r[0]["selected_angle"], "facts": len(r[0]["facts"]), "cache_hit": r[1]},
                           inputs="需求画像 · 完整候选证据 · 平台目标", depends_on=["brief", "sources", "style"])
        facts = plan["facts"]
        tr.publish("evidence", {"facts": facts, "risks": plan["risks"]}, "planner", "证据已选定")
        tr.publish("plan", {**plan, "cache_hit": hit}, "planner", "立意已确定", to="editor")
        raw = perform("compose", "按选定立意创作完整稿件",
                     lambda: compose(task, scene, strat, facts, images, instruction, writer_model=writer_model, plan=plan),
                     view=lambda a: {"title": a.get("title"), "blocks": len(a.get("blocks", []))},
                     inputs="选定立意 · 证据及条件 · 图片候选 · 平台风格", depends_on=["plan", "evidence"])
        article = normalize_article(raw, facts, images)
        tr.publish("draft:1", article, "editor", "初稿已完成", version=1, to="reviewer")
        det, jd = review(1)
        msgs = collect_issues(det, jd)
        attempts.append({"round": 1, "issues": msgs, "version": 1})
        if msgs and jd.get("overall") != "incomplete" and enable_revision:
            tr.emit("route_selected", "controller", label="评审发现问题，定向修订", reason="；".join(msgs),
                    **{"from": "reviewer", "to": "editor"})
            gaps = [p for p in jd.get("problems", []) if p.get("type") in ("unsupported", "evidence_gap")]
            if gaps:
                lookup = perform("lookup", "补查本型号资料", lambda: supplement_evidence(kb, doc, facts, gaps),
                                inputs="评审指出的缺证据句段，仅查当前型号", depends_on=["review:1"])
                facts = lookup["facts"]
                tr.publish("lookup", lookup, "retrieve", "补查已完成", to="editor")
                tr.publish("evidence", {"facts": facts, "risks": plan["risks"]}, "planner", "证据包已更新")
                msgs.append("补查结论：" + lookup["reason"] + "。无法获得原文支持的承诺必须删除，不能用委婉措辞保留。")
            else:
                tr.skip("lookup", "补查本型号资料", "问题可用已有证据或表达修改解决")
            before = copy.deepcopy(article)
            raw = perform("repair", "按具体问题定向修订（最多一次）",
                         lambda: compose(task, scene, strat, facts, images, instruction, previous=before,
                                         issues=msgs, writer_model=writer_model, plan=plan),
                         view=lambda a: {"title": a.get("title"), "blocks": len(a.get("blocks", []))},
                         inputs="当前稿件 · 具体问题 · 相关证据 · 必须保留内容", depends_on=["review:1", "rules:1"])
            article = normalize_article(raw, facts, images)
            revisions = article_changes(before, article, jd, facts)
            tr.publish("revision", {"changes": revisions, "issues": msgs}, "editor", "修订已完成", version=2, to="reviewer")
            tr.publish("draft:2", article, "editor", "修订稿已完成", version=2)
            # 先撤销初稿通过状态，复审超时也不能借用初稿的评审。
            jd = {"overall": "not_reviewed", "problems": []}
            det = deterministic_check(article, facts, doc, strat, images)
            det, jd = review(2)
            attempts.append({"round": 2, "issues": collect_issues(det, jd), "version": 2})
        else:
            for step, label in (("repair", "定向修订"), ("lookup", "补查本型号资料"), ("rejudge", "修订稿复审")):
                reason = "评测仅提示词优化版，不执行修订" if not enable_revision and msgs else "评审覆盖不完整，保留待复核状态" if msgs else "初稿规则检查与独立评审通过，直接交付"
                tr.skip(step, label, reason)
    except llm.BudgetExceeded:
        budget_hit = True
        with tr.lock:
            for step in tr.steps:
                if step["status"] == "running":
                    step.update(status="error", detail={"error": "时间预算耗尽，结果未返回"},
                                ms=max(0, int((time.monotonic() - tr.started) * 1000) - step.get("started_ms", 0)))
        tr.emit("budget_exhausted", "controller", label="时间预算已用尽，未完成审核需人工复核")
        if article is None:
            return fin({"status": "budget_exceeded", "questions": ["已达到创作时间预算，尚无完整稿件。请调整需求后重试。"]})
        det = deterministic_check(article, facts, doc, strat, images)
    except Exception:
        with tr.lock:
            tr.closed = True
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    res = build_result(task, scene, dm, strat, doc, images, facts, article, det, jd, attempts, [], kb)
    res["image_search"] = retrieved.get("image_search", {})
    if budget_hit:
        res["status"] = "ok_with_flags"
        res["verification"]["remaining"].append("时间预算耗尽，必要修订或复核尚未完成。")
    res["planning"] = {k: v for k, v in plan.items() if k != "facts"}
    if plan.get("critical_gaps"):
        res["status"] = "ok_with_flags"
        res["verification"]["remaining"] += [f"关键需求无法从本型号资料确认：{gap}" for gap in plan["critical_gaps"]]
    res["evidence"]["risks"] = plan.get("risks", [])
    res["revisions"] = revisions
    res["workflow_version"] = WORKFLOW_VERSION
    res["context_version"] = context_version(doc)
    res["verification"]["article_version"] = 2 if revisions or "draft:2" in tr.artifacts else 1
    res["verification"]["state"] = "passed" if res["status"] == "ok" else "needs_review"
    res["verification"]["judge"]["model"] = judge_model
    res["models_used"] = {"writer": writer_model, "judge": judge_model, "fast": settings.FAST_MODEL,
                          "speed": "fast" if fast else "quality"}
    tr.publish("final", {"article": article, "state": res["verification"]["state"],
                         "remaining": res["verification"]["remaining"], "version": res["verification"]["article_version"]},
               "controller", "终稿已就绪" if res["status"] == "ok" else "稿件已就绪，待复核")
    return fin(res)


def supplement_evidence(kb, doc, facts, problems):
    """按问题原句检索同型号片段；找到候选不等于已证明，由复审判断支持关系。"""
    refreshed = kb.load(doc.id)
    if refreshed.id != doc.id:
        raise ValueError("补查不能跨型号")
    query = " ".join(str(p.get("quote", "")) + " " + str(p.get("detail", "")) for p in problems)
    terms = set(re.findall(r"[A-Za-z][\w.-]+|[\u4e00-\u9fff]{2,}", query))
    terms |= {word[i:i + 2] for word in list(terms) if re.search(r"[\u4e00-\u9fff]", word)
              for i in range(len(word) - 1)}
    used = {f["sid"] for f in facts}
    ranked = sorted(((sum(t.lower() in s.text.lower() for t in terms), s) for s in refreshed.snippets
                     if s.id not in used and s.kind not in ("position", "fit", "unfit", "ask")), key=lambda pair: -pair[0])
    added = []
    for score, s in ranked[:3]:
        if score < 2:
            continue
        added.append({"id": f"F{len(facts) + len(added) + 1}", "sid": s.id, "text": s.text, "kind": s.kind,
                      "role": "supplement", "why": "评审缺口的同型号候选资料，仍需复审核实", "conditions": [],
                      "source": {"title": s.title, "label": s.label, "path": s.path, "snippet": s.id, "model": doc.name}})
    return {"facts": facts + added, "added": [f["id"] for f in added], "model": doc.name,
            "reason": f"找到 {len(added)} 条同型号候选，修订与复审须判断是否真正支持" if added else "未找到新的相关依据，删除相应承诺"}


def article_changes(before, after, review, facts):
    def parts(a):
        return {(key, -1): a.get(key, "") for key in ("title", "lead", "cta")} | {
            ("body" if b["type"] == "text" else "caption", i): b.get("text", b.get("caption", ""))
            for i, b in enumerate(a["blocks"])}
    old, new = parts(before), parts(after)
    changes = []
    for where, index in sorted(old.keys() | new.keys()):
        if old.get((where, index)) == new.get((where, index)):
            continue
        problems = [p for p in review.get("problems", []) if p.get("where") == where and p.get("index", -1) == index]
        refs = (after.get("fact_refs", {}).get(where, []) if index < 0 else
                after["blocks"][index].get("fact_refs", []) if index < len(after["blocks"]) else [])
        changes.append({"where": where, "index": index, "before": old.get((where, index), ""),
                        "after": new.get((where, index), ""), "problems": problems, "fact_refs": refs,
                        "evidence": [f["id"] for f in facts if f["id"] in refs]})
    return changes


# ---------- 结果组装（对应手册统一输出四段）----------
def build_result(task, scene, dm, strat, doc, images, facts, article, det, jd, attempts, removed, kb):
    id2img = {f"I{n}": im for n, im in enumerate(images, 1)}
    used = [b["image_id"] for b in article["blocks"] if b["type"] == "image"]
    pos_of = {}
    text_idx = 0
    for b in article["blocks"]:
        if b["type"] == "text":
            text_idx += 1
        elif b["type"] == "image":
            pos_of[b["image_id"]] = f"第 {text_idx} 段后" if text_idx else "文首"
    img_out = [{"id": iid, "name": id2img[iid].id, "model": id2img[iid].model,
                "source_title": id2img[iid].source_title or f"{doc.name} 图片索引",
                "source_type": id2img[iid].source_type, "checked_at": id2img[iid].checked_at,
                "source_url": id2img[iid].page, "origin_url": id2img[iid].url,
                "caption": next((b["caption"] for b in article["blocks"] if b.get("image_id") == iid), ""),
                "position": pos_of.get(iid, ""), "local_path": str(id2img[iid].path),
                "kind": id2img[iid].kind, "shows_device": id2img[iid].shows_device, "vision": id2img[iid].vision}
               for iid in used]
    spec_imgs = strat["images"]
    heroes_used = [i for i in img_out if i["shows_device"] is not False]
    notice = []
    avail_hero = sum(1 for i in images if i.is_hero)
    if avail_hero == 0:
        notice.append(f"{doc.name} 的知识库缺少可用整机图，且暂无通过核验的官方联网补图。"
                      "请补充该型号官方整机图，或稍后重试联网检索。")
    elif img_out and not heroes_used:
        notice.append("本稿所配图片均不含整机，仅作辅助示意。")
    if len(img_out) < spec_imgs[0]:
        reason = "知识库可用图片不足" if len(images) < spec_imgs[0] else "请补充配图或重新生成"
        notice.append(f"{strat['platform_name']}建议 {spec_imgs[0]}-{spec_imgs[1]} 张图，当前仅配 {len(img_out)} 张（{reason}）。")
    used_fids = {r for b in article["blocks"] for r in b.get("fact_refs", [])}
    used_fids.update(r for refs in article.get("fact_refs", {}).values() for r in refs)
    claim_rows = []
    semantic = {(c.get("where"), c.get("index", -1)): c for c in (jd or {}).get("claims", [])}
    fields = [(where, -1, article.get(where, ""), article.get("fact_refs", {}).get(where, [])) for where in ("title", "lead", "cta")]
    fields += [("body" if b["type"] == "text" else "caption", i, b.get("text", b.get("caption", "")), b.get("fact_refs", []))
               for i, b in enumerate(article["blocks"])]
    for where, index, text, refs in fields:
        if text:
            verdict = semantic.get((where, index), {}).get("verdict", "not_reviewed")
            checked = semantic.get((where, index), {})
            mapped = [fid for fid in checked.get("fact_ids", refs) if fid in {f["id"] for f in facts}]
            used_fids.update(mapped)
            claim_rows.append({"where": where, "index": index, "claim": text, "fact_ids": mapped, "verdict": verdict})
    comp = [{"rule": h.get("rule"), "hit": h.get("hit"), "action": "rewritten"}
            for a in attempts[:-1] for h in []]
    # 记录修订过程里命中过的合规项（第 1 轮之后被改写）
    for a in attempts[:-1]:
        for m in a["issues"]:
            if "合规" in m or "绝对化" in m or "虚假" in m or "价格" in m or "虚构" in m or "竞品" in m:
                comp.append({"rule": m.split("：")[0].split("] ")[-1], "hit": m.split("：", 1)[-1][:60], "action": "rewritten"})
    for r in removed:
        comp.append({"rule": "核验未通过", "hit": r["preview"], "action": "removed"})
    pend = list(article["pending_confirm"])
    pend.append(TODAY_NOTE)
    if strat["price_policy"] in ("forbid", "none_in_kb"):
        pend.append("价格、补贴、库存与活动：本稿不含，发布前以官方渠道为准。")
    if jd:
        pend += [p for p in jd.get("pending_confirm", []) if p]
    remaining = collect_issues(det, jd)
    status = "ok" if not remaining else "ok_with_flags"
    res = {
        "status": status,
        "scene_judgement": {
            "audience": scene["audience"], "scenario": scene["scenario"], "user_problem": scene.get("user_problem", ""),
            "goal": scene.get("goal", ""), "stage": scene.get("stage", ""), "platform": strat["platform_name"],
            "strategy_notes": scene.get("strategy_notes", ""), "weights": scene["weights"],
            "prior_weights": scene["prior_weights"], "llm_weights": scene["llm_weights"],
            "hard_constraints": scene.get("hard_constraints", []), "soft_preferences": scene.get("soft_preferences", []),
            "tradeoffs": scene.get("tradeoffs", []), "unmappable": scene.get("unmappable", []),
            "matched_scenario_rule": scene.get("matched_scenario_rule")},
        "model": {"id": doc.id, "name": doc.name, "mode": dm["mode"], "recommendation": dm.get("recommendation"),
                  "alternatives": dm.get("alt_names", [])},
        "evidence": {"models": [doc.name], "backend": kb.backend,
                     "facts": [{**f, "used": f["id"] in used_fids} for f in facts],
                     "sources": doc.sources},
        "article": {**article},
        "images": img_out,
        "image_notice": notice,
        "platform_spec": {k: strat[k] for k in ("platform", "platform_name", "images", "chars", "structure", "tags")},
        "verification": {
            "facts": claim_rows,
            "images": det["images"],
            "compliance": comp,
            "platform": det["platform_issues"],
            "remaining": remaining,
            "repair_rounds": [{"round": a["round"], "issues": a["issues"]} for a in attempts],
            "judge": {"model": settings.JUDGE_MODEL, "overall": (jd or {}).get("overall"),
                      "problems": (jd or {}).get("problems", []), "must_fix": (jd or {}).get("must_fix", []),
                      "improvements": (jd or {}).get("improvements", [])},
            "pending_confirm": list(dict.fromkeys(pend))},
    }
    return res
