"""知识库访问层（本地后端）。

接口按 docs/contracts/ima-access.md 的 LocalKB / ImaKB 同构设计：
    models() / resolve(query) / load(model_id) / prices(model_id) / matrix_card(model_id) / image_file(...)
ImaKB 在 MVP 阶段仅保留占位（评测与最终演示前需实现，见 README）。

事实只来自 P1 型号目录下的 `产品事实.md`、`卖点与限制.md`、`图片索引.csv`，价格只来自
`P1/08-官方公开价格快照/官方价格快照.csv`。每条资料切成带编号的“片段”（Snippet），
下游所有事实都必须引用片段编号，核验才能逐条回查。
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import settings

P1 = "P1-产品参数库"
GROUPS = [("01-鸿蒙电脑", "鸿蒙电脑"), ("02-MateBook-Windows", "Windows 笔记本")]
PRICE_CSV = "08-官方公开价格快照/官方价格快照.csv"
MATRIX_CSV = "00-全库横向索引/全型号参数联合矩阵.csv"

NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"huawei|华为", "", s)
    return re.sub(r"[\s　\-_()（）\[\]【】·,，:：/]+", "", s)


def nums(text: str) -> set[str]:
    return set(NUM_RE.findall((text or "").replace(",", "")))


@dataclass
class Snippet:
    id: str
    kind: str          # spec | position | conclusion | support | limit | fit | unfit | ask | price
    label: str         # 展示用来源标签
    text: str
    path: str          # 相对 KB 根目录的来源路径
    title: str = ""    # 资料标题

    @property
    def nums(self) -> set[str]:
        return nums(self.text)


@dataclass
class Image:
    id: str            # 文件名（图片索引.csv 登记）
    model: str         # 图片索引.csv「产品型号」列
    path: Path
    caption: str       # 官网图片说明
    page: str          # 来源页面
    url: str           # 原始图片URL
    width: str = ""
    height: str = ""
    use: str = ""
    vision: str = ""   # 视觉模型离线描述（可为空）
    vision_consistent: bool | None = None
    kind: str = ""     # device|device_scene|detail|screen_ui|diagram|logo|people|other（tag_images 生成，可为空）
    shows_device: bool | None = None
    angle: str = ""
    color: str = ""
    source_type: str = "knowledge_base"
    source_title: str = ""
    checked_at: str = ""

    @property
    def is_hero(self) -> bool:
        """能当主视觉的图：画面里能看到整机。未打标签时不下结论（按 True 放行，由上游提示）。"""
        return True if self.shows_device is None else bool(self.shows_device)


@dataclass
class ModelDoc:
    id: str
    name: str
    group: str
    dir: Path
    snippets: list[Snippet] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    position: str = ""

    @property
    def image_models(self) -> set[str]:
        return {i.model for i in self.images}

    def snippet(self, sid: str) -> Snippet | None:
        return next((s for s in self.snippets if s.id == sid), None)


@dataclass
class ModelInfo:
    id: str
    name: str
    group: str
    keys: set[str]
    dir: Path
    name_key: str = ""  # 官方全名归一化后的键


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


def _csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class LocalKB:
    backend = "local"

    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.KB_DIR)
        self.p1 = self.root / P1
        if not self.p1.exists():
            raise FileNotFoundError(f"找不到知识库目录：{self.p1}（设置 KB_DIR 或把副本放到 data/kb）")
        self._infos: list[ModelInfo] = []
        self._docs: dict[str, ModelDoc] = {}
        self._doc_versions: dict[str, tuple] = {}
        self._vision = self._load_vision()
        self._scan()

    # ---------- 目录扫描与型号解析 ----------
    def _scan(self) -> None:
        for gdir, gname in GROUPS:
            base = self.p1 / gdir
            if not base.exists():
                continue
            for d in sorted(base.iterdir()):
                f = d / "产品事实.md"
                if not d.is_dir() or not f.exists():
                    continue
                first = _read(f).splitlines()[0] if f.stat().st_size else ""
                name = re.sub(r"^#\s*", "", first).replace("- 产品事实", "").strip() or d.name
                keys = {norm(d.name), norm(name), norm(d.name.replace("系列", ""))}
                self._infos.append(ModelInfo(d.name, name, gname, {k for k in keys if k}, d, norm(name)))

    def models(self) -> list[ModelInfo]:
        return list(self._infos)

    def info(self, model_id: str) -> ModelInfo | None:
        return next((m for m in self._infos if m.id == model_id), None)

    def resolve(self, query: str) -> tuple[str, list[str]]:
        """返回 ("ok"|"ambiguous"|"none", [model_id...])。

        规则：官方全名完全匹配 → 确定；仅匹配目录简称（如 “MateBook 14”“MateBook D 16”）且有更具体的
        同系型号 → 歧义；查询是某些型号键的子串 → 唯一则确定、多个则歧义；最后才用“型号键出现在查询里”做最长匹配。
        """
        nq = norm(query)
        if not nq:
            return "none", []
        ms = self._infos
        full = [m.id for m in ms if nq == m.name_key]
        if full:
            return "ok", full[:1]
        exact = [m.id for m in ms if nq in m.keys]
        if exact:
            more = [m.id for m in ms if m.id not in exact and any(nq in k for k in m.keys)]
            ids = exact + more
            return ("ok", ids) if len(ids) == 1 else ("ambiguous", ids)
        sub = [m.id for m in ms if any(nq in k for k in m.keys)]
        if sub:
            return ("ok", sub) if len(sub) == 1 else ("ambiguous", sub)
        best, hit = 0, []
        for m in ms:
            for k in m.keys:
                if k in nq:
                    if len(k) > best:
                        best, hit = len(k), [m.id]
                    elif len(k) == best and m.id not in hit:
                        hit.append(m.id)
        return ("ok", hit) if len(hit) == 1 else (("ambiguous", hit) if hit else ("none", []))

    # ---------- 型号资料 ----------
    def load(self, model_id: str) -> ModelDoc:
        info = self.info(model_id)
        if not info:
            raise KeyError(model_id)
        d = info.dir
        paths = [d / name for name in ("产品事实.md", "卖点与限制.md", "来源清单.csv", "图片索引.csv")]
        version = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in paths)
        if model_id in self._docs and self._doc_versions.get(model_id) == version:
            return self._docs[model_id]
        rel = lambda p: str(p.relative_to(self.root)).replace("\\", "/")  # noqa: E731
        doc = ModelDoc(model_id, info.name, info.group, d)
        n = 0

        def add(kind, label, text, path, title):
            nonlocal n
            n += 1
            doc.snippets.append(Snippet(f"S{n}", kind, label, text.strip(), path, title))

        facts_md = _read(d / "产品事实.md")
        for kind, label, text in _parse_facts(facts_md):
            add(kind, label, text, rel(d / "产品事实.md"), f"{info.name} - 产品事实")
        sell = d / "卖点与限制.md"
        if sell.exists():
            for kind, label, text in _parse_selling(_read(sell)):
                add(kind, label, text, rel(sell), f"{info.name}｜卖点与限制")
                if kind == "position" and not doc.position:
                    doc.position = text.strip()
        doc.sources = [
            {"type": r.get("资料类型", ""), "title": r.get("标题", ""), "url": r.get("URL", ""),
             "fetched": r.get("抓取日期", "")}
            for r in _csv(d / "来源清单.csv")]
        for r in _csv(d / "图片索引.csv"):
            fn = (r.get("文件名") or "").strip()
            p = d / "images" / fn
            if not fn or not p.exists():
                continue
            v = self._vision.get(fn, {})
            doc.images.append(Image(
                id=fn, model=(r.get("产品型号") or "").strip(), path=p,
                caption=(r.get("官网图片说明") or "").strip(), page=(r.get("来源页面") or "").strip(),
                url=(r.get("原始图片URL") or "").strip(), width=r.get("宽度", ""), height=r.get("高度", ""),
                use=(r.get("建议用途") or "").strip(), vision=v.get("desc", ""),
                vision_consistent=v.get("consistent"), kind=v.get("kind", ""),
                shows_device=v.get("shows_device"), angle=v.get("angle", ""), color=v.get("color", "")))
        self._docs[model_id] = doc
        self._doc_versions[model_id] = version
        return doc

    def image_file(self, model_id: str, filename: str) -> Path | None:
        """只放行知识库登记图片，或联网补图清单中已核验的本型号图片。"""
        doc = self.load(model_id)
        img = next((i for i in doc.images if i.id == filename), None)
        if not img and filename.startswith("web-"):
            from .web_images import cached_images
            img = next((i for i in cached_images(doc, require_fresh=False) if i.id == filename), None)
        return img.path if img else None

    # ---------- 价格（仅官方公开价格快照）----------
    def _price_rows(self) -> list[dict]:
        return _csv(self.p1 / PRICE_CSV)

    def prices(self, model_id: str, limit: int = 6) -> list[Snippet]:
        info = self.info(model_id)
        if not info:
            return []
        name_n = norm(info.name)
        series = info.id.endswith("系列")
        okay_types = ("官方商城页面价", "官网参考起价", "当前商城页面价", "当前商城活动页价")
        out, seen = [], set()
        for r in self._price_rows():
            pn = norm(r.get("规范产品名称", ""))
            hit = pn == name_n or (series and pn.startswith(norm(info.id.replace("系列", ""))))
            amt = (r.get("页面金额（元）") or "").strip()
            ptype = (r.get("价格类型") or "").strip()
            if not hit or not amt or ptype not in okay_types or "缺货" in ptype:
                continue
            style = (r.get("精确款式") or "").strip()
            key = (style, amt)
            if key in seen:
                continue
            seen.add(key)
            when = (r.get("核验时间") or "")[:10]
            cond = (r.get("条件摘要") or "").strip()[:60]
            text = f"{style}：{ptype} {amt} 元（核验时间 {when}；条件：{cond or '见官方页面'}）"
            out.append(Snippet(f"P{len(out) + 1}", "price", f"价格快照·{ptype}", text,
                               f"{P1}/{PRICE_CSV}", "官方公开价格快照"))
            if len(out) >= limit:
                break
        return out

    # ---------- 型号精简卡（供“未指定型号”时推荐）----------
    @lru_cache(maxsize=1)
    def _matrix(self) -> dict[str, dict]:
        out = {}
        for r in _csv(self.p1 / MATRIX_CSV):
            src = r.get("本地事实源", "")
            out[Path(src).parent.name] = r
        return out

    def matrix_card(self, model_id: str) -> dict:
        r = self._matrix().get(model_id, {})
        cut = lambda k, n=140: (r.get(k, "") or "")[:n]  # noqa: E731
        doc = self.load(model_id)
        return {
            "model_id": model_id, "name": doc.name, "group": doc.group,
            "定位": doc.position[:200],
            "操作系统": cut("操作系统", 60), "处理器": cut("处理器", 80), "内存": cut("内存", 50),
            "存储": cut("存储", 60), "屏幕": cut("屏幕规格", 160), "尺寸重量": cut("尺寸重量", 120),
            "电池": cut("电池", 80), "接口": cut("接口", 140),
            "官方价格快照": [{"text": s.text, "source": s.path} for s in self.prices(model_id)],
        }

    # ---------- 视觉描述缓存 ----------
    def _load_vision(self) -> dict:
        f = settings.CACHE_DIR / "vision.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def whoami(self) -> dict:
        return {"backend": "local", "kb_name": "本地副本 data/kb", "connected": True,
                "models": len(self._infos)}


class ImaKB:  # pragma: no cover - 占位
    backend = "ima"

    def __init__(self, *a, **k):
        raise NotImplementedError(
            "ImaKB 尚未实现：MVP 开发期使用 KB_BACKEND=local。评测/演示前按 docs/contracts/ima-access.md 实现。")


@lru_cache(maxsize=1)
def get_kb():
    return ImaKB() if settings.KB_BACKEND == "ima" else LocalKB()


# ---------- 解析 ----------
def _chunk(lines: list[str], size: int = 450) -> list[str]:
    out, cur = [], ""
    for ln in lines:
        cur = f"{cur} {ln}".strip()
        if len(cur) >= size:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def _parse_facts(md: str):
    """产品事实.md → [(kind, label, text)]；按“## 小节”切块，长小节再按长度切。"""
    lines = md.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("## 官方规格摘录")), None)
    if start is None:
        return []
    sec, buf, order = None, {}, []
    for raw in lines[start + 1:]:
        ln = raw.strip()
        if ln.startswith("## "):
            sec = ln[3:].strip()
            buf[sec] = []
            order.append(sec)
        elif ln and sec and not ln.startswith(">"):
            buf[sec].append(ln)
    out = []
    for s in order:
        for c in _chunk(buf[s]):
            out.append(("spec", f"产品事实·{s}", c))
    return out


