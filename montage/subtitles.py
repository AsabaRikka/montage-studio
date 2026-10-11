from __future__ import annotations

import json
import re
from pathlib import Path


def read_srt(path: Path) -> list[dict]:
    raw = path.read_bytes()
    encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'gb18030')
    for enc in encodings:
        try:
            text = raw.decode(enc)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError('字幕编码无法识别，请另存为 UTF-8。')
    text = text.replace('\r\n', '\n').strip()
    if not text:
        return []
    stamp = r'(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})'
    pattern = re.compile(stamp + r'\s*-->\s*' + stamp + r'[^\n]*\n(.*?)(?=\n\s*\n|\Z)', re.S)
    result = []
    for match in pattern.finditer(text):
        groups = match.groups()
        def secs(offset):
            h, m, s, ms = map(int, groups[offset:offset + 4])
            return h * 3600 + m * 60 + s + ms / 1000
        start, end = secs(0), secs(4)
        line = re.sub(r'<[^>]*>', '', groups[8]).strip()
        if end <= start or not line:
            raise ValueError('字幕包含空行或结束时间早于开始时间，请检查。')
        result.append({'start': start, 'end': end, 'text': line})
    if not result:
        raise ValueError('没有读到有效 SRT 字幕。')
    return sorted(result, key=lambda x: x['start'])


def stamp(seconds: float, ass=False) -> str:
    ticks = round(max(0, seconds) * (100 if ass else 1000))
    base = 100 if ass else 1000
    sec, part = divmod(ticks, base)
    mins, sec = divmod(sec, 60)
    hour, mins = divmod(mins, 60)
    return f'{hour}:{mins:02}:{sec:02}.{part:02}' if ass else f'{hour:02}:{mins:02}:{sec:02},{part:03}'


def write_srt(path: Path, segments: list[dict]):
    path.write_text('\n\n'.join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i, s in enumerate(segments, 1)) + '\n', encoding='utf-8-sig')


def align_script(text, rows, duration):
    """Approximate supplied script timing using matched recognized characters.

    This is an editable initial alignment, not a forced phonetic alignment.
    Unmatched characters interpolate over matched anchors or source duration.
    """
    import difflib
    import numpy as np
    lines = [s.strip() for s in re.split(r'\n|(?<=[。！？!?；;])', text) if s.strip()]
    lines = [line[i:i+18] for line in lines for i in range(0,len(line),18)]
    if not lines:
        raise ValueError('请填写文稿。')
    script=''.join(lines)
    recognized='';times=[]
    for row in rows:
        t=row['text'].strip()
        recognized+=t
        times.extend(row['start']+(row['end']-row['start'])*i/max(1,len(t)) for i in range(len(t)))
    anchors={0:0.,len(script):duration}
    if recognized:
        for block in difflib.SequenceMatcher(None,script,recognized,autojunk=False).get_matching_blocks():
            for i in range(block.size):
                anchors[block.a+i]=times[block.b+i]
    xs=sorted(anchors)
    ys=np.maximum.accumulate([min(duration,max(0,anchors[x])) for x in xs])
    position=0;result=[]
    for line in lines:
        start=float(np.interp(position,xs,ys));position+=len(line)
        end=float(np.interp(position,xs,ys))
        if end-start<.08:
            raise ValueError('文稿与识别内容差异较大，自动对齐出现过短字幕。请按原识别时间手动修正。')
        result.append(dict(start=start,end=end,text=line))
    return result


def write_ass(path: Path, segments: list[dict], width: int, height: int, settings: dict, duration: float):
    size = max(14, round(settings['font_size'] * height / 1280))
    margin = round(settings['margin'] * height / 1280)
    color = settings['font_color'].lstrip('#')
    if not re.fullmatch('[0-9A-Fa-f]{6}', color):
        color = 'FFFFFF'
    primary = '&H00' + color[4:6] + color[2:4] + color[:2]
    align = {'bottom': 2, 'center': 5, 'top': 8}[settings['subtitle_position']]
    outline = settings['outline'] * height / 1280
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans SC,{size},{primary},&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},0,{align},30,30,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = [header]
    for segment in segments:
        start, end = max(0, segment['start']), min(duration, segment['end'])
        if end <= start:
            continue
        # Treat user text as plain text, never as ASS override commands.
        line = segment['text'].replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', r'\N')
        lines.append(f'Dialogue: 0,{stamp(start, True)},{stamp(end, True)},Default,,0,0,0,,{line}\n')
    path.write_text(''.join(lines), encoding='utf-8-sig')


def transcribe(audio: Path, output: Path, model: Path, language='zh', prompt=''):
    import os
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from faster_whisper import WhisperModel
    recognizer = WhisperModel(str(model), device='cpu', compute_type='int8', local_files_only=True,
                              cpu_threads=max(1, min(6, (os.cpu_count() or 4) // 2)))
    pieces, info = recognizer.transcribe(str(audio), language=None if language == 'auto' else language,
                                        vad_filter=True, beam_size=5, word_timestamps=True,
                                        initial_prompt=prompt or None, condition_on_previous_text=False)
    rows = []
    for segment in pieces:
        words = segment.words or []
        if not words:
            if segment.text.strip():
                rows.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip()})
            continue
        pending, start, end = '', None, None
        for word in words:
            if start is None:
                start = word.start
            pending += word.word
            end = word.end
            if len(pending.strip()) >= 18 or re.search(r'[。！？!?；;，,]$', pending.strip()):
                if end > start and pending.strip():
                    rows.append({'start': start, 'end': end, 'text': pending.strip()})
                pending, start = '', None
        if pending.strip() and end is not None and start is not None and end > start:
            rows.append({'start': start, 'end': end, 'text': pending.strip()})
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
