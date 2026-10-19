"""营销软文智能体流水线。

场景解析(LLM) → 平台策略(规则) → 型号确定/推荐 → 资料检索(代码) → 事实点提取(LLM)
→ 图文编排与生成(LLM) → 确定性核验 + 独立审核模型 → 必要时修订 → 输出四段结果。

每一步都会记录输入摘要、输出摘要和耗时（trace），界面据此展示工作流。
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
from functools import lru_cache
from typing import Callable

import yaml

from . import llm, settings, verify, web_images
from .kb import Image, ModelDoc, Snippet, get_kb

PLATFORMS = ["wechat_article", "xiaohongshu", "moments", "poster"]
MAX_REPAIR = 1
TODAY_NOTE = f"事实基准日 {settings.KB_BASE_DATE}；发布前须以华为官方页面和实际销售 SKU 复核。"


# ---------- 配置与提示词 ----------
@lru_cache(maxsize=1)
def scenes_cfg() -> dict:
    return yaml.safe_load((settings.PKG / "config" / "scenes.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def platforms_cfg() -> dict:
    return yaml.safe_load((settings.PKG / "config" / "platforms.yaml").read_text(encoding="utf-8"))


def prompt(name: str) -> str:
    base = (settings.PKG / "prompts" / "base.md").read_text(encoding="utf-8")
    step = (settings.PKG / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    return f"{base}\n\n---\n\n{step}"


def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1)


# ---------- 同一组输入的重复运行缓存 ----------
# 一键演示常拿同一组输入连跑多次。场景解析、事实点提取是给定输入后结果不变的 LLM 调用，
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
    key = "scene|" + json.dumps([settings.KB_BASE_DATE, task.get("product"), task.get("audience"),
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


def extract_facts_cached(doc, scene: dict, strat: dict, instruction: str | None) -> tuple[list[dict], bool]:
    key = "extract|" + json.dumps([doc.id, settings.KB_BASE_DATE, scene.get("top_dims"), scene.get("weights"),
                                   scene.get("hard_constraints"), scene.get("soft_preferences"),
                                   strat.get("platform"), strat.get("max_facts"), instruction or ""],
                                  ensure_ascii=False, sort_keys=True)
    hit = _cache_get(key)
    if hit is not None:
        return hit, True
    facts = extract_facts(doc, scene, strat)
    _cache_put(key, facts)
    return facts, False


# ---------- trace ----------
class Trace:
    def __init__(self, cb: Callable[[dict], None] | None = None):
        self.steps: list[dict] = []
        self.cb = cb

    def run(self, step: str, label: str, fn):
        rec = {"step": step, "label": label, "status": "running", "ms": 0, "detail": {}}
        self.steps.append(rec)
        self._emit()
        t = time.time()
        try:
            detail = fn()
            rec["detail"] = detail if isinstance(detail, dict) else {"result": detail}
            rec["status"] = "done"
            return detail
        except Exception as e:  # noqa: BLE001
            rec["status"] = "error"
            rec["detail"] = {"error": str(e)}
            raise
        finally:
            rec["ms"] = int((time.time() - t) * 1000)
            self._emit()

    def _emit(self):
        if self.cb:
            self.cb({"steps": self.steps})


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
def retrieve(kb, model_id: str, strat: dict) -> dict:
    doc = kb.load(model_id)
    imgs = [i for i in doc.images if verify.image_model_ok(i, doc)]
    dropped = [i.id for i in doc.images if i not in imgs]
    lookup = {"status": "not_needed", "reason": "知识库已有整机图", "pages": []}
    if not any(i.is_hero for i in imgs):
        lookup = web_images.find_hero(doc)
        imgs = lookup.get("images", []) + imgs
    # 整机图排前面，logo/示意图等非产品图排后面；模型只会在“可用图片”里按语义挑，不会被图注带偏
    rank = {"device": 0, "device_scene": 1, "detail": 2, "screen_ui": 3, "diagram": 4, "other": 5, "people": 5, "logo": 6, "": 3}
    imgs.sort(key=lambda i: (0 if i.is_hero else 1, rank.get(i.kind, 5)))
    heroes = [i for i in imgs if i.is_hero and i.kind in ("device", "device_scene", "")]
    return {"doc": doc, "images": imgs, "dropped_images": dropped, "hero_count": len(heroes),
            "image_search": {k: v for k, v in lookup.items() if k != "images"}}


def _snip_line(s: Snippet) -> str:
    return f"{s.id} [{s.kind}｜{s.label}] {s.text[:260]}"


def extract_facts(doc: ModelDoc, scene: dict, strat: dict) -> list[dict]:
    snippets: list[Snippet] = list(doc.snippets) + list(strat["price_snippets"])
    payload = {
        "需求画像": {"user_problem": scene.get("user_problem"), "top_dims": scene["top_dims"],
                   "weights": scene["weights"], "hard_constraints": scene.get("hard_constraints"),
                   "soft_preferences": scene.get("soft_preferences")},
        "平台": {"name": strat["platform_name"], "max_facts": strat["max_facts"], "price_policy": strat["price_policy"]},
        "资料片段": [_snip_line(s) for s in snippets],
    }
    out = llm.ask_json(prompt("extract"), jdump(payload), model=settings.FAST_MODEL, role="fast")
    by_id = {s.id: s for s in snippets}
    picked, seen = [], set()
    for it in out.get("selected", []):
        sid = it.get("sid")
        if sid in by_id and sid not in seen:
            seen.add(sid)
            picked.append((by_id[sid], it))
    picked = picked[:strat["max_facts"]]
    facts = []
    for n, (s, it) in enumerate(picked, 1):
        facts.append({
            "id": f"F{n}", "sid": s.id, "text": s.text, "kind": s.kind,
            "role": it.get("role", "proof"), "dimension": it.get("dimension", ""), "why": it.get("why", ""),
            "source": {"title": s.title, "label": s.label, "path": s.path, "snippet": s.id, "model": doc.name}})
    if not facts:
        raise llm.LLMError("事实点提取为空")
    return facts


# ---------- 图文编排与生成 ----------
def image_catalog(images: list[Image]) -> list[dict]:
    return [{"id": f"I{n}", "name": i.id, "model": i.model, "官网图注": i.caption,
             "尺寸": f"{i.width}x{i.height}", "视觉描述": i.vision, "画面类型": i.kind, "含整机": i.shows_device,
             "建议用途": i.use, "来源类型": i.source_type, "来源页面": i.page, "核验时间": i.checked_at}
            for n, i in enumerate(images, 1)]


def compose(task: dict, scene: dict, strat: dict, facts: list[dict], images: list[Image],
            instruction: str | None, previous: dict | None = None, issues: list[str] | None = None,
            writer_model: str | None = None) -> dict:
    payload = {
        "需求画像": {k: scene.get(k) for k in ("audience", "scenario", "user_problem", "goal", "stage",
                                            "hard_constraints", "soft_preferences", "tradeoffs", "unmappable",
                                            "strategy_notes")},
        "用户限制": task.get("constraints") or [],
        "补充": task.get("extra") or "",
        "平台策略": {k: strat[k] for k in ("platform_name", "reader", "structure", "tone", "cta_style", "images",
                                          "chars", "tags", "price_policy", "writing_limits")},
        "已选事实": [{"id": f["id"], "角色": f["role"], "text": f["text"], "来源": f["source"]["label"]} for f in facts],
        "可用图片": image_catalog(images),
        "修改指令": instruction or "",
    }
    if previous is not None:
        payload["上一版"] = previous
        payload["核验意见"] = issues or []
        sys_p, mdl = prompt("repair"), settings.FAST_MODEL
    else:
        sys_p, mdl = prompt("compose"), (writer_model or settings.WRITER_MODEL)
    return llm.ask_json(sys_p, jdump(payload), model=mdl,
                        role="fast" if previous is not None or mdl == settings.FAST_MODEL else "writer")


def normalize_article(raw: dict, facts: list[dict], images: list[Image]) -> dict:
    fids = {f["id"] for f in facts}
    id2img = {f"I{n}": i for n, i in enumerate(images, 1)}
    blocks, used = [], set()
    for b in raw.get("blocks", []):
        if b.get("type") == "image":
            iid = b.get("image_id")
            if iid in id2img and iid not in used:
                used.add(iid)
                blocks.append({"type": "image", "image_id": iid, "caption": (b.get("caption") or id2img[iid].caption).strip()})
        elif b.get("type") == "text" and (b.get("text") or "").strip():
            blocks.append({"type": "text", "text": b["text"].strip(),
                           "fact_refs": [r for r in b.get("fact_refs", []) if r in fids]})
    tags = [t if t.startswith("#") else f"#{t}" for t in (raw.get("tags") or []) if str(t).strip()]
    return {"title": (raw.get("title") or "").strip(), "title_options": raw.get("title_options") or [],
            "lead": (raw.get("lead") or "").strip(), "blocks": blocks, "cta": (raw.get("cta") or "").strip(),
            "tags": tags, "pending_confirm": [p for p in (raw.get("pending_confirm") or []) if str(p).strip()]}


# ---------- 核验 ----------
def deterministic_check(article: dict, facts: list[dict], doc: ModelDoc, strat: dict,
                        images: list[Image]) -> dict:
    by_id = {f["id"]: f for f in facts}
    all_text = " ".join(f["text"] for f in facts)
    all_nums = set(re.findall(r"\d+(?:\.\d+)?", all_text.replace(",", "")))
    issues: list[dict] = []   # {where, index, kind, detail}

    def scan(where: str, idx: int, text: str, refs: list[str] | None):
        if not text:
            return
        sup = all_nums if not refs else set(re.findall(
            r"\d+(?:\.\d+)?", " ".join(by_id[r]["text"] for r in refs if r in by_id).replace(",", "")))
        if refs is not None and not refs:
            sup = set()
        for h in verify.scan_compliance(text, all_text):
            issues.append({"where": where, "index": idx, "kind": "compliance", "rule": h["rule"], "detail": h["hit"]})
        bad = verify.check_numbers(text, sup | (all_nums if where != "body" else set()))
        for n in bad:
            issues.append({"where": where, "index": idx, "kind": "number", "detail": f"数字 {n} 不在所引用事实中"})
        for m in verify.check_model_mentions(text, doc):
            issues.append({"where": where, "index": idx, "kind": "model", "detail": f"出现其他型号“{m}”"})
        if strat["price_policy"] in ("forbid", "none_in_kb"):
            for p in verify.price_leak(text):
                issues.append({"where": where, "index": idx, "kind": "price", "detail": f"本平台/本次不允许价格：{p}"})

    scan("title", -1, article["title"], None)
    scan("lead", -1, article["lead"], None)
    scan("cta", -1, article["cta"], None)
    for i, b in enumerate(article["blocks"]):
        if b["type"] == "text":
            scan("body", i, b["text"], b.get("fact_refs", []))
            if re.search(r"\d", b["text"]) and not b.get("fact_refs") and verify.unit_numbers(b["text"]):
                issues.append({"where": "body", "index": i, "kind": "no_ref", "detail": "含参数数字但没有 fact_refs"})
        else:
            scan("caption", i, b.get("caption", ""), None)
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
          images: list[Image] | None = None) -> dict:
    payload = {
        "平台策略": {"name": strat["platform_name"], "price_policy": strat["price_policy"], "tone": strat["tone"],
                     "structure": strat["structure"], "chars": strat["chars"], "writing_limits": strat["writing_limits"]},
        "已选事实": [{"id": f["id"], "text": f["text"]} for f in facts],
        "配图资料": image_catalog(images or []),
        "软文": {"title": article["title"], "lead": article["lead"], "cta": article["cta"], "tags": article["tags"],
                "blocks": [{"index": i, **{k: v for k, v in b.items()}} for i, b in enumerate(article["blocks"])]},
        "规则表命中数": len(det["issues"]),
    }
    selected = judge_model or settings.JUDGE_MODEL
    return llm.ask_json(prompt("judge"), jdump(payload), model=selected,
                        role="fast" if selected == settings.FAST_MODEL else "judge")


def collect_issues(det: dict, jd: dict | None) -> list[str]:
    msgs = []
    for it in det["issues"]:
        msgs.append(f"[{it['where']}#{it['index']}] {it.get('rule', it['kind'])}：{it['detail']}")
    msgs += [f"[平台] {p}" for p in det["platform_issues"]]
    if jd:
        for p in jd.get("problems", []):
            msgs.append(f"[{p.get('where', 'body')}#{p.get('index', -1)}] 审核模型（{p.get('type', '')}）：{p.get('detail', '')}")
    return msgs


def strip_bad_blocks(article: dict, det: dict, jd: dict | None) -> tuple[dict, list[dict]]:
    """修订仍未通过时的兜底：删除仍有问题的正文块/图片，不带伤发布。"""
    bad = {it["index"] for it in det["issues"] if it["where"] in ("body", "caption", "image") and it["index"] >= 0}
    removed = []
    keep = []
    for i, b in enumerate(article["blocks"]):
        if i in bad:
            removed.append({"index": i, "preview": (b.get("text") or b.get("image_id") or "")[:50]})
        else:
            keep.append(b)
    article = {**article, "blocks": keep}
    return article, removed


# ---------- 主流程 ----------
def run(task: dict, instruction: str | None = None, on_update: Callable[[dict], None] | None = None) -> dict:
    tr = Trace(on_update)
    kb = get_kb()
    t0 = time.time()
    task = {**task, "constraints": list(task.get("constraints") or [])}
    # 生成档位：quality 保持写作/审核 high；fast 全部降到 FAST_MODEL，用于现场演示
    fast = (task.get("speed") or "").strip().lower() == "fast"
    writer_model = settings.FAST_MODEL if fast else settings.WRITER_MODEL
    judge_model = settings.FAST_MODEL if fast else settings.JUDGE_MODEL

    def fin(res: dict) -> dict:
        res["trace"] = tr.steps
        res["task"] = task
        res["total_ms"] = int((time.time() - t0) * 1000)
        res["kb"] = kb.whoami()
        if on_update:
            on_update({"steps": tr.steps, "result": res})
        return res

    miss = check_task(task)
    if miss:
        return fin(miss)

    scene = tr.run("scene", "场景解析（规则先验 + 模型推理）", lambda: parse_scene_cached(task, instruction))
    if scene["need_info"].get("blocking") and scene["need_info"].get("questions"):
        return fin({"status": "need_info", "questions": scene["need_info"]["questions"], "scene_judgement": scene})

    dm = tr.run("model", "确定型号（指定 / 按需求推荐）", lambda: decide_model(task, scene, kb))
    if dm["status"] != "ok":
        return fin({"status": "need_info", "questions": dm["questions"], "candidates": dm.get("candidates", []),
                    "candidate_ids": dm.get("candidate_ids", []), "scene_judgement": scene})
    model_id = dm["model_id"]

    strat = tr.run("strategy", "平台策略（规则表）", lambda: plan_strategy(task, scene, kb, model_id))
    tr.steps[-1]["detail"] = _strategy_view(strat)
    tr.steps[-1]["detail"]["price_policy_note"] = {
        "forbid": "本次不出现价格", "conditional": "可引用官方价格快照，须带类型/时间/条件",
        "none_in_kb": "知识库无该型号价格快照 → 只写以官方渠道为准"}.get(strat["price_policy"], "")

    # 只检索一次：之前为了写 trace 摘要会重复调用 retrieve
    docs_holder: dict = {}

    def _retrieve_once():
        r0 = retrieve(kb, model_id, strat)
        docs_holder["r"] = r0
        return {"model": model_id, "backend": kb.backend,
                "snippets": len(r0["doc"].snippets), "images": len(r0["images"]),
                "dropped_images_model_mismatch": r0["dropped_images"], "hero_images": r0["hero_count"],
                "image_kinds": {i.id[-28:]: i.kind or "未标注" for i in r0["images"]},
                "sources": [s["url"] for s in r0["doc"].sources][:3], "image_search": r0["image_search"]}

    tr.run("retrieve", "读取本型号资料，缺图时检索官网并核验", _retrieve_once)
    r = docs_holder["r"]
    doc, images = r["doc"], r["images"]

    def _extract():
        facts0, hit = extract_facts_cached(doc, scene, strat, instruction)
        return {"facts": facts0, "cache_hit": hit}

    facts = tr.run("extract", "事实点提取（按画像权重选片段）", _extract)["facts"]

    raw = tr.run("compose", "图文编排与软文生成",
                 lambda: {"article": compose(task, scene, strat, facts, images, instruction,
                                             writer_model=writer_model)})["article"]
    article = normalize_article(raw, facts, images)

    attempts = []
    det = None
    # 1) 确定性核验是毫秒级，先循环修到通过（最多 MAX_REPAIR 次），不调用慢模型
    for rnd in range(MAX_REPAIR + 1):
        det = tr.run("verify", f"确定性核验（第{rnd + 1}轮：数字/型号/图片/价格/规则表/平台）",
                     lambda: deterministic_check(article, facts, doc, strat, images))
        msgs = collect_issues(det, None)
        attempts.append({"round": rnd + 1, "issues": msgs})
        if not msgs or rnd == MAX_REPAIR:
            break
        raw = tr.run("repair", f"按意见修订（第{rnd + 1}次）", lambda: {
            "article": compose(task, scene, strat, facts, images, instruction, previous=article,
                               issues=msgs, writer_model=writer_model)})["article"]
        article = normalize_article(raw, facts, images)

    # 2) 先删去规则仍未通过的片段，独立审核必须看到实际展示的终稿。
    removed = []
    if collect_issues(det, None):
        article, removed = strip_bad_blocks(article, det, None)
        det = tr.run("verify", "删去未通过片段后复核",
                     lambda: deterministic_check(article, facts, doc, strat, images))

    # 独立审核意见进入结果供人确认，不触发整篇重写。
    jd = tr.run("judge", f"独立审核（{judge_model}）", lambda: judge(
        article, facts, strat, det, judge_model=judge_model, images=images))
    attempts.append({"round": len(attempts) + 1, "issues": collect_issues({"issues": [], "platform_issues": []}, jd),
                     "source": "judge"})
    res = build_result(task, scene, dm, strat, doc, images, facts, article, det, jd, attempts, removed, kb)
    res["image_search"] = r["image_search"]
    res["verification"]["judge"]["model"] = judge_model
    res["models_used"] = {"writer": writer_model, "judge": judge_model, "fast": settings.FAST_MODEL,
                          "speed": "fast" if fast else "quality"}
    return fin(res)


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
    used_fids = {r for b in article["blocks"] if b["type"] == "text" for r in b.get("fact_refs", [])}
    claim_rows = []
    for b in article["blocks"]:
        if b["type"] == "text":
            claim_rows.append({"claim": b["text"][:60], "fact_ids": b.get("fact_refs", []),
                               "verdict": "supported" if b.get("fact_refs") else "no_fact_claim"})
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
    if jd and jd.get("overall") not in ("pass", "ok") and not jd.get("problems"):
        remaining.append("独立审核未通过，请人工复核后发布。")
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
                     "facts": [{"id": f["id"], "text": f["text"], "role": f["role"], "why": f["why"],
                                "used": f["id"] in used_fids, "source": f["source"]} for f in facts],
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
                      "problems": (jd or {}).get("problems", [])},
            "pending_confirm": list(dict.fromkeys(pend))},
    }
    return res
