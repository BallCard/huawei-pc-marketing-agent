"""用户审核的具体样板：代码限定候选，现有策划模型选择，素材与产品事实分开。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import yaml
from . import settings, marketing_product_pairs


def library():
    data = yaml.safe_load((settings.PKG / 'config' / 'marketing_templates.yaml').read_text(encoding='utf-8'))
    approved = set(data['review']['approved']) - set(data['review']['rejected'])
    data['templates'] = [t for t in data['templates'] if t['id'] in approved]
    store = store_library()
    if store['templates']:
        data['templates'].extend(store['templates'])
        data['store_review'] = store['review']
    return data


def store_library():
    """门店／私域营销模式候选库。默认审核列表为空，不改变现有生成行为。"""
    path = settings.PKG / 'config' / 'store_private_templates.yaml'
    if not path.exists():
        return {'version': '', 'review': {}, 'templates': []}
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    approved = set(data['review']['approved']) - set(data['review']['rejected'])
    data['templates'] = [t for t in data['templates'] if t['id'] in approved]
    return data


def topic_valid(topic, today=None):
    try:
        local_day = today or datetime.now(timezone(timedelta(hours=8))).date()
        age = (local_day - date.fromisoformat(topic.get('checked_on', ''))).days
        url = urlsplit(topic.get('source', ''))
        return bool(topic.get('title', '').strip() and url.scheme in ('https', 'http') and url.hostname and 0 <= age <= 7)
    except (ValueError, TypeError):
        return False


def candidates(task, data=None):
    data = data or library()
    context = task.get('creative_context') or {}
    eligible, unavailable = [], []
    for t in data['templates']:
        reason = ''
        if task.get('platform') not in t['platforms']:
            reason = '本轮未实现这个平台的样板形式'
        elif t.get('touchpoints') and not set(t['touchpoints']) & set(task.get('touchpoints') or []):
            reason = '本轮未选择该样板对应的私域触点'
        elif t.get('demo') and not task.get('demo_mode'):
            reason = '需要开启概念演示，并保留试验／非真实标识'
        elif t.get('subject') and not (task.get('concept_subject') or '').strip():
            reason = '需要填写拟议联动对象'
        elif t.get('topic') and not topic_valid(task.get('topic_context') or {}):
            reason = '需要提供议题、来源链接与七日内核对日期'
        elif t.get('store') and not task.get('demo_mode') and not any(
                i.get('kind') in ('activity', 'service') for i in context.get('confirmed_items', [])):
            reason = '需要有效的门店活动／服务资料，或使用明确标注的演示数据'
        if reason:
            unavailable.append({'id': t['id'], 'reason': reason})
        else:
            eligible.append(copy.deepcopy(t))
    return eligible, unavailable


def prepare_task(task):
    """只给 B 增加样板；已保存的同次创作快照不随续审改变。"""
    if task.get('prompt_variant', 'baseline') != 'differentiated':
        return task
    task = copy.deepcopy(task)
    ctx = task.setdefault('creative_context', {})
    if ctx.get('template_review'):
        return task
    data = library()
    eligible, unavailable = candidates(task, data)
    ctx['methods'] = []  # 未经本次审核的旧方法不再作为 B 的候选。
    ctx['approved_templates'] = eligible
    ctx['template_review'] = {**data['review'], 'version': data['version'], 'unavailable': unavailable}
    ctx['topic_context'] = {**task['topic_context'], 'trust': '用户提供议题，本程序未联网核实，不证明热度'} if topic_valid(task.get('topic_context') or {}) else None
    ctx['demo_items'] = ([
        {'id': 'D1', 'text': '示例体验点“春风体验点”（虚构门店）'},
        {'id': 'D2', 'text': '演示安排：周六14:00—17:00，携带一份课程资料参加文档查看体验（非真实活动）'},
    ] if task.get('demo_mode') else [])
    requested = task.get('marketing_template', 'auto')
    if requested != 'auto':
        selected_pair = marketing_product_pairs.pair(requested)
        if selected_pair:
            task['_template_product'] = selected_pair['model_name']
            ctx['template_product_pair'] = selected_pair
    ctx['digest'] = hashlib.sha256(json.dumps({k: v for k, v in ctx.items() if k != 'digest'}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
    return task


def bind_plan(out, task, facts):
    """只接受已获准且当前可用的 ID 与槽位；模板文字永不成为产品事实。"""
    task = prepare_task(task)
    ctx = task.get('creative_context') or {}
    eligible = ctx.get('approved_templates', [])
    by_id = {t['id']: t for t in eligible}
    validate_task(task)
    requested = task.get('marketing_template', 'auto')
    choice = requested if requested != 'auto' else out.get('template_id')
    origin = '用户指定' if requested != 'auto' else '策划模型选择'
    if not isinstance(choice, str) or choice not in by_id:
        choice = next((i for i in ('C13', 'C08', 'C14') if i in by_id), None)
        origin = '模型未返回有效样板，规则回退'
    if choice is None:
        raise ValueError('当前任务没有可用的已审核样板')
    t = copy.deepcopy(by_id[choice])
    valid_refs = {f['sid'] for f in facts} | {f['id'] for f in facts}
    if choice == 'C16' and task.get('demo_mode'):
        valid_refs |= {i['id'] for i in ctx.get('demo_items', [])}
    slots = []
    supplied = out.get('template_slots')
    raw_slots = {s.get('slot'): s for s in supplied if isinstance(s, dict) and isinstance(s.get('slot'), str)} if isinstance(supplied, list) else {}
    for name in t['slots']:
        slot = raw_slots.get(name, {})
        slots.append({'slot': name, 'text': str(slot.get('text') or '')[:400],
                      'refs': [r for r in slot.get('refs', []) if isinstance(r, str) and r in valid_refs]
                      if isinstance(slot.get('refs'), list) else []})
    if choice == 'C16' and task.get('demo_mode'):
        for item in ctx.get('demo_items', []):
            if any(f['id'] == item['id'] for f in facts):
                continue
            facts.append({'id': item['id'], 'sid': item['id'], 'text': item['text'], 'kind': 'demo_context',
                          'evidence_type': 'fictional_demo', 'conditions': [], 'claim': '', 'why': '仅用于标注后的概念演示',
                          'source': {'title': '虚构演示资料', 'label': '演示数据，非门店确认', 'snippet': item['id'], 'model': ''}})
    if choice == 'C16' and not task.get('demo_mode') and not any(
            f.get('kind') == 'store_context' and f.get('source', {}).get('material_kind') in ('service', 'activity') for f in facts):
        raise ValueError('C16 策划未选入门店确认的活动／服务资料，不能编成真实邀请')
    product_pair = marketing_product_pairs.pair(choice)
    resolved_name = task.get('_resolved_model_name', '')
    if requested != 'auto' and product_pair and resolved_name and resolved_name != product_pair.get('model_name'):
        raise ValueError(f'样板 {choice} 的对标型号是 {product_pair.get("model_name")}，当前选择的是 {resolved_name}；请改用对应华为型号或更换样板')
    return {**t, 'selection_source': origin, 'reason': str(out.get('template_reason') or '')[:400],
            'filled_slots': slots, 'review_sha256': ctx.get('template_review', {}).get('sha256'),
            'concept_subject': task.get('concept_subject', '') if choice == 'C10' else '',
            'demo': bool(task.get('demo_mode')), 'product_pair': product_pair,
            'fallback_asset': product_pair.get('fallback_asset') if product_pair else '',
            'fallback_note': product_pair.get('fallback_note') if product_pair else ''}


def validate_task(task):
    """生成前检查用户指定样板，避免消耗模型调用后才报缺资料。"""
    if task.get('prompt_variant', 'baseline') != 'differentiated':
        return
    ctx = prepare_task(task).get('creative_context') or {}
    requested = task.get('marketing_template', 'auto')
    available = {t['id'] for t in ctx.get('approved_templates', [])}
    if requested != 'auto' and requested not in available:
        reason = next((x['reason'] for x in ctx.get('template_review', {}).get('unavailable', []) if x['id'] == requested), '样板未经审核许可')
        raise ValueError(f'样板 {requested} 暂不能使用：{reason}')
    if not available:
        raise ValueError('当前任务没有可用的已审核样板')
    if requested != 'auto' and task.get('product'):
        selected_pair = marketing_product_pairs.pair(requested)
        if selected_pair:
            # 在启动后台任务前核对用户手填型号，避免写作完成后才发现样板与型号不一致。
            from .kb import get_kb
            status, ids = get_kb().resolve(str(task['product']).strip())
            if status == 'ambiguous':
                raise ValueError(f'样板 {requested} 需要固定到 {selected_pair["model_name"]}；当前型号有多个匹配，请填写完整型号')
            if status == 'ok' and selected_pair.get('model_id') not in ids:
                raise ValueError(f'样板 {requested} 的对标型号是 {selected_pair["model_name"]}，当前填写的是 {task["product"]}')


def disclosures(task, template=None):
    labels = []
    if task.get('demo_mode'):
        labels.append('概念演示·含虚构设定，非真实门店活动')
    key = (template or {}).get('id')
    if key == 'C04':
        labels.append('角色试验·与品牌方暂无联系')
    elif key == 'C07':
        labels.append('四格漫画·情景演绎')
    elif key == 'C09':
        labels.append('数字分身概念·非真人数字孪生')
    elif key == 'C10':
        labels.append('联动概念提案·非真实合作')
    if (template or {}).get('disclosure'):
        labels.append(str(template['disclosure']))
    return labels


def decorate(article, task, plan=None):
    article = copy.deepcopy(article)
    labels = disclosures(task, (plan or {}).get('template') or task.get('_template_plan'))
    if labels:
        article['disclosures'] = labels
    else:
        article.pop('disclosures', None)
    return article


def normalize_structure(article, task, plan, facts):
    """四格海报只保留分镜和 CTA；移除重复元信息，不截断任何事实句。"""
    template = (plan or {}).get('template') or task.get('_template_plan') or {}
    if task.get('prompt_variant') != 'differentiated' or task.get('platform') != 'poster' or template.get('id') != 'C07':
        return article
    article = copy.deepcopy(article)
    changes = []
    if article.get('lead'):
        changes.append({'field': 'lead', 'before': article['lead'], 'after': '', 'reason': '四格样板不另加导语'})
        article['lead'] = ''
    labels = set(disclosures(task, template))
    kept = []
    for i, block in enumerate(article.get('blocks', [])):
        if block.get('type') == 'text' and block.get('text', '').strip() in labels and not block.get('fact_refs'):
            changes.append({'field': f'blocks[{i}]', 'before': block['text'], 'after': '', 'reason': '标识由 disclosures 独立展示，不占一个故事格'})
        else:
            kept.append(block)
    article['blocks'] = kept
    names = sorted({f.get('source', {}).get('model', '') for f in facts} | {task.get('product', '')}, key=len, reverse=True)
    for i, block in enumerate(article.get('blocks', [])):
        if block.get('type') != 'text':
            continue
        before = block['text']
        text = re.sub(r'^第[一二三四1234]格[｜|：:、.\s]*', '', before)
        text = re.sub(r'^情景演绎[：:｜|\s]*', '', text)
        for name in names:
            if len(name) >= 8 and text.startswith(name):
                text = text[len(name):].lstrip(' :：，,｜|·—-')
                break  # 海报页眉和生图逐字文案已独立展示完整型号。
        if text and text != before:
            block['text'] = text
            changes.append({'field': f'blocks[{i}].text', 'before': before, 'after': text, 'reason': '移除编号或重复页眉型号，不截断事实与条件'})
    if changes:
        article['structure_adjustments'] = changes
    return article


VISUALS = {
    'interaction': '突出一个真实产品细节与一道评论征集问题。用提问卡与留白形成互动感；不画虚构网友头像、点赞量、评论内容或已获反馈。',
    'miniature': '用微缩城市／桌面世界作为产品之外的背景。将已选事实抽象映射为天幕、路径或空间节点；主电脑保持唯一真实产品，不把背景想象当实测能力。',
    'avatar': '设计原创试验角色作为旁边的小型叙事元素，保持统一语气。不得复制天选姬或任何现成IP形象；角色不是华为官方代言人。',
    'comic': '采用清晰的四格动漫小剧场，按任务、难处、有据动作、收尾顺序阅读。四格用人物和背景表达，真实产品只在一格出现一次，其余格不重画另一台电脑；每格短文只能使用批准文案。',
    'contrast': '选择一个简单醒目的视觉反差：规整与轻松、繁与简等。只围绕一个具体任务、一项事实；标题短，画面有故事感，不做长篇合唱或多角色大场面。',
    'twin': '用原创虚构人物与其概念分身形成现实／想象双视角，安排在一个生活任务中；不是用户真人肖像，不暗示产品具有生成数字孪生的能力。',
    'collaboration': '围绕已填拟议联动对象设计概念主题；不仿造授权徽章、官方联名Logo或真实合作公告。不改变产品结构或为其添加联名款能力，醒目标明非真实合作。',
    'question': '以一个具体选购问题为主标题，下方用准确事实和必要条件回答。信息层级清晰，不做伪横评和排行榜。',
    'theme': '围绕一个核心主题使用统一配色与视觉线索，突出一个入口；未确认活动时不画折扣、礼品或权益。',
    'topical': '只借本次提供议题的相关生活任务形成场景，不画热搜排名、新闻认证或编造社会反响。',
    'invitation': '以具体体验项目为中心，准确列批准的参与信息。演示资料必须保留演示标识，不伪装为门店实拍或正在举行的活动。',
}


def visual_brief(result):
    t = (result.get('planning') or {}).get('template') or (result.get('task') or {}).get('_template_plan')
    if not t:
        return None
    return {'case_id': t['id'], 'title': t['title'], 'source': t['source'],
            'user_note': t['user_note'], 'structure': t['pattern'], 'slots': t.get('filled_slots', []),
            'visual_direction': VISUALS[t['visual']], 'concept_subject': t.get('concept_subject', ''),
            'required_labels': disclosures(result.get('task') or {}, t),
            'product_pair': t.get('product_pair') or marketing_product_pairs.pair(t['id']),
            'fallback_url': marketing_product_pairs.fallback_url(t['id'])}
