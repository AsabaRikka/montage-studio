"""Real Qt playback/seek acceptance on generated media, with isolated data."""
import hashlib
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from .runtime import write_json
from .core import Runner
from .theme import apply


def verify(folder):
    from .gui import Player
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    media=folder/'12秒合成视频.mp4'
    Runner().ffmpeg(['-f','lavfi','-i','testsrc2=s=360x640:r=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
        '-t','12','-c:v','libx264','-threads','2','-c:a','aac',media])
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');apply(app)
    player=Player(media);frames=[]
    player.video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.toImage()) if f.isValid() else None)
    player.show();checks=[]
    def wait(condition):
        deadline=time.monotonic()+20
        while not condition():
            if time.monotonic()>deadline:raise TimeoutError('播放验证超时')
            QTest.qWait(25)
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)))
    def point(fraction):
        return QPoint(round(player.timeline.width()*fraction),player.timeline.height()//2)
    try:
        def tracking():
            wait(lambda:player.player.position()>600 and player.timeline.isEnabled() and frames)
            assert player.timeline.maximum()==player.player.duration()
            assert abs(player.timeline.value()-player.player.position())<200
            assert player.time_label.text().endswith('/ 00:12')
            assert not frames[-1].isNull();frames[-1].save(str(folder/'实际解码帧.png'))
            return dict(duration=player.player.duration(),position=player.player.position(),decoded=True)
        check('播放跟随_总时长_真实解码',tracking)
        def paused_click():
            QTest.mouseClick(player.play_button,Qt.MouseButton.LeftButton)
            assert player.player.playbackState()==QMediaPlayer.PlaybackState.PausedState
            QTest.mouseClick(player.timeline,Qt.MouseButton.LeftButton,pos=point(.65))
            wait(lambda:abs(player.player.position()-7800)<350)
            QTest.qWait(300);assert not player.player.isPlaying()
            player.grab().save(str(folder/'浅色进度条.png'))
            return dict(click_seek_ms=player.player.position(),paused_preserved=True)
        check('暂停后点击跳转保持暂停',paused_click)
        def drag():
            QTest.mouseClick(player.play_button,Qt.MouseButton.LeftButton)
            QTest.mousePress(player.timeline,Qt.MouseButton.LeftButton,pos=point(.6))
            assert not player.player.isPlaying() and player.timeline.isSliderDown()
            QTest.mouseMove(player.timeline,point(.25));target=player.timeline.value()
            QTest.qWait(250);assert player.timeline.value()==target
            QTest.mouseRelease(player.timeline,Qt.MouseButton.LeftButton,pos=point(.25))
            wait(lambda:player.player.isPlaying() and 2700<player.player.position()<3500)
            return dict(drag_seek_ms=player.player.position(),resume=True,drag_not_overwritten=True)
        check('播放中拖动_松手继续',drag)
        def keyboard_and_end():
            player.player.pause();player.timeline.setFocus();before=player.player.position()
            QTest.keyClick(player.timeline,Qt.Key.Key_Right)
            wait(lambda:abs(player.player.position()-(before+1000))<200)
            QTest.keyClick(player.timeline,Qt.Key.Key_Home);wait(lambda:player.player.position()==0)
            assert not player.player.isPlaying()
            player.player.setPosition(11700);player.player.play()
            wait(lambda:player.player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia)
            QTest.mouseClick(player.play_button,Qt.MouseButton.LeftButton)
            wait(lambda:player.player.isPlaying() and 100<player.player.position()<1000)
            assert Player.clock(3661000)=='01:01:01' and Player.clock(0)=='00:00'
            return dict(keyboard_seek=True,end_replay=True,long_time_format=True)
        check('键盘跳转_播完重播_时间格式',keyboard_and_end)
        def dark():
            apply(app,True);player.player.pause();QTest.qWait(120)
            player.grab().save(str(folder/'深色进度条.png'))
            assert player.player.error()==QMediaPlayer.Error.NoError
            player.done(0);assert player.player.playbackState()==QMediaPlayer.PlaybackState.StoppedState
            return dict(dark=True,close_stops=True,no_playback_error=True)
        check('深色界面_关闭停止',dark)
    finally:
        player.done(0);app.processEvents()
    report=dict(passed=len(checks)==5 and all(c['passed'] for c in checks),checks=checks,synthetic_media_only=True,
        exe_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() if getattr(sys,'frozen',False) else None)
    write_json(folder/'播放器验证.json',report)
    return 0 if report['passed'] else 1
