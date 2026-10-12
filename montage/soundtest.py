"""Native unsaved sound audition acceptance, using synthetic media only."""
import copy
import hashlib
import sys
import time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from PySide6.QtMultimedia import QMediaPlayer
from .core import Runner
from .runtime import data_dir, write_json
from .service import SETTINGS, scan
from .theme import apply


def verify(folder):
    from .gui import IntroSoundDialog, MainWindow, set_combo
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    runner=Runner();source=folder/'6秒原声440Hz.mp4';second=folder/'6秒另一前贴.mp4'
    music=folder/'音乐880然后1320Hz.wav';voice=folder/'独立声音660Hz.wav'
    runner.ffmpeg(['-f','lavfi','-i','testsrc2=s=360x640:r=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
        '-t','6','-c:v','libx264','-threads','2','-c:a','aac',source])
    runner.ffmpeg(['-i',source,'-vf','hue=h=120','-c:v','libx264','-threads','2','-c:a','copy',second])
    runner.ffmpeg(['-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=2',
        '-f','lavfi','-i','sine=frequency=1320:sample_rate=48000:duration=6',
        '-filter_complex','[0:a][1:a]concat=n=2:v=0:a=1[a]','-map','[a]',music])
    runner.ffmpeg(['-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=6',voice])
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,second,music,voice)}
    assets=scan([source,second],'a')['assets'];musics=scan([music,voice],'music')['assets']
    settings=dict(SETTINGS,resolution='360x640');app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');apply(app)
    dialog=IntroSoundDialog(assets,settings,{},musics,2);dialog.show();checks=[];outputs={}
    def wait(condition):
        deadline=time.monotonic()+90
        while not condition():
            if time.monotonic()>deadline:raise TimeoutError(dialog.status.text())
            QTest.qWait(25)
    def close_player(d=dialog):
        if d.preview_player is not None:
            d.preview_player.done(0);d.preview_player=None;app.processEvents()
    def render(label,d=dialog):
        close_player(d);QTest.mouseClick(d.preview_button,Qt.MouseButton.LeftButton)
        wait(lambda:d.worker is None)
        assert d.last_result and 'value' in d.last_result,d.status.text()
        path=Path(d.last_result['value']['path']);outputs[label]=str(path)
        runner.ffmpeg(['-i',path,'-f','null','-'])
        close_player(d);return path
    def spectrum(path):
        pcm=folder/'measure.f32';runner.ffmpeg(['-ss','0.8','-i',path,'-t','1','-vn','-ac','1','-ar','48000','-f','f32le',pcm])
        x=np.fromfile(pcm,dtype='<f4');freq=np.fft.rfftfreq(len(x),1/48000);amp=np.abs(np.fft.rfft(x*np.hanning(len(x))))/len(x)*4
        return {hz:float(amp[np.abs(freq-hz).argmin()]) for hz in (440,660,880,1320)}
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)))
        write_json(folder/'声音试听验证.json',dict(passed=len(checks)==6 and all(c['passed'] for c in checks),checks=checks,
            synthetic_media_only=True,data_directory=str(data_dir()),manual_listening=False,outputs=outputs,
            exe_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() if getattr(sys,'frozen',False) else None))
    try:
        def playback():
            set_combo(dialog.controls.mode,'one');set_combo(dialog.controls.music,str(music));dialog.controls.volume.setValue(.5)
            dialog.controls.music_volume.setValue(.8);dialog.controls.offset.setValue(2)
            dialog.grab().save(str(folder/'声音设置浅色.png'))
            QTest.mouseClick(dialog.preview_button,Qt.MouseButton.LeftButton);wait(lambda:dialog.worker is None)
            assert 'value' in dialog.last_result,dialog.last_result
            p=dialog.preview_player;frames=[];p.video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.toImage()) if f.isValid() else None)
            wait(lambda:p.player.position()>500 and p.timeline.isEnabled() and frames)
            assert p.player.hasAudio() and p.player.hasVideo() and p.audio.device().isNull() is False
            frames[-1].save(str(folder/'试听实际解码帧.png'));position=p.player.position();p.player.pause()
            QTest.mouseClick(p.timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(p.timeline.width()*.65),p.timeline.height()//2))
            wait(lambda:3700<p.player.position()<4200);assert not p.player.isPlaying()
            p.player.play();QTest.mousePress(p.timeline,Qt.MouseButton.LeftButton,pos=QPoint(p.timeline.width()//2,12))
            QTest.mouseMove(p.timeline,QPoint(p.timeline.width()//4,12));QTest.mouseRelease(p.timeline,Qt.MouseButton.LeftButton,pos=QPoint(p.timeline.width()//4,12))
            wait(lambda:p.player.isPlaying() and 1300<p.player.position()<2100)
            assert p.player.error()==QMediaPlayer.Error.NoError
            p.grab().save(str(folder/'试听进度条.png'));path=Path(dialog.last_result['value']['path']);outputs['mix']=str(path);close_player()
            amp=spectrum(path);assert .045<amp[440]<.08 and .08<amp[1320]<.13 and amp[880]<.002,amp
            return dict(decoded_ms=position,has_audio=True,audio_device=True,paused_click=True,playing_drag=True,mix_spectrum=amp)
        check('未保存设置_真实影音解码_可拖播放_混音起点',playback)
        def modes():
            set_combo(dialog.controls.mode,'none');dialog.controls.volume.setValue(1);set_combo(dialog.controls.sound,'original')
            original=spectrum(render('original'));assert .10<original[440]<.14
            dialog.controls.volume.setValue(.25);quiet=spectrum(render('quiet'));assert .22<quiet[440]/original[440]<.28
            set_combo(dialog.controls.sound,'mute');muted=spectrum(render('mute'));assert max(muted.values())<.0001
            set_combo(dialog.controls.mode,'one');dialog.controls.music_volume.setValue(.5);dialog.controls.offset.setValue(0)
            bgm=spectrum(render('music_only'));assert bgm[880]>.045 and bgm[440]<.001 and bgm[1320]<.002
            set_combo(dialog.controls.sound,'external');dialog.controls.voice.setText(str(voice));set_combo(dialog.controls.mode,'none');dialog.controls.volume.setValue(1)
            external=spectrum(render('external'));assert external[660]>.10 and external[440]<.002
            set_combo(dialog.controls.sound,'separate');render('separate')
            return dict(original=original,quarter_gain=quiet,mute=muted,bgm_only=bgm,external=external,separation_processed=True,separation_quality_not_asserted=True)
        check('原声_音量_静音_BGM_独立声音_去旧音乐',modes)
        def random_and_bulk():
            set_combo(dialog.controls.sound,'original');set_combo(dialog.controls.mode,'random_job')
            render('random');assert dialog.last_settings['a_music'] in [m['path'] for m in musics]
            first=dialog.last_settings['a_music'];render('random_repeat');assert dialog.last_settings['a_music']==first
            set_combo(dialog.controls.mode,'random_a');render('random_a')
            dialog.inherit.setChecked(True);assert not dialog.controls.isEnabled()
            render('inherit');assert dialog.last_settings['a_music']=='' and dialog.last_settings['a_volume']==1
            dialog.inherit.setChecked(False);dialog.apply_sound.setChecked(False);dialog.source.setCurrentIndex(1)
            render('bulk_second');assert dialog.last_result['value']['name']==assets[1]['name'] and dialog.last_settings['a_volume']==1
            return dict(random_example_named=first,repeatable=True,random_a=True,inherit_uses_batch=True,unchecked_preserves_selected_source=True,second_intro=True)
        check('随机示例_继承整批_多选试听对象',random_and_bulk)
        def errors():
            dialog.apply_sound.setChecked(True);set_combo(dialog.controls.sound,'original');set_combo(dialog.controls.mode,'one');set_combo(dialog.controls.music,'')
            dialog.preview();assert dialog.worker is None and '选择一首' in dialog.status.text()
            set_combo(dialog.controls.music,str(music));dialog.controls.offset.setValue(999)
            dialog.preview();wait(lambda:dialog.worker is None);assert 'error' in dialog.last_result and '起点' in dialog.status.text()
            set_combo(dialog.controls.mode,'none');set_combo(dialog.controls.sound,'external');dialog.controls.voice.setText(str(folder/'不存在.wav'))
            dialog.preview();wait(lambda:dialog.worker is None);assert 'error' in dialog.last_result
            set_combo(dialog.controls.sound,'original');dialog.controls.offset.setValue(0);render('recovered')
            empty=IntroSoundDialog(assets,settings,{},[],2);set_combo(empty.controls.mode,'random_job');empty.preview()
            assert empty.worker is None and '音乐库' in empty.status.text();empty.done(0)
            return dict(missing_selection=True,invalid_offset=True,missing_external=True,empty_random_library=True,recovered=True)
        check('错误提示_恢复试听',errors)
        def cancellation():
            dialog.settings['resolution']='720x1280';dialog.settings['crf']=23
            dialog.preview();assert dialog.worker is not None;QTest.mouseClick(dialog.cancel_preview,Qt.MouseButton.LeftButton)
            wait(lambda:dialog.worker is None);assert dialog.last_result.get('cancelled') and dialog.preview_button.isEnabled()
            dialog.preview();assert dialog.worker is not None;dialog.done(0);QTest.qWait(100)
            assert dialog.worker is None and not dialog.isVisible()
            assert not list((data_dir()/'cache').glob('*.partial.*'))
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
            return dict(stop_button=True,close_stops=True,no_partial_files=True,source_hashes_unchanged=True)
        check('停止生成_关窗取消_源文件保护',cancellation)
        def persistence():
            window=MainWindow();window.show();window.assets={'a':assets,'b':[assets[1]],'music':musics}
            window.overrides={a['id']:dict(fixed=i,a_volume=.2+i*.1,subtitle_rows=[dict(start=0,end=1,text='保留字幕')]) for i,a in enumerate(assets)}
            window.refresh_assets();window.lists['a'].selectAll();window.save_session()
            before=copy.deepcopy(window.overrides);session=(data_dir()/'session.json').read_bytes()
            history=window.store.db.iterdump();db_before=list(history)
            failures=[]
            def cancel_dialog():
                try:
                    d=app.activeModalWidget();assert isinstance(d,IntroSoundDialog);d.controls.volume.setValue(.88)
                    render('window_unsaved',d);apply(app,True);d.grab().save(str(folder/'声音设置深色.png'));apply(app)
                    d.reject()
                except Exception as exc:
                    failures.append(str(exc));app.activeModalWidget().reject()
            QTimer.singleShot(150,cancel_dialog);window.edit_intro();assert not failures,failures
            assert window.overrides==before and (data_dir()/'session.json').read_bytes()==session
            assert list(window.store.db.iterdump())==db_before
            def save_dialog():
                d=app.activeModalWidget();d.controls.volume.setValue(.75);d.apply_fixed.setChecked(False)
                QTest.mouseClick(d.bb.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
            QTimer.singleShot(150,save_dialog);window.edit_intro()
            assert all(window.overrides[a['id']]['a_volume']==.75 and window.overrides[a['id']]['fixed']==i and window.overrides[a['id']]['subtitle_rows']==before[a['id']]['subtitle_rows'] for i,a in enumerate(assets))
            assert list(window.store.db.iterdump())==db_before
            window.close();reopened=MainWindow()
            assert all(reopened.overrides[a['id']]['a_volume']==.75 for a in assets);reopened.close()
            return dict(cancel_preserves_session=True,no_history_jobs_or_reservations=True,save_persists=True,fixed_and_subtitles_preserved=True,reopen=True)
        check('实际入口_取消不保存_批量保存_重开_不占历史',persistence)
    finally:
        if not dialog.closing:dialog.done(0)
        app.processEvents()
    return 0 if len(checks)==6 and all(c['passed'] for c in checks) else 1
