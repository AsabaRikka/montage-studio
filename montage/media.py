from __future__ import annotations
import json
import os
import shutil
import uuid
from pathlib import Path
from .core import Engine, probe, signature, digest, video_filter, audio_filter, Cancelled
from .runtime import asset, self_command
from .subtitles import write_ass, read_srt


class MediaEngine(Engine):
    """Prepare unique source variants once; hard cuts copy the cached H264 stream."""

    def separated(self, source):
        key = digest([signature(source), 'mdx-hq3-residual-v1'])
        out = self.cache/(key+'.voice.wav')
        if out.is_file():
            return out
        self.log('尝试去旧音乐：'+Path(source).name+'（完成后请试听口播及音效）')
        wav, temp = self.cache/(key+'.mix.wav'), self.cache/(key+'.partial.wav')
        try:
            self.runner.ffmpeg(['-i', source, '-vn', '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', wav])
            self.runner.run(self_command('--separate', str(wav), str(temp), str(asset('models')/'separation'/'UVR-MDX-NET-Inst_HQ_3.onnx')))
            os.replace(temp, out)
        finally:
            wav.unlink(missing_ok=True)
            temp.unlink(missing_ok=True)
        return out

    def encoding(self, s, hardware=False):
        if hardware and s.get('encoder') == 'nvidia':
            return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', str(s['crf']), '-b:v', '0', '-g', str(s['fps']*2), '-bf', '0']
        return ['-c:v', 'libx264', '-crf', str(s['crf']), '-preset', 'veryfast', '-threads', '3' if s.get('performance') != 'full' else '8', '-g', str(s['fps']*2), '-bf', '0']

    def encode(self, common, tail, s, progress=None, duration=0):
        if s.get('encoder') == 'nvidia':
            try:
                self.runner.ffmpeg(common+self.encoding(s, True)+tail, duration=duration, progress=progress, cwd=self.cache)
                return
            except RuntimeError:
                self.log('硬件编码不可用，自动改用CPU编码。')
        self.runner.ffmpeg(common+self.encoding(s)+tail, duration=duration, progress=progress, cwd=self.cache)

    def prepare(self, source, s, side, custom=None):
        info = probe(Path(source), self.runner)
        if not info['video']:
            raise ValueError('素材不包含视频画面：'+Path(source).name)
        w, h = map(int, s['resolution'].split('x'))
        fps = s['fps']
        duration = max(1/fps, round(info['duration']*fps)/fps)
        segments = (s.get('subtitle_rows') if s.get('subtitle_rows') is not None else self.ensure_subtitles(source, s, custom)) if side == 'a' and s['subtitles'] else []
        mode = s.get(side+'_sound', 'original')
        music = s.get(side+'_music', '')
        external = s.get(side+'_voice', '')
        offset = s.get(side+'_music_start', 0.)
        relevant = {k: s.get(k) for k in ('fps', 'fit', 'crf', 'encoder', 'font_size', 'font_color', 'margin', 'outline', 'subtitle_position')}
        relevant.update(mode=mode, music_start=offset, music_volume=s.get(side+'_music_volume', .3), volume=s.get(side+'_volume', 1.))
        key = digest([signature(source), signature(music) if music else None, signature(external) if external and mode == 'external' else None, relevant, w, h, segments, 'normalized-v1'])
        result, temp = self.cache/(key+'.mp4'), self.cache/(key+'.partial.mp4')
        if result.is_file():
            return result, duration
        self.log('准备'+('前贴：' if side == 'a' else '主视频：')+Path(source).name)
        args = ['-i', source]
        filters = [f'[0:v:0]{video_filter(w,h,fps,s["fit"],duration)}[iv]']
        if segments:
            ass = self.cache/(key+'.ass')
            write_ass(ass, segments, w, h, s, duration)
            filters.append(f'[iv]subtitles={ass.name}:fontsdir=fonts[v]')
        else:
            filters.append('[iv]null[v]')
        sound_index = 0
        inputs = 1
        if mode == 'external':
            if not external or not probe(Path(external), self.runner)['audio']:
                raise ValueError('请指定包含声音的独立口播/音效文件。')
            args += ['-i', external]
            sound_index, inputs = inputs, inputs+1
        elif mode == 'separate' and info['audio']:
            args += ['-i', self.separated(source)]
            sound_index, inputs = inputs, inputs+1
        elif mode not in ('original', 'mute', 'separate'):
            raise ValueError('未知声音模式。')
        if mode != 'mute' and (info['audio'] or mode == 'external'):
            filters.append(f'[{sound_index}:a:0]{audio_filter(s.get(side+"_volume",1.),duration)}[voice]')
        else:
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[voice]')
        if music:
            mi = probe(Path(music), self.runner)
            if not mi['audio'] or not 0 <= offset < mi['duration']:
                raise ValueError('音乐没有音轨，或起点超出音乐时长：'+Path(music).name)
            args += ['-stream_loop', '-1', '-ss', str(offset), '-i', music]
            fade = min(.4, duration/2)
            filters += [f'[{inputs}:a:0]{audio_filter(s.get(side+"_music_volume",.3),duration)},afade=t=in:d={fade},afade=t=out:st={duration-fade}:d={fade}[music]', '[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[a]']
        else:
            filters.append('[voice]alimiter=limit=0.95:latency=1[a]')
        tail = ['-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',str(duration),'-video_track_timescale','15360','-movflags','+faststart',temp]
        try:
            self.encode(args+['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]'],tail,s)
            self.validate(temp, duration, s)
            os.replace(temp,result)
        finally:
            temp.unlink(missing_ok=True)
        return result, duration

    def validate(self, path, expected, s):
        info = probe(Path(path), self.runner)
        w,h = map(int,s['resolution'].split('x'))
        if not info['video'] or not info['audio'] or (info['width'],info['height']) != (w,h) or abs(info['duration']-expected) > .15:
            raise ValueError('输出完整性检查失败（音轨、尺寸或时长不符）。')
        return info

    def render_pair(self, intro, main, s, output, custom=None, progress=None):
        output = Path(output).resolve()
        output.parent.mkdir(parents=True,exist_ok=True)
        a, da = self.prepare(intro,s,'a',custom)
        b, db = self.prepare(main,s,'b')
        d = 0 if s['transition']=='cut' else min(round(s['transition_duration']*s['fps'])/s['fps'], da-1/s['fps'], db-1/s['fps'])
        if d < 1/s['fps']:
            d = 0
        expected = da+db-d
        temp = output.with_name(output.stem+'.'+uuid.uuid4().hex[:8]+'.partial.mp4')
        common = ['-i',a,'-i',b]
        try:
            if not d:
                # Keep video bitstream; join decoded audio on exact source duration to
                # avoid accumulating AAC priming gaps at the boundary.
                listing = self.cache/(uuid.uuid4().hex+'.concat.txt')
                listing.write_text(f"file '{a.name}'\nduration {da:.9f}\nfile '{b.name}'\nduration {db:.9f}\n",encoding='utf-8')
                try:
                    self.runner.ffmpeg(['-f','concat','-safe','0','-i',listing,'-i',a,'-i',b,
                        '-filter_complex',f'[1:a]{audio_filter(1,da)}[a0];[2:a]{audio_filter(1,db)}[a1];[a0][a1]concat=n=2:v=0:a=1[au]',
                        '-map','0:v:0','-map','[au]','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(expected),'-movflags','+faststart','-progress','pipe:1',temp],cwd=self.cache,duration=expected,progress=progress)
                finally:
                    listing.unlink(missing_ok=True)
            else:
                f = [f'[0:v]settb=AVTB,setpts=PTS-STARTPTS[v0]',f'[1:v]settb=AVTB,setpts=PTS-STARTPTS[v1]',
                     f'[v0][v1]xfade=transition={s["transition"]}:duration={d:.6f}:offset={da-d:.6f},format=yuv420p[v]',
                     f'[0:a]{audio_filter(1,da)}[a0]',f'[1:a]{audio_filter(1,db)}[a1]']
                if s['audio_transition']=='crossfade':
                    f += [f'[a0][a1]acrossfade=d={d}:c1=tri:c2=tri[au]']
                else:
                    f += [f'[a0]atrim=end={da-d/2}[ac0]',f'[a1]atrim=start={d/2},asetpts=PTS-STARTPTS[ac1]','[ac0][ac1]concat=n=2:v=0:a=1[au]']
                self.encode(common+['-filter_complex',';'.join(f),'-map','[v]','-map','[au]'],
                    ['-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t',str(expected),'-movflags','+faststart','-progress','pipe:1',temp],s,progress,expected)
            self.validate(temp,expected,s)
            os.replace(temp,output)
            if progress:
                progress(100)
            return output
        finally:
            temp.unlink(missing_ok=True)
