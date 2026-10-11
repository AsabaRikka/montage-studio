from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import random
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .runtime import asset, binary, data_dir, self_command
from .subtitles import read_srt, write_ass, write_srt

DEFAULTS = dict(pairing='single', transition='fade', transition_duration=0.5, audio_transition='crossfade',
                bgm='', bgm_start=0.0, bgm_volume=0.30, intro_volume=1.0, main_volume=1.0,
                bgm_fade=0.4, subtitles=False, language='zh', vocabulary='', font_size=52,
                font_color='#FFFFFF', margin=110, outline=3, subtitle_position='bottom',
                resolution='720x1280', fit='pad', fps=30, crf=20, encoder='cpu',
                output='', seed=42)


class Cancelled(Exception):
    pass


class Runner:
    def __init__(self, stop=None, log=None):
        self.stop = stop or threading.Event()
        self.log = log or (lambda _: None)

    def run(self, args, cwd=None, progress=None, duration=0):
        if self.stop.is_set():
            raise Cancelled('已停止')
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == 'nt' else 0
        process = subprocess.Popen([str(x) for x in args], cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, creationflags=flags, stdin=subprocess.DEVNULL)
        messages = queue.Queue()
        def reader():
            for line in iter(process.stdout.readline, b''):
                messages.put(line.decode('utf-8', errors='replace'))
            messages.put(None)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        result = []
        try:
            while True:
                if self.stop.is_set():
                    raise Cancelled('已停止，完成的文件会保留。')
                try:
                    line = messages.get(timeout=0.15)
                except queue.Empty:
                    continue
                if line is None:
                    break
                result.append(line)
                if progress and duration and line.startswith('out_time_us='):
                    try:
                        progress(min(99, int(float(line.split('=')[1]) / 1e6 / duration * 100)))
                    except ValueError:
                        pass
            process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            thread.join(timeout=2)
            process.stdout.close()
        output = ''.join(result)
        if process.returncode:
            self.log(output[-6000:])
            raise RuntimeError(output[-2200:] or f'处理组件退出：{process.returncode}')
        return output

    def ffmpeg(self, args, **kwargs):
        return self.run([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                         '-filter_complex_threads', '2', *args], **kwargs)


