"""门店资料、文字素材和独立稿件历史；均保存在现有私有 SQLite 中。"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from . import settings


class ContextItem(BaseModel):
    kind: Literal["fact", "service", "stock", "activity", "customer_question", "photo_note"] = "fact"
    text: str = Field(min_length=1, max_length=800)
    source: str = Field(default="", max_length=200)
    confirmed: bool = False
    confirmed_on: date | None = None
    expires_on: date | None = None

    @model_validator(mode="after")
    def confirmation(self):
        if self.confirmed:
            if not self.text.strip() or not self.source.strip() or not self.confirmed_on:
                raise ValueError("确认资料必须填写内容、来源和确认日期")
            if self.confirmed_on > date.today():
                raise ValueError("确认日期不能在未来")
            if self.kind in ("stock", "activity") and not self.expires_on:
                raise ValueError("库存和活动必须填写有效截止日期")
            if self.expires_on and self.expires_on < self.confirmed_on:
                raise ValueError("截止日期不能早于确认日期")
        return self


class StoreProfile(BaseModel):
    name: str = Field(default="", max_length=100)
    audience: str = Field(default="", max_length=200)
    tone: str = Field(default="自然、具体，允许轻松幽默", max_length=200)
    items: list[ContextItem] = Field(default_factory=list, max_length=40)


def store_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("门店编号只可使用 1–64 位字母、数字、下划线或连字符")
    return value


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def article_parts(article):
    yield from ((key, -1, str(article.get(key) or "")) for key in ("title", "lead", "cta"))
    for i, block in enumerate(article.get("blocks") or []):
        if block.get("type") == "text":
            yield "body", i, str(block.get("text") or "")


class EditorialStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=20)
        db.execute("CREATE TABLE IF NOT EXISTS editorial_profiles (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS editorial_history (id TEXT PRIMARY KEY, store_id TEXT NOT NULL, created REAL NOT NULL, published INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS editorial_history_store ON editorial_history(store_id, created DESC)")
        db.commit()
        return db

    def profile(self, sid):
        with closing(self.connect()) as db:
            row = db.execute("SELECT payload FROM editorial_profiles WHERE id=?", (store_key(sid),)).fetchone()
        return json.loads(row[0]) if row else StoreProfile().model_dump(mode="json")

    def save_profile(self, sid, profile: StoreProfile):
        data = profile.model_dump(mode="json")
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO editorial_profiles VALUES (?,?)", (store_key(sid), _dump(data)))
        return data

    def remember(self, jid, result, created=None):
        # 概念演示的虚构资料不进入真实门店历史，也不产生可标记发布的记录。
        if (result.get("task") or {}).get("demo_mode"):
            return False
        article = result.get("article")
        if not isinstance(article, dict) or not article.get("title"):
            return False
        task = result.get("task") or {}
        lineage = result.get("review_parent") or result.get("poster_parent")
        row = {"job_id": jid, "store_id": task.get("store_id") or "default",
               "origin": "生成记录" if task.get("store_id") else "旧稿，门店未登记",
               "parent": lineage, "platform": task.get("platform", ""),
               "model": (result.get("model") or {}).get("id", task.get("product", "")),
               "title": article.get("title", ""), "article": article,
               "reader_task": (result.get("planning") or {}).get("reader_task", ""),
               "format": (result.get("planning") or {}).get("format", ""),
               "template_id": ((result.get("planning") or {}).get("template") or {}).get("id", ""),
               "angle": (result.get("planning") or {}).get("selected_angle", ""),
               "review_state": (result.get("verification") or {}).get("state", "unknown")}
        with closing(self.connect()) as db, db:
            # 幂等导入不得重置用户的发布标记或旧稿时间。
            db.execute("INSERT OR IGNORE INTO editorial_history(id,store_id,created,payload) VALUES (?,?,?,?)",
                       (jid, store_key(row["store_id"]), created if created is not None else time.time(), _dump(row)))
        return True

    def backfill(self):
        with closing(self.connect()) as db:
            exists = db.execute("SELECT name FROM sqlite_master WHERE name='jobs'").fetchone()
            rows = db.execute("SELECT id,created,payload FROM jobs WHERE id NOT IN (SELECT id FROM editorial_history)").fetchall() if exists else []
        count = 0
        for jid, created, raw in rows:
            job = json.loads(raw)
            if job.get("state") == "done":
                count += bool(self.remember(jid, job.get("result") or {}, created))
        return count

    def history(self, sid, limit=20):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT payload,published,created FROM editorial_history WHERE store_id=? ORDER BY created DESC,id DESC LIMIT ?",
                              (store_key(sid), min(limit, 100))).fetchall()
        return [{**json.loads(raw), "published": bool(pub), "created": created} for raw, pub, created in rows]

    def mark_published(self, sid, jid, published):
        with closing(self.connect()) as db, db:
            cur = db.execute("UPDATE editorial_history SET published=? WHERE id=? AND store_id=?", (int(published), jid, store_key(sid)))
            if not cur.rowcount:
                raise KeyError(jid)

    def history_item(self, sid, jid):
        with closing(self.connect()) as db:
            row = db.execute("SELECT payload,published,created FROM editorial_history WHERE store_id=? AND id=?",
                             (store_key(sid), jid)).fetchone()
        return {**json.loads(row[0]), "published": bool(row[1]), "created": row[2]} if row else None

    def snapshot(self, sid):
        profile = self.profile(sid)
        today = date.today().isoformat()
        usable, pending = [], []
        for i, item in enumerate(profile["items"], 1):
            row = {"id": f"C{i}", **item}
            if item["confirmed"] and (not item["expires_on"] or item["expires_on"] >= today):
                usable.append(row)
            else:
                pending.append({"id": row["id"], "kind": item["kind"], "reason": "已过期" if item["confirmed"] else "尚未确认"})
        methods = yaml.safe_load((settings.PKG / "config" / "creative_methods.yaml").read_text(encoding="utf-8"))
        history = self.history(sid)
        # 对照窗口固定20篇，不把全部长期历史塞进模型。
        data = {"store_id": sid, "store": {k: profile[k] for k in ("name", "audience", "tone")},
                "confirmed_items": usable, "unavailable_items": pending, "history": history,
                "methods": methods, "history_limit": 20, "as_of": today}
        data["digest"] = hashlib.sha256(_dump(data).encode()).hexdigest()[:20]
        return data


def context_facts(context, selected_ids):
    """C 引用与产品 F 引用分开；文字素材只证明记录存在，不证明产品能力。"""
    return [{"id": it["id"], "sid": it["id"], "text": it["text"], "kind": "store_context",
             "evidence_type": "user_confirmed", "conditions": [], "claim": "", "why": "门店确认资料",
             "source": {"title": "门店确认资料", "label": it["source"], "path": "", "snippet": it["id"],
                        "confirmed_on": it["confirmed_on"], "expires_on": it["expires_on"], "material_kind": it["kind"],
                        "model": "", "store_id": context.get("store_id")}}
            for it in context.get("confirmed_items", []) if it["id"] in selected_ids][:3]


def _plain(text):
    return re.sub(r"[\W_]+", "", text.lower())


def check_similarity(article, context, facts=(), exclude=()):
    """字面重合提示，不计算语义相似度或原创率，不改变事实审核状态。"""
    support = [_plain(f.get("text", "") + "".join(c.get("text", "") for c in f.get("conditions", [])))
               for f in facts if f.get("kind") != "store_context"]
    matches, fact_matches = [], []
    histories = [h for h in context.get("history", []) if h["job_id"] not in exclude]
    for where, index, text in article_parts(article):
        current = _plain(text)
        if len(current) < (8 if where == "title" else 12):
            continue
        for h in histories:
            best = None
            for old_where, old_index, old_text in article_parts(h["article"]):
                old = _plain(old_text)
                matcher = SequenceMatcher(None, current, old, autojunk=False)
                block = matcher.find_longest_match()
                ratio = matcher.ratio()
                if block.size < 8 or (ratio < .72 and block.size < 18):
                    continue
                candidate = {"where": where, "index": index, "quote": text, "job_id": h["job_id"], "title": h["title"],
                             "previous_where": old_where, "previous_index": old_index, "previous_quote": old_text,
                             "overlap": current[block.a:block.a + block.size], "ratio": round(ratio, 3),
                             "published": h["published"]}
                if best is None or candidate["ratio"] > best["ratio"]:
                    best = candidate
            if best:
                # 整句接近原始证据时单列，不能为降重改写参数或删条件。
                literal_fact = any(len(current) >= 12 and (current in s or SequenceMatcher(None, current, s).ratio() >= .9) for s in support)
                (fact_matches if literal_fact else matches).append(best)
    matches.sort(key=lambda m: (-m["ratio"], m["job_id"]))
    return {"method": "字面重合（非原创率、非语义查重）", "compared": len(histories),
            "window": context.get("history_limit", 20), "matches": matches[:8], "fact_matches": fact_matches[:8],
            "threshold": "至少8字连续重合且句段比值≥0.72，或至少18字连续重合；短句不检测",
            "suggestions": [f"{m['where']}#{m['index']} 与《{m['title']}》重合：{m['overlap']}。更换开头或叙述顺序，保持证据与条件。"
                            for m in [m for m in matches if m["where"] != "cta"][:2]]}
