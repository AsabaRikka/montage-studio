"""Source-region repair and exact subtitle frame previews."""
import copy
import threading
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QRectF, QUrl
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QDialog, QDialogButtonBox, QCheckBox, QFormLayout, QTabWidget)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from .core import Runner, Cancelled, preview_frame
from .runtime import data_dir


class FrameWorker(QThread):
    ready = Signal(object)

    def __init__(self, path, settings, seconds, segments, source_size, parent):
        super().__init__(parent)
        self.args = (path, copy.deepcopy(settings), seconds)
        self.segments = copy.deepcopy(segments)
        self.source_size = source_size
        self.stop = threading.Event()
        self.output = data_dir() / 'frame_previews' / (uuid.uuid4().hex + '.png')

    def run(self):
        try:
            info = preview_frame(*self.args, self.output, self.segments, self.source_size, Runner(self.stop))
            self.ready.emit({'path': str(self.output), 'duration': info['duration']})
        except Cancelled:
            pass
        except Exception as exc:
            self.ready.emit({'error': str(exc)})


class FrameCanvas(QWidget):
    selected = Signal(object)

    def __init__(self, selectable=False):
        super().__init__()
        self.setMinimumSize(260, 240)
        self.pixmap = QPixmap()
        self.selectable = selectable
        self.region = None
        self.origin = None

    def image_rect(self):
        if self.pixmap.isNull():
            return QRectF()
        size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#14213b'))
        rect = self.image_rect()
        if not rect.isEmpty():
            painter.drawPixmap(rect, self.pixmap, QRectF(self.pixmap.rect()))
            if self.selectable and self.region:
                r = self.region
                painter.setPen(QPen(QColor('#ff673d'), 2))
                painter.drawRect(QRectF(rect.x()+r['x']*rect.width(), rect.y()+r['y']*rect.height(), r['w']*rect.width(), r['h']*rect.height()))

    def mousePressEvent(self, event):
        if self.selectable and event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self.origin = event.position()

    def mouseMoveEvent(self, event):
        if self.origin is None:
            return
        rect = self.image_rect()
        point = event.position()
        x1, x2 = sorted([self.origin.x(), min(rect.right(), max(rect.left(), point.x()))])
        y1, y2 = sorted([self.origin.y(), min(rect.bottom(), max(rect.top(), point.y()))])
        self.region = dict(x=(x1-rect.x())/rect.width(), y=(y1-rect.y())/rect.height(), w=(x2-x1)/rect.width(), h=(y2-y1)/rect.height())
        self.update()

    def mouseReleaseEvent(self, event):
        if self.origin is not None:
            self.mouseMoveEvent(event)
            self.origin = None
            if self.region and min(self.region['w'], self.region['h']) > .001:
                self.selected.emit(self.region.copy())


class FramePreview(QWidget):
    def __init__(self, path, settings, parent=None, selectable=False):
        super().__init__(parent)
        self.path, self.settings = path, copy.deepcopy(settings)
        self.worker = None
        self.last_result = None
        self.request = None
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        self.canvas = FrameCanvas(selectable)
        box.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel('时间'))
        self.time = QDoubleSpinBox()
        self.time.setRange(0, 86400)
        self.time.setDecimals(2)
        self.time.setSingleStep(.1)
        self.time.setSuffix(' 秒')
        row.addWidget(self.time)
        self.refresh = QPushButton('刷新效果预览')
        row.addWidget(self.refresh)
        box.addLayout(row)
        self.status = QLabel('修改后点击刷新，查看当前时间的实际处理效果。')
        self.status.setWordWrap(True)
        box.addWidget(self.status)

    def render(self, settings=None, segments=None, source_size=False):
        if self.worker and self.worker.isRunning():
            return
        self.status.setText('正在生成预览…')
        self.refresh.setEnabled(False)
        self.worker = FrameWorker(self.path, settings or self.settings, self.time.value(), segments, source_size, self)
        self.worker.ready.connect(self.ready)
        self.worker.start()

    def ready(self, result):
        self.worker.wait()
        self.last_result = result
        self.refresh.setEnabled(True)
        if 'error' in result:
            self.status.setText('预览失败：' + result['error'][-500:])
            return
        self.canvas.pixmap = QPixmap(result['path'])
        Path(result['path']).unlink(missing_ok=True)
        self.canvas.update()
        self.time.setMaximum(max(0, result['duration']-.05))
        self.status.setText('当前帧预览已更新。修改后请再次刷新。')

    def stop(self):
        if self.worker:
            self.worker.stop.set()
            self.worker.wait()
            self.worker.output.unlink(missing_ok=True)


