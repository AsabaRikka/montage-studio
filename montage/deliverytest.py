"""Delivery evidence on generated fixtures, including native GUI and recovery."""
from pathlib import Path
import json
import os
import shutil
import threading
import time
import uuid
from .runtime import write_json, asset, data_dir
from .core import Runner, probe, preview_frame, Cancelled
from .media import MediaEngine
from .service import scan, SETTINGS, run_batch
from .store import Store
from .planner import make_plan


def extras(folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    checks=[]
    def check(name,func):
        t=time.monotonic()
        try:checks.append(dict(name=name,passed=True,seconds=round(time.monotonic()-t,2),result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)[-3000:]))
        checks[-1]['seconds']=round(time.monotonic()-t,2)
        write_json(folder/'扩展报告.json',dict(passed=all(x['passed'] for x in checks),checks=checks))
    demo=folder/'演示素材'
    a=demo/'01_中文口播前贴.mp4';b=demo/'02_主视频.mp4';music=demo/'03_前贴音乐.wav'
    def speech():
        eng=MediaEngine(data=folder/'speech_runtime')
        try:
            rows=eng.ensure_subtitles(a,dict(SETTINGS,language='zh'))
            assert rows and len(''.join(r['text'] for r in rows))>=8,rows
            write_json(folder/'识别字幕.json',rows)
            eng.runner.ffmpeg(['-i',a,'-i',music,'-filter_complex','[0:a]volume=1[v];[1:a]volume=0.35[m];[v][m]amix=inputs=2:duration=first:normalize=0[au]','-map','0:v','-map','[au]','-c:v','copy','-c:a','aac',folder/'口播与旧音乐.mp4'])
            voice=eng.separated(folder/'口播与旧音乐.mp4')
            from scipy.io import wavfile
            import numpy as np
            rate,values=wavfile.read(voice)
            assert rate==44100 and np.isfinite(values).all() and float(np.std(values))>.001
            assert abs(len(values)/rate-probe(a)['duration'])<.1
            stamp=voice.stat().st_mtime_ns
            assert eng.separated(folder/'口播与旧音乐.mp4').stat().st_mtime_ns==stamp
            shutil.copy2(voice,folder/'分离后口播_需试听.wav')
            s=dict(SETTINGS,subtitles=True,a_sound='separate',a_music=str(music),encoder='nvidia')
            out=eng.render_pair(folder/'口播与旧音乐.mp4',b,s,folder/'中文720p示例.mp4')
            eng.runner.ffmpeg(['-i',out,'-f','null','-'])
            preview_frame(out,s,1,folder/'成片首段.png')
            preview_frame(out,s,probe(a)['duration']+.3,folder/'成片主视频段.png')
            return dict(rows=rows,duration=probe(out)['duration'],output=str(out),separation_peak=float(np.max(np.abs(values))),quality='需对真实素材试听，不保证无损保留口播或音效')
        finally:eng.close()
    check('中文口播离线识别与音乐分离720p成片',speech)
    def recovery():
        from .selftest import fixtures
        aa,bb,cc,_=fixtures(folder/("中文 路径 O'Brien_"+uuid.uuid4().hex[:8]))
        assets=scan([aa,bb,cc],'a')['assets'];am={x['id']:x for x in assets};keys=[x['id'] for x in assets]
        st=Store(folder/('recovery_db_'+uuid.uuid4().hex[:8]));s=dict(SETTINGS,resolution='360x640',output=str(folder/'故障恢复'))
        pairs=[(keys[0],keys[1]),(keys[0],keys[2])];bid=st.create('故障测试',am,pairs,s,[s,s])
        original=bb.read_bytes();bb.write_bytes(b'corrupted media')
        r=run_batch(bid,folder=st.folder)
        assert r['counts']=={'failed':1,'complete':1},r
        completed=Path(st.jobs(bid)[1]['output']);stamp=completed.stat().st_mtime_ns
        bb.write_bytes(original)
        moved=bb.with_name("移走的 O'Brien.mp4");bb.rename(moved);st.relocate(bid,keys[1],moved)
        r=run_batch(bid,folder=st.folder,retry=True)
        assert r['counts']=={'complete':2} and completed.stat().st_mtime_ns==stamp
        with_cancel=st.create('暂停测试',am,[(keys[0],keys[2])],s,[s]);stop=threading.Event()
        def notify(e):
            if e['type']=='job' and e['status']=='running':stop.set()
        cancel=run_batch(with_cancel,stop,notify,st.folder)
        assert cancel['counts']=={'pending':1} and cancel['paused']
        assert not st.history('暂停测试')
        st.abandon(with_cancel);assert not st.excluded('暂停测试')
        st.backup(folder/"历史 O'Brien.sqlite3");st.restore(folder/"历史 O'Brien.sqlite3")
        assert len(st.history())==2
        st.close();return dict(retry=r,cancel=cancel,corrupt_isolation=True,rename_identity=True,backup_restore=True)
    check('坏文件隔离_重试_活动暂停_重定位_备份',recovery)
    check('原生界面端到端',lambda:gui(folder/'gui'))
    result=dict(passed=all(x['passed'] for x in checks),checks=checks)
    write_json(folder/'扩展报告.json',result);return 0 if result['passed'] else 1


