"""Packaged diagnostics; generated media only, no company material or uploads."""
from pathlib import Path
import json
import os
import threading
import time
from .core import Runner, probe, Cancelled
from .runtime import asset, write_json, data_dir
from .media import MediaEngine
from .service import SETTINGS, scan, run_batch
from .store import Store
from .planner import make_plan


def fixtures(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    r=Runner()
    paths=[]
    for name,source,freq in [('前贴 A 的测试.mp4','testsrc2',440),('主视频 B.mp4','testsrc2',660),('无声 片段.mp4','color=c=0x154c55',0)]:
        p=folder/name
        args=['-f','lavfi','-i',source+':s=360x640:r=30' if source.startswith('color') else source+'=s=360x640:r=30']
        if freq:
            args+=['-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000']
        r.ffmpeg(args+['-t','2','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',p])
        paths.append(p)
    music=folder/'新音乐.wav'
    r.ffmpeg(['-f','lavfi','-i','sine=frequency=220:sample_rate=44100','-t','1','-c:a','pcm_s16le',music])
    return *paths,music


def verify(folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    checks=[];start=time.monotonic()
    a,b,silent,music=fixtures(folder/'素材 带空格')
    eng=MediaEngine(data=folder/'runtime')
    base=dict(SETTINGS,resolution='360x640',subtitles=True,subtitle_rows=[dict(start=.1,end=1.8,text='这是字幕测试，保留主视频原声')],a_music=str(music))
    def check(name,func):
        try:
            value=func();checks.append(dict(name=name,passed=True,result=value))
        except Exception as exc:
            checks.append(dict(name=name,passed=False,error=str(exc)[-2000:]))
    def render(name,transition='cut',main=b,encoder='cpu',audio_transition='crossfade'):
        s=dict(base,transition=transition,encoder=encoder,audio_transition=audio_transition)
        out=folder/(name+'.mp4');eng.render_pair(a,main,s,out)
        info=probe(out)
        # A decode pass detects broken bitstreams, not just readable metadata.
        eng.runner.ffmpeg(['-i',out,'-f','null','-'])
        return dict(duration=info['duration'],width=info['width'],height=info['height'],file=str(out))
    check('硬切字幕音乐',lambda:render('硬切'))
    check('无声主视频',lambda:render('无声输出',main=silent))
    for transition in ('fade','dissolve','wipeleft','slideleft'):
        check(transition,lambda t=transition:render(t,t))
    check('转场声音硬切',lambda:render('声音硬切','fade',audio_transition='cut'))
    check('NVIDIA编码或自动CPU回退',lambda:render('硬件编码','cut',encoder='nvidia'))
    def invalid_offset():
        try:eng.prepare(a,dict(base,a_music_start=5),'a')
        except ValueError:return '正确拒绝'
        raise AssertionError('无效音乐起点未被拒绝')
    check('音乐起点检查',invalid_offset)
    eng.close()
    def batch_recovery():
        assets=scan([a,b,silent],'a')['assets'];am={x['id']:x for x in assets}
        keys=[x['id'] for x in assets];pairs=[(keys[0],keys[1]),(keys[0],keys[2])]
        store=Store(folder/'queue');s=dict(SETTINGS,resolution='360x640',output=str(folder/'批量'))
        bid=store.create('测试游戏',am,pairs,s,[s,s])
        stop=threading.Event()
        def callback(event):
            if event['type']=='job' and event['status']=='complete':stop.set()
        first=run_batch(bid,stop,callback,folder/'queue')
        assert first['counts'].get('complete')==1 and first['counts'].get('pending')==1
        first_output=Path(store.jobs(bid)[0]['output']);mtime=first_output.stat().st_mtime_ns
        store.close();store=Store(folder/'queue')
        result=run_batch(bid,folder=folder/'queue')
        assert result['counts']=={'complete':2}
        assert first_output.stat().st_mtime_ns==mtime and len(store.history())==2
        try:make_plan([keys[0]],keys[1:],1,excluded=store.excluded('测试游戏'))
        except ValueError:pass
        else:raise AssertionError('未排除历史')
        store.backup(folder/'历史备份.sqlite3');store.close()
        return dict(first=first,second=result)
    check('暂停重启恢复和历史',batch_recovery)
    if (asset('models')/'small'/'model.bin').exists():
        def offline_asr():
            e=MediaEngine(data=folder/'asr')
            try:return e.ensure_subtitles(a,dict(SETTINGS,language='zh'))
            finally:e.close()
        check('离线字幕模型启动',offline_asr)
    result=dict(passed=all(c['passed'] for c in checks),seconds=round(time.monotonic()-start,2),checks=checks)
    write_json(folder/'自检报告.json',result)
    return 0 if result['passed'] else 1