KEEP_H2 = {"一句话定位", "六个沟通角度", "适合进入候选清单的任务", "不适合直接下结论的任务", "发布或销售前必须追问"}


def _parse_selling(md: str):
    out = []
    h2 = h3 = sub = None
    got_position = False
    for raw in md.splitlines():
        ln = raw.strip()
        if ln.startswith("## "):
            h2, h3, sub = ln[3:].strip(), None, None
            continue
        if ln.startswith("### "):
            h3, sub = re.sub(r"^\d+\.\s*", "", ln[4:].strip()), None
            continue
        m = re.match(r"^\*\*(.+?)\*\*$", ln)
        if m:
            sub = m.group(1)
            continue
        if not ln or ln.startswith(">") or h2 not in KEEP_H2:
            continue
        bullet = ln.startswith("- ")
        text = ln[2:].strip() if bullet else ln
        if h2 == "一句话定位":
            if not got_position and not bullet:
                out.append(("position", "卖点与限制·一句话定位", text))
                got_position = True
        elif h2 == "六个沟通角度":
            if sub == "可用结论" and not bullet:
                out.append(("conclusion", f"卖点与限制·{h3}·可用结论", text))
            elif sub == "支撑事实" and bullet:
                out.append(("support", f"卖点与限制·{h3}·支撑事实", text))
            elif sub == "表达边界" and bullet:
                out.append(("limit", f"卖点与限制·{h3}·表达边界", text))
        elif bullet:
            kind = {"适合进入候选清单的任务": "fit", "不适合直接下结论的任务": "unfit",
                    "发布或销售前必须追问": "ask"}[h2]
            out.append((kind, f"卖点与限制·{h2}", text))
    return out