class SourcePlayer(QWidget):
    """Original clip playback for listening and locating subtitle timestamps."""
    def __init__(self, path, time_control):
        super().__init__()
        box = QVBoxLayout(self)
        self.video = QVideoWidget()
        self.video.setMinimumSize(260, 240)
        box.addWidget(self.video, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.positionChanged.connect(lambda ms: time_control.setValue(ms/1000))
        self.player.durationChanged.connect(lambda ms: time_control.setMaximum(max(0, ms/1000-.05)))
        row = QHBoxLayout()
        play = QPushButton('播放 / 暂停原片')
        play.clicked.connect(lambda: self.player.pause() if self.player.isPlaying() else self.player.play())
        seek = QPushButton('跳到预览时间')
        seek.clicked.connect(lambda: self.player.setPosition(round(time_control.value()*1000)))
        row.addWidget(play)
        row.addWidget(seek)
        box.addLayout(row)
        label = QLabel('原片用于听音和定位；修改后的字幕请在“烧录效果”页查看。')
        label.setWordWrap(True)
        box.addWidget(label)


class WatermarkDialog(QDialog):
    def __init__(self, path, settings, count=1, parent=None):
        super().__init__(parent)
        self.setWindowTitle('水印区域处理 · ' + Path(path).name)
        self.resize(800, 760)
        self.path = path
        self.settings = copy.deepcopy(settings)
        box = QVBoxLayout(self)
        tip = QLabel('在画面上拖拽框住水印（略大于水印边缘），或调整百分比。周边像素修补可能留下模糊痕迹，请预览不同时间点。')
        tip.setWordWrap(True)
        box.addWidget(tip)
        self.enabled = QCheckBox('对此素材启用水印修补')
        self.enabled.setChecked(True)
        box.addWidget(self.enabled)
        self.preview = FramePreview(path, settings, self, selectable=True)
        box.addWidget(self.preview, 1)
        form = QHBoxLayout()
        self.fields = {}
        for key, label in [('x','左边'), ('y','顶部'), ('w','宽度'), ('h','高度')]:
            form.addWidget(QLabel(label))
            control = QDoubleSpinBox()
            control.setRange(0 if key in ('x','y') else .1, 100)
            control.setDecimals(1)
            control.setSuffix('%')
            control.valueChanged.connect(self.update_region)
            self.fields[key] = control
            form.addWidget(control)
        box.addLayout(form)
        self.set_region(settings.get('watermarks', {}).get(path) or dict(x=.80, y=.93, w=.18, h=.055))
        self.preview.canvas.selected.connect(self.set_region)
        row = QHBoxLayout()
        original = QPushButton('查看原图')
        original.clicked.connect(self.original)
        row.addWidget(original)
        row.addStretch()
        box.addLayout(row)
        self.apply_all = QCheckBox(f'将此区域应用到选中的 {count} 个视频（按画面比例）')
        self.apply_all.setVisible(count > 1)
        box.addWidget(self.apply_all)
        self.error = QLabel('')
        box.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存设置')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.preview.refresh.clicked.connect(self.render)
        self.original()

    def set_region(self, region):
        for key, control in self.fields.items():
            control.blockSignals(True)
            control.setValue(region[key]*100)
            control.blockSignals(False)
        self.update_region()

    def region(self):
        return {key: control.value()/100 for key, control in self.fields.items()}

    def update_region(self):
        if len(self.fields) == 4:
            self.preview.canvas.region = self.region()
            self.preview.canvas.update()

    def options(self):
        settings = copy.deepcopy(self.settings)
        settings.setdefault('watermarks', {}).pop(self.path, None)
        if self.enabled.isChecked():
            settings['watermarks'][self.path] = self.region()
        return settings

    def original(self):
        settings = copy.deepcopy(self.settings)
        settings['watermarks'] = {}
        self.preview.render(settings, source_size=True)

    def render(self):
        self.preview.render(self.options(), source_size=True)

    def validate(self):
        r = self.region()
        if self.enabled.isChecked() and (r['x']+r['w'] > 1.00001 or r['y']+r['h'] > 1.00001):
            self.error.setText('区域超出画面，请缩小宽度或高度。')
            return
        self.accept()

    def done(self, result):
        self.preview.stop()
        super().done(result)
