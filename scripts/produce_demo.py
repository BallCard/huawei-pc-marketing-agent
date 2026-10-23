"""Create a narrated, focused product demo from real browser recordings (all outputs on D:).

Uses the installed edge-tts package from data/demo-tools/python and ffmpeg on PATH.
Does not modify application state or any recorded generation result.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'data' / 'demo-production'
OUT = ROOT / 'output' / 'demo'
TEMP = ROOT / 'data' / 'demo-temp'
for folder in (WORK, OUT, TEMP):
    folder.mkdir(parents=True, exist_ok=True)
os.environ['TEMP'] = os.environ['TMP'] = str(TEMP)
sys.path.insert(0, str(ROOT / 'data' / 'demo-tools' / 'python'))


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def probe(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                         '-of', 'default=nw=1:nk=1', str(path)], text=True))


def at(report, kind, case=None):
    return next(m['at_seconds'] for m in report['marks'] if m['kind'] == kind
                and (case is None or m.get('case') == case))


def ass_time(t):
    centis = max(0, round(t * 100))
    return f'{centis//360000}:{centis//6000%60:02}:{centis//100%60:02}.{centis%100:02}'


async def voice(text, path):
    import edge_tts
    await edge_tts.Communicate(text, 'zh-CN-YunxiNeural', rate='+3%', volume='+0%',
                               boundary='WordBoundary').save(str(path), str(path.with_suffix('.jsonl')))


def subtitle_cues(item):
    """Keep punctuation from the script and use actual speech word boundaries."""
    text = item['text']
    events = [json.loads(line) for line in Path(item['audio']).with_suffix('.jsonl').read_text(encoding='utf-8').splitlines()]
    words = []
    cursor = 0
    for event in events:
        word = html.unescape(event['text'])
        pos = text.find(word, cursor)
        if pos < 0:
            raise ValueError(f'Cannot align narration token {word!r} in {item["id"]}')
        words.append((pos, (event['offset'] / 1e7), (event['offset'] + event['duration']) / 1e7))
        cursor = pos + len(word)
    if not words:
        raise ValueError(f'No timed narration tokens for {item["id"]}')
    groups = []
    start = 0
    for i in range(1, len(words)):
        previous = text[words[i-1][0]:words[i][0]]
        if words[i][0] - words[start][0] >= 27 or (any(c in previous for c in '，。；？！：') and words[i][0]-words[start][0]>=10):
            groups.append((start, i))
            start = i
    groups.append((start, len(words)))
    for start, stop in groups:
        last = words[stop][0] if stop < len(words) else len(text)
        end = words[stop][1]-0.03 if stop < len(words) else words[-1][2]+0.15
        yield words[start][1], end, text[words[start][0]:last]


def make_intro(path, title, subtitle, tag, screenshot):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    canvas = Image.new('RGB', (1920, 1080), '#101922')
    draw = ImageDraw.Draw(canvas)
    font = lambda size: ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', size)
    # Use an actual application screenshot, visibly presented as the product illustration.
    shot = Image.open(screenshot).convert('RGB').resize((1024, 576))
    shadow = Image.new('RGBA', canvas.size)
    ImageDraw.Draw(shadow).rounded_rectangle((835, 258, 1865, 844), 25, fill=(0, 0, 0, 145))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    canvas = Image.alpha_composite(canvas.convert('RGBA'), shadow)
    canvas.paste(shot, (827, 245))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((86, 140, 352, 192), 26, fill='#cc7755')
    draw.text((111, 147), tag, font=font(24), fill='white')
    y = 290
    for line in title.split('\n'):
        draw.text((86, y), line, font=font(70), fill='#fff6e8', stroke_width=1)
        y += 110
    for n, line in enumerate(subtitle.split('\n')):
        draw.text((92, y + 48 + 47*n), line, font=font(28), fill='#bbc6cd')
    draw.text((92, 930), '华章有据  /  真实产品演示', font=font(25), fill='#d69a7d')
    canvas.convert('RGB').save(path)


def sources():
    first = json.loads((ROOT / 'data/demo-recording/retry/recording.json').read_text(encoding='utf-8'))
    comparison_path = ROOT / 'data/demo-recording/comparison/recording.json'
    second = json.loads(comparison_path.read_text(encoding='utf-8')) if comparison_path.exists() else None
    moments_path = ROOT / 'data/demo-recording/comparison-moments/recording.json'
    if second and moments_path.exists():
        moments = json.loads(moments_path.read_text(encoding='utf-8'))
        if not moments.get('failure') and moments.get('video') and moments.get('cases'):
            second['cases'] = [c for c in second['cases'] if c['id'] != 'office-moments'] + moments['cases']
            second['moments_directory'] = str(moments_path.parent)
    if first.get('failure'):
        raise RuntimeError('Primary recording failed; a success demonstration cannot be fabricated.')
    return first, second


def scenes(first, second):
    case = first['cases'][0]
    raw = first['video']
    elapsed = round(case['elapsed_ms'] / 1000)
    p = ROOT / 'data/demo-recording/retry'
    result = [
        {'id':'opening', 'title':'让门店创作，少一点负担', 'card':'intro', 'text':
         '如果你是门店销售，接待完顾客，还要找资料、挑图片，再给小红书和朋友圈写推文。用统一稿，怕顾客不感兴趣；自己用AI写，又怕参数和承诺不准确。华章有据，想把这件事变简单。'},
        {'id':'input','title':'01  一句话说明顾客和场景','raw':raw,'start':at(first,'case_start'),'end':at(first,'generation_start'),'focus':(0.75,0.53),'zoom':1.16,'text':
         '我们直接打开工作台。切到“说一句话”，告诉它：给每天背电脑去图书馆的大学新生，写一篇突出携带和U盘使用的小红书。选好型号和发布平台，就可以开始。信息不够时，系统会给选项追问，最多两轮。'},
        {'id':'process','title':'02  真实任务：从资料到核验','raw':raw,'start':at(first,'generation_start'),'end':at(first,'generation_end'),'focus':(0.53,0.47),'zoom':1.05,
         'badge':f'真实生成等待已加速｜本次任务实际 {elapsed} 秒','text':
         f'接下来是这一次任务的真实处理过程。系统先理解需求，再选资料和内容角度，完成写作、检查和修订。这里压缩了等待，本次实际用时约{elapsed}秒。生成之后，还要继续看它的证据和审核状态。'},
        {'id':'result','title':'03  先看真实交付的作品','image':str(p/'student-xhs-work.png'),'focus':(0.77,0.47),'zoom':1.25,'text':
         '现在看成稿。标题是“背去图书馆，U盘直接插”。正文围绕携带和接口展开，配了三张同型号产品图，也给出了到店体验的引导。右侧是文案，左侧可以继续打磨语气和卖点。'},
        {'id':'mobile','title':'电脑和手机，检查不同阅读效果','raw':raw,'start':at(first,'work')+3,'end':at(first,'evidence')-1,'focus':(0.62,0.48),'zoom':1.08,'text':
         '再切到手机预览，看一眼顾客实际阅读时的版式。内容和图片在同一个作品里，店员可以继续调整，再复制或导出。'},
    ]
    if second and not second.get('failure') and len(second.get('cases', [])) >= 2:
        cdir=ROOT/'data/demo-recording/comparison'
        result += [
            {'id':'audience','title':'04  换一类顾客，检查内容变化','image':str(cdir/'office-xhs-work.png'),'focus':(0.77,0.46),'zoom':1.20,'text':
             '保持同一款产品，把读者换成经常拜访客户的职场新人。标题变成了“第一次带电脑见客户，U盘往哪插”，开头也换成了客户拜访。不过，两份稿子都集中在携带和接口，场景差异还可以继续拉开。'},
            {'id':'platform','title':'再换平台：门店朋友圈','image':str(Path(second.get('moments_directory',str(cdir)))/'office-moments-work.png'),'focus':(0.66,0.49),'zoom':1.15,'text':
             '同一个办公任务，再换成朋友圈。这里输出了短文和两张配图。当前结果仍有篇幅和接口承诺的审核异议，系统把它标为待复核；店员需要处理后再发表。'},
        ]
    result += [
        {'id':'evidence','title':'05  把关键主张，带回原始依据','image':str(p/'student-xhs-evidence.png'),'focus':(0.49,0.58),'zoom':1.28,'text':
         '这时点开事实核验。比如重量，不只保留一个数字，还区分键盘版本，并保留含电池等条件。引用的原句、资料来源和已用事实都能回查。当前演示使用本地资料包，实时接入知识库，是下一步要补齐的能力。'},
        {'id':'review','title':'审核状态如实保留','image':str(p/'student-xhs-review.png'),'focus':(0.50,0.49),'zoom':1.18,'text':
         '这一次仍有一项待处理：某段正文超过了项目设定的长度。界面保留了提示，也列出尚无依据的兼容和体验信息。自动审核的价值，是让问题可以继续处理；一份生成结果，还需要按它的实际状态判断。'},
        {'id':'export','title':'06  复制正文，导出含图片的 HTML','raw':raw,'start':at(first,'export')-4.5,'end':at(first,'case_end'),'focus':(0.17,0.81),'zoom':1.19,'text':
         '最后，店员可以复制正文，或导出含图片的HTML。发布仍由店员完成。接下来最值得优化的，是把文案和图片整理成更方便使用的素材包，让最后几步也更省力。'},
        {'id':'ending','title':'让好故事，有据可查','card':'ending','text':
         '华章有据已经串起了需求、资料、图文、核验和导出的流程。下一步，我们会用少量门店试用，验证操作时间、修改量和发布意愿，再补上门店自己的信息与近期选题。让好产品有好故事，也让故事有据可查。'},
    ]
    return result


def render_scene(item, length):
    output=WORK/f'{item["id"]}-visual.mp4'
    args=['ffmpeg','-hide_banner','-loglevel','error','-y']
    if item.get('raw'):
        source_length=item['end']-item['start']
        args+=['-ss',str(item['start']),'-t',str(source_length),'-i',item['raw']]
        timing=f'setpts=(PTS-STARTPTS)*{length/source_length:.8f},'
    else:
        args+=['-loop','1','-framerate','25','-i',item['image']]
        timing=''
    # Slow eased zoom towards the referenced area; the return occurs at the next full shot.
    zoom=item.get('zoom',1.02)
    fx,fy=item.get('focus',(0.5,0.5))
    frames=max(1,round(length*25))
    z=f'1+({zoom}-1)*min(on/{max(1,min(70,frames-1))},1)'
    x=f'min(max(iw*{fx}-iw/zoom/2,0),iw-iw/zoom)'
    y=f'min(max(ih*{fy}-ih/zoom/2,0),ih-ih/zoom)'
    # zoompan d=1 preserves source motion; subsequent scale/pad provides clean room for subtitles.
    filt=f'{timing}fps=25,scale=1600:900,zoompan=z=\'{z}\':x=\'{x}\':y=\'{y}\':d=1:s=1600x900:fps=25,scale=1712:963,pad=1920:1080:104:32:color=0x101922,setsar=1'
    args+=['-vf',filt,'-t',str(length),'-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(output)]
    command(args)
    return output


async def main():
    first,second=sources()
    items=scenes(first,second)
    make_intro(WORK/'intro.png','把写推文\n变成一句话','少填需求 · 查到依据\n真实产品演示', '华章有据  DEMO', ROOT/'data/demo-recording/retry/student-xhs-work.png')
    make_intro(WORK/'ending.png','好产品\n值得好故事','下一步：少量门店试用\n验证省时、修改量与发布意愿', '华章有据  下一步', ROOT/'data/demo-recording/retry/student-xhs-work.png')
    for item in items:
        if item.get('card'):
            item['image']=str(WORK/f'{item["card"]}.png')
            item['zoom']=1.02
    # Speech is sequential and cached; restarting the renderer does not make duplicate requests.
    for item in items:
        audio=WORK/f'{item["id"]}.mp3'
        digest=hashlib.sha256((item['text']+'|zh-CN-YunxiNeural|+3%|WordBoundary').encode()).hexdigest()
        cache=audio.with_suffix('.sha256')
        if not audio.exists() or audio.stat().st_size<1000 or not audio.with_suffix('.jsonl').exists() or not cache.exists() or cache.read_text()!=digest:
            for attempt in range(5):
                try:
                    await voice(item['text'],audio)
                    cache.write_text(digest)
                    break
                except Exception:
                    if attempt==4:raise
                    await asyncio.sleep(2+attempt*2)
        item['audio']=str(audio)
        item['duration']=math.ceil((probe(audio)+1.0)*25)/25
        print(json.dumps({'scene':item['id'],'seconds':item['duration']},ensure_ascii=False),flush=True)
    (WORK/'scenes.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
    for item in items:
        visual=render_scene(item,item['duration'])
        part=WORK/f'{item["id"]}-part.mp4'
        command(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(visual),'-i',item['audio'],
                 '-map','0:v','-map','1:a','-c:v','copy','-af','apad','-t',str(item['duration']),
                 '-c:a','aac','-b:a','192k',str(part)])
    (WORK/'concat.txt').write_text(''.join(f"file '{item['id']}-part.mp4'\n" for item in items),encoding='utf-8')
    intermediate=WORK/'narrated-clean.mp4'
    command(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(WORK/'concat.txt'),'-c','copy',str(intermediate)])
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Microsoft YaHei,30,&H00FFFFFF,&H000000FF,&H00101820,&HA0000000,0,0,0,0,100,100,0,0,3,9,0,2,60,60,21,1
Style: Title,Microsoft YaHei,26,&H00DDA888,&H000000FF,&H00101820,&HA0000000,1,0,0,0,100,100,0,0,3,8,0,7,105,12,10,1
Style: Badge,Microsoft YaHei,22,&H00FFFFFF,&H000000FF,&H00101820,&HA0000000,0,0,0,0,100,100,0,0,3,8,0,9,20,105,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[header]
    srt=[]
    offset=0.0
    for item in items:
        end=offset+item['duration']
        lines.append(f'Dialogue: 1,{ass_time(offset)},{ass_time(end)},Title,,0,0,0,,{item["title"]}\n')
        badge=item.get('badge','真实界面素材 · AI 中文配音')
        lines.append(f'Dialogue: 1,{ass_time(offset)},{ass_time(end)},Badge,,0,0,0,,{badge}\n')
        for start,stop,chunk in subtitle_cues(item):
            lines.append(f'Dialogue: 2,{ass_time(offset+start)},{ass_time(offset+stop)},Subtitle,,0,0,0,,{chunk}\n')
            srt.append({'start':offset+start,'end':offset+stop,'text':chunk})
        item['output_start']=offset
        offset=end
    (WORK/'narration.ass').write_text(''.join(lines),encoding='utf-8-sig')
    final=OUT/'华章有据-复赛演示-配音聚焦版.mp4'
    command(['ffmpeg','-hide_banner','-loglevel','warning','-y','-i',str(intermediate),'-vf','ass=narration.ass',
             '-c:v','libx264','-preset','fast','-crf','19','-af','aresample=async=1:first_pts=0,loudnorm=I=-16:TP=-1.5:LRA=11',
             '-ar','48000','-c:a','aac','-b:a','192k','-movflags','+faststart',str(final)],cwd=WORK)
    command(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(final),'-vn','-af','aresample=async=1:first_pts=0',
             '-c:a','libmp3lame','-q:a','2',str(OUT/'中文旁白.mp3')])
    def srt_time(t):
        ms=round(t*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    (OUT/'中文字幕.srt').write_text('\n'.join(f'{n}\n{srt_time(s["start"])} --> {srt_time(s["end"])}\n{s["text"]}\n' for n,s in enumerate(srt,1)),encoding='utf-8-sig')
    (OUT/'配音稿.txt').write_text('\n\n'.join(f'{item["title"]}\n{item["text"]}' for item in items),encoding='utf-8')
    (WORK/'final-manifest.json').write_text(json.dumps({'video':str(final),'duration':probe(final),'voice':'zh-CN-YunxiNeural',
        'ai_narration':True,'primary_job':first['cases'][0], 'comparison_cases':second.get('cases',[]) if second else [],
        'all_output_and_temp_on_drive_D':True,'scene_manifest':items},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'video':str(final),'duration':probe(final)},ensure_ascii=False),flush=True)


if __name__=='__main__':
    asyncio.run(main())
