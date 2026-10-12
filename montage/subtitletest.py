"""Real frame navigation and burned subtitle checks using isolated synthetic media."""
import hashlib
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from .core import Runner
from .runtime import write_json, data_dir
from .service import SETTINGS
from .theme import apply


def verify(folder):
    from .gui import SubtitleDialog
    from .editing import WatermarkDialog
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    media = folder/'6秒合成字幕定位.mp4'
    Runner().ffmpeg(['-f','lavfi','-i','color=c=0x15243b:s=360x640:r=30',
        '-t','6','-c:v','libx264','-threads','2',media])
    original_hash = hashlib.sha256(media.read_bytes()).hexdigest()
    app = QApplication.instance() or QApplication([]); app.setStyle('Fusion'); apply(app)
    settings = dict(SETTINGS, resolution='360x640')
    dialog = SubtitleDialog(dict(path=str(media),name=media.name,duration=6),settings,
        [dict(start=0,end=2,text='第一段字幕'),dict(start=2,end=5,text='第二段字幕')],None)
    frame = dialog.frame; checks = []; dialog.show()

    def wait(condition):
        deadline = time.monotonic()+20
        while not condition():
            if time.monotonic()>deadline:
                raise TimeoutError(frame.status.text())
            QTest.qWait(25)

    def rendered(seconds):
        wait(lambda:frame.worker is None and frame.last_result is not None)
        assert 'error' not in frame.last_result, frame.last_result
        assert abs(frame.last_result['seconds']-seconds)<.025, frame.last_result
        assert not frame.canvas.pixmap.isNull()
        return frame.canvas.pixmap.toImage()

    def point(seconds):
        slider = frame.timeline
        return QPoint(round(7+(slider.width()-14)*seconds/(slider.maximum()/1000)),slider.height()//2)

    def whites(image):
        return sum(image.pixelColor(x,y).lightness()>180
            for y in range(image.height()//2,image.height()) for x in range(image.width()))

    def check(name, func):
        try: checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc: checks.append(dict(name=name,passed=False,error=str(exc)))
        write_json(folder/'字幕进度条验证.json',dict(passed=len(checks)==6 and all(c['passed'] for c in checks),
            checks=checks,synthetic_media_only=True,data_directory=str(data_dir()),
            exe_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() if getattr(sys,'frozen',False) else None))

    try:
        def initial():
            assert frame.timeline.isEnabled() and frame.timeline.maximum()==5950
            image = rendered(0); image.save(str(folder/'第一段字幕实际帧.png'))
            assert whites(image)>100
            return dict(initial_frame=True,total_seconds=frame.duration,burned_caption_pixels=whites(image))
        check('打开即显示实际字幕帧与完整进度范围',initial)

        def click_drag():
            QTest.mouseClick(frame.timeline,Qt.MouseButton.LeftButton,pos=point(3))
            second = rendered(frame.time.value());second.save(str(folder/'第二段字幕实际帧.png'))
            assert whites(second)>100
            QTest.mousePress(frame.timeline,Qt.MouseButton.LeftButton,pos=point(3))
            QTest.mouseMove(frame.timeline,point(5.5))
            assert frame.timeline.isSliderDown() and abs(frame.time.value()-5.5)<.03
            assert frame.worker is None, '拖动中不应反复生成帧'
            QTest.mouseRelease(frame.timeline,Qt.MouseButton.LeftButton,pos=point(5.5))
            blank = rendered(frame.time.value());blank.save(str(folder/'字幕结束后实际帧.png'))
            assert whites(blank)==0
            return dict(click_caption=True,drag_release_blank=True,spin_slider_synced=True)
        check('真实点击与拖动松手按字幕时间刷新',click_drag)

        def precise_keyboard():
            frame.time.setValue(1.23);frame.time.setFocus();QTest.keyClick(frame.time,Qt.Key.Key_Return)
            rendered(1.23);assert frame.timeline.value()==1230
            assert dialog.isVisible() and not frame.closed
            frame.timeline.setFocus();QTest.keyClick(frame.timeline,Qt.Key.Key_Right);rendered(1.33)
            QTest.keyClick(frame.timeline,Qt.Key.Key_End);rendered(5.95)
            QTest.keyClick(frame.timeline,Qt.Key.Key_Home);rendered(0)
            return dict(precise_seconds=1.23,arrow_step=.1,end_clamped=True,home=True)
        check('精确输入与键盘首尾微调',precise_keyboard)

        def latest_edits():
            frame.time.setValue(.5);dialog.preview();first_worker=frame.worker
            dialog.rows_table.item(1,2).setText('已修改的新字幕')
            frame.time.setValue(3.25);dialog.preview()
            assert frame.worker is first_worker and frame.request is not None
            frame.time.setValue(3.75);dialog.preview()
            image=rendered(3.75);image.save(str(folder/'修改字幕后实际帧.png'))
            assert whites(image)>100
            assert image!=__import__('PySide6.QtGui',fromlist=['QImage']).QImage(str(folder/'第二段字幕实际帧.png'))
            dialog.grab().save(str(folder/'字幕进度条浅色.png'))
            return dict(latest_time=3.75,current_edited_caption=True,stale_frame_discarded=True)
        check('连续跳转最后位置生效且使用最新字幕',latest_edits)

        def watermark():
            repair=WatermarkDialog(str(media),settings)
            try:
                repair.show();wait(lambda:repair.preview.worker is None)
                assert repair.preview.timeline.isEnabled() and not repair.preview.canvas.pixmap.isNull()
                repair.set_region(dict(x=.7,y=.6,w=.2,h=.15))
                QTest.mouseClick(repair.preview.timeline,Qt.MouseButton.LeftButton,
                    pos=QPoint(repair.preview.timeline.width()//2,14))
                wait(lambda:repair.preview.worker is None)
                assert 'error' not in repair.preview.last_result,repair.preview.last_result
                assert 2.8<repair.preview.last_result['seconds']<3.1
                assert not repair.preview.canvas.pixmap.isNull()
                return dict(shared_watermark_timeline=True,repair_frame=True)
            finally:repair.done(0)
        check('共用水印预览进度条回归',watermark)

        def dark_close():
            apply(app,True);QTest.qWait(100);dialog.grab().save(str(folder/'字幕进度条深色.png'))
            frame.time.setValue(4);dialog.preview();worker=frame.worker
            dialog.done(0);app.processEvents()
            assert not worker.isRunning() and frame.closed and frame.request is None
            assert not worker.output.exists()
            assert hashlib.sha256(media.read_bytes()).hexdigest()==original_hash
            return dict(dark=True,close_cancels=True,temporary_frame_removed=True,source_unchanged=True)
        check('深色界面与关闭取消保留原片',dark_close)
    finally:
        dialog.done(0);app.processEvents()
    return 0 if len(checks)==6 and all(c['passed'] for c in checks) else 1
