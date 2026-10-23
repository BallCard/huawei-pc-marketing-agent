"""Cut a real browser recording using its event marks; label compressed waits explicitly.

python -X utf8 scripts/edit_demo.py
Requires ffmpeg/ffprobe on PATH. Keeps the raw recording and per-task evidence unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def ass_time(seconds):
    cs = round(seconds * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='data/demo-recording')
    args = parser.parse_args()
    out = Path(args.directory).resolve()
    report = json.loads((out / 'recording.json').read_text(encoding='utf-8'))
    if report.get('failure'):
        raise SystemExit('Recording is incomplete; keep the source and resolve the failure before creating a success demo.')
    raw = Path(report['video']).resolve()
    duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                              '-of', 'default=nw=1:nk=1', str(raw)], text=True).strip())
    marks = report['marks']
    by_case = {case['id']: case for case in report['cases']}
    waits = []
    for start in (m for m in marks if m['kind'] in {'generation_start', 'generation_resume'}):
        # Clarifications are shown at real speed, outside the preceding generation interval.
        end = next((m for m in marks if m['at_seconds'] > start['at_seconds']
                    and m.get('case') == start['case'] and m['kind'] in {'clarification', 'generation_end'}), None)
        if end and end['at_seconds'] - start['at_seconds'] > 15:
            waits.append((start['at_seconds'], end['at_seconds'], start['case']))
    cursor = 0.0
    segments = []
    for start, end, case in waits:
        if start > cursor:
            segments.append((cursor, start, 1.0, None))
        speed = max(1.0, (end - start) / 9.0)
        segments.append((start, end, speed, case))
        cursor = end
    if duration > cursor:
        segments.append((cursor, duration, 1.0, None))
    filters = []
    timeline = []
    at = 0.0
    for n, (start, end, speed, case) in enumerate(segments):
        filters.append(f'[0:v]trim=start={start:.3f}:end={end:.3f},setpts=(PTS-STARTPTS)/{speed:.6f},fps=25[v{n}]')
        length = (end - start) / speed
        timeline.append({'source_start': start, 'source_end': end, 'speed': speed,
                         'edited_start': at, 'edited_end': at + length, 'case': case})
        at += length
    filters.append(''.join(f'[v{n}]' for n in range(len(segments))) + f'concat=n={len(segments)}:v=1:a=0,ass=demo-captions.ass[out]')
    (out / 'demo-filter.txt').write_text(';\n'.join(filters), encoding='utf-8')

    def edited_time(source):
        for segment in timeline:
            if segment['source_start'] <= source <= segment['source_end']:
                return segment['edited_start'] + (source - segment['source_start']) / segment['speed']
        return at

    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1600
PlayResY: 900
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,27,&H00FFFFFF,&H000000FF,&H00282828,&HA0000000,0,0,0,0,100,100,0,0,3,9,0,2,45,45,16,1
Style: Label,Microsoft YaHei,19,&H00FFFFFF,&H000000FF,&H00303030,&HA0000000,0,0,0,0,100,100,0,0,3,7,0,9,20,20,13,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = [header]
    def caption(start, end, text, style='Caption'):
        if end <= start:
            return
        safe = text.replace('{', '').replace('}', '').replace('\n', r'\N')
        lines.append(f'Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{safe}\n')

    caption(0, at, '真实网页操作录制 · 无配音初稿', 'Label')
    intro_end = next((m['at_seconds'] for m in marks if m['kind'] == 'case_start'), 8)
    caption(0, edited_time(intro_end), '华章有据｜从产品知识出发，生成有据可查的营销图文')
    for mark in marks:
        t = edited_time(mark['at_seconds'])
        if mark['kind'] == 'case_start':
            caption(t, min(at, t + 8), f"{mark['label']}｜一句话说明顾客与使用场景")
        elif mark['kind'] == 'work':
            case = by_case[mark['case']]
            status = '自动检查完成' if case.get('status') == 'ok' else '含待复核事项，以页面状态为准'
            caption(t, min(at, t + 7), f"{mark['label']}｜{status}")
        elif mark['kind'] == 'evidence':
            caption(t, min(at, t + 10), '回查本地产品资料、引用原句与条件；不代表 ima 实时读取')
        elif mark['kind'] == 'export':
            caption(max(0, t - 2), min(at, t + 3), '实际导出含图片的 HTML，发布仍由使用者完成')
    for seg in timeline:
        if seg['case']:
            seconds = seg['source_end'] - seg['source_start']
            caption(seg['edited_start'], seg['edited_end'], f'生成等待已加速 {seg["speed"]:.1f}×｜该段实际等待 {seconds:.1f} 秒')
    (out / 'demo-captions.ass').write_text(''.join(lines), encoding='utf-8-sig')
    (out / 'edit-timeline.json').write_text(json.dumps({'raw': str(raw), 'raw_duration': duration,
        'edited_duration': at, 'segments': timeline}, ensure_ascii=False, indent=2), encoding='utf-8')
    output = out / 'huazhang-demo-draft.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y', '-i', str(raw),
                    '-filter_complex_script', 'demo-filter.txt', '-map', '[out]', '-an',
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', str(output)], cwd=out, check=True)
    print(output)


if __name__ == '__main__':
    main()