def gui(folder):
    import faulthandler
    trace = open(Path(folder).parent/'gui_trace.log','w')
    faulthandler.dump_traceback_later(35, repeat=True, file=trace)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtMultimedia import QMediaPlayer
    from .gui import MainWindow,STYLE,set_combo,SubtitleDialog,Player
    from .selftest import fixtures
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=MainWindow();window.notify_error=lambda exc:errors.append(str(exc));errors=[];window.show()
    a,b,silent,music=fixtures(folder/'input')
    def wait_until(condition,timeout=90):
        deadline=time.monotonic()+timeout
        while not condition():
            if time.monotonic()>deadline:raise TimeoutError('GUI操作未按时完成')
            app.processEvents();QTest.qWait(30)
        app.processEvents()
    try:
        window.assets={'a':[],'b':[],'music':[]};window.overrides={};window.refresh_assets()
        for role,paths in [('a',[a]),('b',[b,silent]),('music',[music])]:
            window.import_paths(role,[str(x) for x in paths]);wait_until(lambda:not window.busy())
        assert [len(window.assets[x]) for x in ('a','b','music')]==[1,2,1],errors
        window.game.setText('原生界面测试_'+uuid.uuid4().hex[:6]);window.output.setText(str(folder/'output'))
        set_combo(window.resolution,'360x640');set_combo(window.a_sound.mode,'one');set_combo(window.a_sound.music,str(music.resolve()))
        window.subtitles.setChecked(True)
        window.overrides[window.assets['a'][0]['id']]={'subtitle_rows':[dict(start=.1,end=1.8,text='中文字幕校正与批量导出测试')]}
        window.instruction.setText('生成2条，均匀分配，不重复配对');window.parse_text();window.generate_plan()
        assert len(window.plan)==2 and not errors,errors
        original_count=window.quantity.value();window.quantity.setValue(1)
        try:window.check_current_plan()
        except ValueError:pass
        else:raise AssertionError('修改后仍允许旧计划执行')
        window.quantity.setValue(original_count)
        for i in range(5):
            window.tabs.setCurrentIndex(i);QTest.qWait(150);window.grab().save(str(folder/f'界面_{i+1}.png'))
        sub=SubtitleDialog(window.assets['a'][0],window.settings(),window.overrides[window.assets['a'][0]['id']]['subtitle_rows'],window);sub.show()
        sub.frame.time.setValue(.5);sub.preview();wait_until(lambda:sub.frame.last_result is not None)
        assert not sub.frame.canvas.pixmap.isNull(),sub.frame.last_result
        sub.grab().save(str(folder/'字幕校正预览.png'));sub.done(0)
        window.create_batch();assert window.bid and not errors,errors
        window.start_batch();wait_until(lambda:not window.busy())
        jobs=window.store.jobs(window.bid);assert all(x['status']=='complete' for x in jobs),jobs
        assert window.total_progress.value()==2
        window.grab().save(str(folder/'导出完成.png'))
        player=Player(jobs[0]['output'],window);frames=[]
        player.video.videoSink().videoFrameChanged.connect(lambda frame:frames.append(frame.toImage()) if frame.isValid() else None)
        player.show()
        wait_until(lambda:player.player.position()>650 and frames and not frames[-1].isNull(),timeout=15)
        frames[-1].save(str(folder/'播放器实际视频帧.png'))
        pos=player.player.position();duration=player.player.duration();player.grab().save(str(folder/'成片播放.png'))
        assert player.player.hasVideo() and player.player.error()==QMediaPlayer.Error.NoError
        print('GUI: closing player',flush=True);player.done(0)
        print('GUI: closing window',flush=True);bid=window.bid;window.close();QTest.qWait(100)
        print('GUI: reopening',flush=True)
        reopened=MainWindow();reopened.show();assert len(reopened.assets['a'])==1
        set_combo(reopened.batch_combo,bid);reopened.load_batch();assert reopened.total_progress.value()==2
        reopened.close()
        return dict(imports=[1,2,1],completed=2,subtitle_frame=True,playback_ms=pos,playback_duration_ms=duration,session_reopen=True,errors=errors)
    finally:
        faulthandler.cancel_dump_traceback_later();trace.close()
        if window.isVisible():window.close()