def probe(path: Path, runner=None):
    runner = runner or Runner()
    info = json.loads(runner.run([binary('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next((s for s in info.get('streams', []) if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    audio = next((s for s in info.get('streams', []) if s['codec_type'] == 'audio'), None)
    if not video and not audio:
        raise ValueError(f'无法读取媒体：{path.name}')
    raw_duration = (video or {}).get('duration') or info.get('format', {}).get('duration') or (audio or {}).get('duration')
    duration = float(raw_duration or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f'无法读取媒体时长：{path.name}')
    width, height = (video or {}).get('width', 0), (video or {}).get('height', 0)
    if video:
        sar = video.get('sample_aspect_ratio', '1:1')
        if re.fullmatch(r'\d+:\d+', sar):
            a, b = map(int, sar.split(':'))
            if a and b:
                width = round(width * a / b)
        rotation = next((int(float(s.get('rotation', 0))) for s in video.get('side_data_list', []) if 'rotation' in s), 0)
        if abs(rotation) % 180 == 90:
            width, height = height, width
    return dict(duration=duration, video=video, audio=audio, width=width, height=height)


def signature(path):
    path = Path(path).resolve()
    stat = path.stat()
    return [str(path), stat.st_size, stat.st_mtime_ns]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def make_pairs(intros, mains, mode, seed=42):
    if not intros or not mains:
        raise ValueError('请先添加前贴和主视频。')
    if mode == 'single':
        return [(intros[0], m) for m in mains]
    if mode == 'all':
        return [(i, m) for m in mains for i in intros]
    if mode == 'sequence':
        return [(intros[n % len(intros)], m) for n, m in enumerate(mains)]
    if mode == 'random':
        rng = random.Random(seed)
        return [(rng.choice(intros), m) for m in mains]
    raise ValueError('未知配对方式')


def dimensions(settings, info):
    if settings['resolution'] == 'source':
        return max(2, round(info['width'] / 2) * 2), max(2, round(info['height'] / 2) * 2)
    w, h = map(int, settings['resolution'].split('x'))
    return w, h


def video_filter(w, h, fps, fit, duration):
    if fit == 'crop':
        scale = f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2:reset_sar=1,crop={w}:{h}'
    else:
        scale = f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black'
    return f'{scale},setsar=1,fps={fps},format=yuv420p,tpad=stop_mode=clone:stop_duration=1,trim=duration={duration:.6f},settb=AVTB,setpts=PTS-STARTPTS'


def audio_filter(volume, duration):
    return f'aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={volume},apad,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS'


def watermark_filter(path, settings, info):
    """Repair a normalized source rectangle before any output crop/padding."""
    region = settings.get('watermarks', {}).get(str(Path(path).resolve()))
    if not region:
        return ''
    values = [float(region[k]) for k in ('x', 'y', 'w', 'h')]
    x, y, rw, rh = values
    if not all(math.isfinite(v) for v in values) or min(x, y) < 0 or min(rw, rh) <= 0 or x+rw > 1.00001 or y+rh > 1.00001:
        raise ValueError('水印区域必须位于视频画面内。')
    w, h = info['width'], info['height']
    left, top = max(1, round(x*w)), max(1, round(y*h))
    right, bottom = min(w-1, round((x+rw)*w)), min(h-1, round((y+rh)*h))
    if right-left < 4 or bottom-top < 4:
        raise ValueError('水印区域太小，请重新框选。')
    return f'scale={w}:{h},setsar=1,delogo=x={left}:y={top}:w={right-left}:h={bottom-top},'


def preview_frame(path, settings, seconds, output, segments=None, source_size=False, runner=None):
    """Render the same source repair and ASS styling used by the export pipeline."""
    runner = runner or Runner()
    info = probe(Path(path), runner)
    if not info['video']:
        raise ValueError('素材不包含视频画面。')
    w, h = (info['width'], info['height']) if source_size else dimensions(settings, info)
    at = max(0, min(float(seconds), info['duration']-1/settings['fps']))
    # Seek at the input for speed; restore the timeline for ASS before rendering.
    chain = watermark_filter(path, settings, info)
    chain += video_filter(w, h, settings['fps'], settings['fit'], info['duration'])
    chain += f',setpts=PTS+{at:.6f}/TB'
    folder = Path(output).parent
    folder.mkdir(parents=True, exist_ok=True)
    ass = folder / (uuid.uuid4().hex + '.ass')
    try:
        if segments is not None:
            fonts = folder / 'fonts'
            fonts.mkdir(exist_ok=True)
            for font in asset('fonts').glob('*tf'):
                if not (fonts / font.name).exists():
                    shutil.copy2(font, fonts / font.name)
            write_ass(ass, segments, w, h, settings, info['duration'])
            chain += f',subtitles={ass.name}:fontsdir=fonts'
        runner.ffmpeg(['-ss', str(at), '-i', path, '-vf', chain, '-frames:v', '1', '-threads', '2', output], cwd=folder)
    finally:
        ass.unlink(missing_ok=True)
    return info


class Engine:
    def __init__(self, stop=None, log=None, data=None):
        self.log = log or (lambda _: None)
        self.runner = Runner(stop, self.log)
        self.data = Path(data) if data else data_dir()
        self.cache = self.data / 'cache'
        self.cache.mkdir(parents=True, exist_ok=True)
        fonts = self.cache / 'fonts'
        fonts.mkdir(exist_ok=True)
        for font in asset('fonts').glob('*tf'):
            if not (fonts / font.name).exists():
                shutil.copy2(font, fonts / font.name)
        self.db = sqlite3.connect(self.data / 'tasks.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, output TEXT, status TEXT, error TEXT, updated REAL)')
        self.db.commit()

    def close(self):
        self.db.close()

    def subtitle_key(self, intro, settings):
        return digest([signature(intro), settings['language'], settings['vocabulary'], 'small-v1'])

    def subtitle_path(self, intro, settings):
        return self.cache / (self.subtitle_key(intro, settings) + '.srt')

    def ensure_subtitles(self, intro, settings, custom=None):
        if custom:
            return read_srt(Path(custom))
        path = self.subtitle_path(intro, settings)
        if path.exists():
            # Empty transcription is cached explicitly to avoid repeated inference on silent media.
            return read_srt(path)
        info = probe(Path(intro), self.runner)
        if not info['audio']:
            self.log(f'{Path(intro).name} 没有人声音轨，跳过自动字幕。')
            write_srt(path, [])
            return []
        model = asset('models') / 'small'
        if not (model / 'model.bin').is_file():
            raise RuntimeError('缺少离线字幕模型，请使用完整便携包，或导入 SRT 字幕。')
        key = path.stem
        wav = self.cache / (key + '.wav')
        result = self.cache / (key + '.json')
        self.log(f'正在识别前贴口播：{Path(intro).name}（首次识别需要一些时间）')
        self.runner.ffmpeg(['-i', intro, '-map', '0:a:0', '-vn', '-ar', '16000', '-ac', '1', wav])
        try:
            self.runner.run(self_command('--transcribe', str(wav), str(result), str(model), settings['language'], settings['vocabulary']))
            segments = json.loads(result.read_text(encoding='utf-8'))
            write_srt(path, segments)
            if not segments:
                self.log('未识别到口播，可在“编辑字幕”中导入或手动添加。')
            return segments
        finally:
            wav.unlink(missing_ok=True)

    def prefix(self, intro, settings, w, h, custom=None):
        info = probe(Path(intro), self.runner)
        if not info['video']:
            raise ValueError('前贴必须是视频文件。')
        fps = settings['fps']
        duration = max(1 / fps, round(info['duration'] * fps) / fps)
        segments = self.ensure_subtitles(intro, settings, custom) if settings['subtitles'] else []
        relevant = {k: settings[k] for k in ('fps', 'fit', 'bgm_start', 'bgm_volume', 'intro_volume', 'bgm_fade', 'font_size', 'font_color', 'margin', 'outline', 'subtitle_position')}
        repair = watermark_filter(intro, settings, info)
        key = digest([signature(intro), signature(settings['bgm']) if settings['bgm'] else None, relevant, w, h, segments, repair, 'prefix-v4'])
        output = self.cache / (key + '.mp4')
        if output.exists():
            return output, duration
        self.log(f'正在制作前贴：{Path(intro).name}')
        filters = [f"[0:v:0]{repair}{video_filter(w, h, fps, settings['fit'], duration)}[iv]"]
        if segments:
            ass = self.cache / (key + '.ass')
            write_ass(ass, segments, w, h, settings, duration)
            filters.append(f'[iv]subtitles={ass.name}:fontsdir=fonts[v]')
        else:
            filters.append('[iv]null[v]')
        if info['audio']:
            filters.append(f"[0:a:0]{audio_filter(settings['intro_volume'], duration)}[voice]")
        else:
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[voice]')
        args = ['-i', intro]
        if settings['bgm']:
            music = probe(Path(settings['bgm']), self.runner)
            if not music['audio']:
                raise ValueError('所选 BGM 没有可用音轨。')
            if settings['bgm_start'] >= music['duration']:
                raise ValueError(f"BGM 起点超出音乐时长（{music['duration']:.1f} 秒）。")
            args += ['-stream_loop', '-1', '-ss', str(settings['bgm_start']), '-i', settings['bgm']]
            fade = min(settings['bgm_fade'], duration / 2)
            filters.append(f"[1:a:0]{audio_filter(settings['bgm_volume'], duration)},afade=t=in:d={fade},afade=t=out:st={duration-fade}:d={fade}[music]")
            filters.append('[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[a]')
        else:
            filters.append('[voice]alimiter=limit=0.95:latency=1[a]')
        temp = self.cache / (key + '.partial.mp4')
        try:
            self.runner.ffmpeg(args + ['-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]',
                                      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-threads', '4',
                                      '-c:a', 'aac', '-b:a', '192k', '-t', str(duration), '-movflags', '+faststart', temp], cwd=self.cache)
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
        return output, duration

    def render(self, intro, main, settings, custom=None, progress=None, preview=False):
        main_info = probe(Path(main), self.runner)
        if not main_info['video']:
            raise ValueError('主视频必须包含画面。')
        w, h = dimensions(settings, main_info)
        prefix, prefix_duration = self.prefix(intro, settings, w, h, custom)
        fps = settings['fps']
        main_duration = max(1/fps, round(main_info['duration'] * fps) / fps)
        if preview:
            main_duration = min(main_duration, 5)
        transition = settings['transition']
        d = 0 if transition == 'cut' else round(settings['transition_duration'] * fps) / fps
        d = min(d, max(0, prefix_duration - 1/fps), max(0, main_duration - 1/fps))
        if d < 1 / fps:
            d, transition = 0, 'cut'
        expected = prefix_duration + main_duration - d
        if d and d + 0.001 < settings['transition_duration']:
            self.log(f'素材较短，转场时长自动缩短为 {d:.2f} 秒。')
        sub = signature(custom) if custom else None
        job_key = digest([signature(main), signature(prefix), settings, sub, preview, 'render-v3'])
        destination = self.data / 'previews' if preview else Path(settings['output'])
        destination.mkdir(parents=True, exist_ok=True)
        def safe_name(value):
            return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(value).stem)[:45].strip(' .') or 'video'
        output = destination / f'{safe_name(main)}__{safe_name(intro)}__{job_key[:8]}.mp4'
        row = self.db.execute('SELECT output,status FROM tasks WHERE id=?', (job_key,)).fetchone()
        if row and row[1] == '完成' and Path(row[0]).is_file():
            try:
                saved = probe(Path(row[0]), self.runner)
                if abs(saved['duration'] - expected) < 0.3 and saved['audio'] and saved['video']:
                    self.log(f'跳过已完成：{Path(row[0]).name}')
                    if progress:
                        progress(100)
                    return Path(row[0]), True
            except (RuntimeError, ValueError):
                pass
        if output.exists():
            output = output.with_stem(output.stem + '_' + uuid.uuid4().hex[:6])
        self.set_status(job_key, output, '处理中')
        temp = destination / (output.stem + '.' + uuid.uuid4().hex[:8] + '.partial.mp4')
        filters = [f'[0:v:0]settb=AVTB,setpts=PTS-STARTPTS[v0]',
                   f"[1:v:0]{watermark_filter(main, settings, main_info)}{video_filter(w,h,fps,settings['fit'],main_duration)}[v1]",
                   f'[0:a:0]{audio_filter(1, prefix_duration)}[a0]']
        if main_info['audio']:
            filters.append(f"[1:a:0]{audio_filter(settings['main_volume'],main_duration)}[a1]")
        else:
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={main_duration}[a1]')
        if transition == 'cut':
            filters += ['[v0][v1]concat=n=2:v=1:a=0[v]', '[a0][a1]concat=n=2:v=0:a=1[a]']
        else:
            filters.append(f'[v0][v1]xfade=transition={transition}:duration={d:.6f}:offset={prefix_duration-d:.6f},format=yuv420p[v]')
            if settings['audio_transition'] == 'crossfade':
                filters.append(f'[a0][a1]acrossfade=d={d:.6f}:c1=tri:c2=tri[a]')
            else:
                # Cut audio at the middle of the visual overlap, retaining the same timeline.
                filters += [f'[a0]atrim=end={prefix_duration-d/2:.6f}[ac0]',
                            f'[a1]atrim=start={d/2:.6f},asetpts=PTS-STARTPTS[ac1]',
                            '[ac0][ac1]concat=n=2:v=0:a=1[a]']
        common = ['-i', prefix, '-i', main, '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]']
        tail = ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                '-t', f'{expected:.6f}', '-movflags', '+faststart', '-progress', 'pipe:1', temp]
        cpu = ['-c:v', 'libx264', '-crf', str(settings['crf']), '-preset', 'veryfast', '-threads', '4']
        try:
            if settings['encoder'] == 'nvidia':
                try:
                    self.runner.ffmpeg(common + ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', str(settings['crf']), '-b:v', '0'] + tail, duration=expected, progress=progress)
                except RuntimeError:
                    self.log('显卡编码不可用，已自动改用 CPU。')
                    self.runner.ffmpeg(common + cpu + tail, duration=expected, progress=progress)
            else:
                self.runner.ffmpeg(common + cpu + tail, duration=expected, progress=progress)
            result = probe(temp, self.runner)
            if not result['video'] or not result['audio'] or abs(result['duration']-expected) > 0.3:
                raise RuntimeError('导出结果时长或音视频轨道异常，未标记为完成。')
            os.replace(temp, output)
            self.set_status(job_key, output, '完成')
            if progress:
                progress(100)
            return output, False
        except Exception as exc:
            self.set_status(job_key, output, '已停止' if isinstance(exc, Cancelled) else '失败', str(exc))
            raise
        finally:
            temp.unlink(missing_ok=True)

    def set_status(self, key, output, status, error=''):
        self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?)', (key, str(output), status, error, time.time()))
        self.db.commit()
