"""固定输入生成提示词 A/B 对照；结果写入忽略提交的 data/，不修改门店历史。"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mvp import settings, prompt_variants as pv
from src.mvp.editorial_context import EditorialStore
from src.mvp.prompt_comparison import compare


def render(result):
    e = lambda value: html.escape(str(value or ""))
    columns = []
    for variant in pv.VARIANTS:
        r = result.get("variants", {}).get(variant)
        if not r:
            continue
        a = r.get("article") or {}
        paragraphs = [*a.get("disclosures", []), a.get("lead", ""), *[b.get("text", "[配图] " + b.get("caption", "")) for b in a.get("blocks", [])], a.get("cta", "")]
        issues = r.get("verification", {}).get("remaining", [])
        columns.append(f'<section><h2>{e(pv.VARIANTS[variant])}</h2><small>{e(r["prompt_version"]["digest"])} · {r["total_ms"]/1000:.1f} 秒</small><h3>{e(a.get("title"))}</h3>' +
                       ''.join(f'<p>{e(t)}</p>' for t in paragraphs if t) +
                       f'<b>{e(r.get("chars"))} 字 · {e(r.get("verification", {}).get("state", r["status"]))}</b>' +
                       ''.join(f'<p class="issue">{e(i)}</p>' for i in issues) +
                       (f'<p class="issue">{e(r["error"])}</p>' if r.get("error") else '') + '</section>')
    texts = result.get('prompt_snapshots')
    def system(variant):
        if texts:
            return texts[variant]['base'] + '\n\n---\n\n' + texts[variant]['compose']
        return pv.prompt('compose', variant)
    diff = '\n'.join(difflib.unified_diff(system('baseline').splitlines(), system('differentiated').splitlines(), fromfile='A/base+compose', tofile='B/base+compose', lineterm=''))
    preparation = result.get('variants', {}).get('preparation')
    prep_html = f'<pre>{e(json.dumps(preparation, ensure_ascii=False, indent=2))}</pre>' if preparation else ''
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>提示词 A/B 实际对照</title>'
            '<style>body{font:15px/1.8 system-ui;background:#f5f3ee;color:#292d29;max-width:1150px;margin:40px auto;padding:0 20px}h1{font-size:28px}.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px}section{background:white;border:1px solid #ddd9d0;border-radius:14px;padding:24px;overflow-wrap:anywhere}small{color:#666}p{white-space:pre-wrap}.issue{color:#884b22}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}details{margin:20px 0}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style>'
            f'<h1>提示词 A/B 实际对照</h1><p>{datetime.now(timezone(timedelta(hours=8))).date()} · 单组真实调用；不构成稳定提升或真实投放效果证明。</p>'
            f'<p>{e(result["scope"])}</p><p>共同输入摘要：{e(result.get("shared",{}).get("digest"))}</p>' + prep_html + '<div class="grid">' + ''.join(columns) + '</div>' +
            f'<details><summary>双方共同输入、事实与策划</summary><pre>{e(json.dumps(result.get("shared",{}),ensure_ascii=False,indent=2))}</pre></details>' +
            f'<details><summary>写作提示词逐行差异</summary><pre>{e(diff)}</pre></details>' +
            '<p>审核使用统一新版提示词和相同规则；没有自动修订。字面重合为零不代表语义新颖。完整结果在同目录 JSON，未自动记入门店历史。</p></html>')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--task', type=Path, help='简报 JSON；不接受其中自带的上下文，始终读取本机门店资料')
    ap.add_argument('--store', default='default')
    ap.add_argument('--reuse', type=Path, help='沿用本机已生成对照的共同策划，不重新选题；用于核对提示词小改动')
    ap.add_argument('--out', type=Path, default=settings.ROOT / 'data/prompt-comparison/latest')
    args = ap.parse_args()
    task = json.loads(args.task.read_text(encoding='utf-8-sig')) if args.task else {
        'product': 'HUAWEI MateBook 14（鸿蒙版）', 'audience': '每天去图书馆的大学生', 'scenario': '去图书馆查看课程资料',
        'platform': 'moments', 'speed': 'quality', 'goal': '带着常用软件清单到店核对', 'constraints': ['不写价格'],
        'extra': '对照用模拟需求，不代表真实客户。只写携带到图书馆这个任务；不要求承诺软件兼容性、运行能力、续航或性能，不指定任何专业软件。自然一点，不编造实测、客户经历或门店服务。'}
    frozen = None
    if args.reuse:
        previous = json.loads(args.reuse.read_text(encoding='utf-8-sig'))
        task = previous['task']
        frozen = previous['shared']
        if not frozen:
            ap.error('原结果没有可沿用的共同策划')
    else:
        task['store_id'] = args.store
        task['creative_context'] = EditorialStore(settings.JOB_DB).snapshot(args.store)
    instruction = task.pop('instruction', None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    def update(snapshot):
        for step in snapshot.get('steps', []):
            key = (step['step'], step['status'])
            if key not in seen:
                print(step['status'], step['label'], flush=True)
                seen.add(key)
    if frozen:
        instruction = frozen.get('instruction') or None
    result = compare(task, instruction, on_update=update, frozen_shared=frozen)
    args.out.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    args.out.with_suffix('.html').write_text(render(result), encoding='utf-8')
    print(json.dumps({'status':result['status'], 'path':str(args.out.with_suffix('.html')),
        'results':{k:{'status':v.get('status'),'chars':v.get('chars'),'ms':v.get('total_ms')} for k,v in result['variants'].items()}},ensure_ascii=False))


if __name__ == '__main__':
    main()