def stress(folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);r=Runner();t=time.monotonic()
    base=folder/'tiny.mp4'
    r.ffmpeg(['-f','lavfi','-i','testsrc2=s=64x112:r=30','-f','lavfi','-i','sine=frequency=400:sample_rate=48000','-t','0.2','-c:v','libx264','-threads','2','-c:a','aac',base])
    paths=[]
    for role,count in [('a',20),('b',500)]:
        dest=folder/role;dest.mkdir(exist_ok=True);files=[]
        for n in range(count):
            p=dest/f'{role}{n:03}.mp4'
            r.ffmpeg(['-i',base,'-c','copy','-metadata',f'comment=synthetic-{role}-{n}',p]);files.append(p)
        paths.append(scan(files,role)['assets'])
    aa,bb=paths;am={x['id']:x for x in aa+bb}
    pairs=make_plan([x['id'] for x in aa],[x['id'] for x in bb],1000,seed=321)
    s=dict(SETTINGS,resolution='64x112',output=str(folder/'output'))
    st=Store(folder/'db');bid=st.create('1000短片压力测试',am,pairs,s,[s]*1000)
    stop=threading.Event()
    def notify(e):
        if e['type']=='job' and e['status']=='complete' and e['number']==317:stop.set()
    first=run_batch(bid,stop,notify,st.folder)
    assert first['counts']=={'complete':317,'pending':683},first
    st.close();st=Store(folder/'db');second=run_batch(bid,folder=st.folder)
    assert second['counts']=={'complete':1000},second
    files=list((folder/'output').rglob('*.mp4'));assert len(files)==1000 and len(st.history())==1000
    # Decode outputs spread across the batch; every output was probed during render.
    for i in range(0,1000,100):r.ffmpeg(['-i',st.jobs(bid)[i]['output'],'-f','null','-'])
    report=dict(passed=True,inputs=[20,500],outputs=1000,first=first,second=second,seconds=round(time.monotonic()-t,2),history=1000,decode_samples=10,scope='0.2秒合成短素材/64x112；测试任务可靠性，不代表90秒720p实际吞吐')
    write_json(folder/'1000条报告.json',report);st.close();return 0
