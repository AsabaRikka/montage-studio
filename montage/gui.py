from __future__ import annotations
import copy
import json
import os
import random
import shutil
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QLockFile, QSize, QItemSelectionModel, QRectF
from PySide6.QtGui import QDesktopServices, QFont, QColor, QIcon, QPixmap, QPainter
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QTabWidget,QListWidget,QListWidgetItem,QFileDialog,QMessageBox,QLineEdit,
    QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QFormLayout,QGroupBox,QSplitter,
    QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QDialog,QDialogButtonBox,
    QProgressBar,QScrollArea,QAbstractItemView,QInputDialog,QColorDialog,QSlider,QStyle)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from .runtime import data_dir,write_json
from .service import SETTINGS,scan,run_batch,api_rules,job_output,write_report
from .store import Store,identity
from .planner import make_plan,parse_instruction,PlanError
from .workflow import available_count, cache_sizes, clear_processing_cache, human_size, MAX_BATCH
from .media import MediaEngine
from .core import Cancelled
from .subtitles import read_srt,write_srt,align_script
from .editing import FramePreview
from .widgets import SeekSlider, NoWheelComboBox as QComboBox, NoWheelSpinBox as QSpinBox, NoWheelDoubleSpinBox as QDoubleSpinBox
from .thumbnails import ThumbnailLoader
from . import __version__
from .runtime import asset
from .theme import stylesheet, apply as apply_theme, tokens, icon as ui_icon
from .gallery import MaterialGrid, NAME, DETAIL, EXTRA, KIND, ERROR


STYLE=stylesheet()


def button(text,callback,primary=False):
    b=QPushButton(text);b.clicked.connect(callback);b.setProperty('primary',primary);return b


def combo(values):
    w=QComboBox()
    for name,value in values:w.addItem(name,value)
    return w


def set_combo(widget,value):
    i=widget.findData(value)
    if i>=0:widget.setCurrentIndex(i)


def spin(lo,hi,value,decimals=None):
    w=QSpinBox() if decimals is None else QDoubleSpinBox()
    w.setRange(lo,hi)
    if decimals is not None:w.setDecimals(decimals);w.setSingleStep(.1)
    w.setValue(value);return w


def table(headers):
    w=QTableWidget(0,len(headers));w.setHorizontalHeaderLabels(headers);w.setAlternatingRowColors(True)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    w.horizontalHeader().setStretchLastSection(True)
    return w


def cells(widget,row,values):
    for col,v in enumerate(values):widget.setItem(row,col,QTableWidgetItem(str(v)))


class Worker(QThread):
    event=Signal(object);completed=Signal(object)
    def __init__(self,func,parent=None):
        super().__init__(parent);self.func=func;self.stop=threading.Event()
    def run(self):
        try:self.completed.emit(dict(value=self.func(self.stop,self.event.emit)))
        except Cancelled:self.completed.emit(dict(cancelled=True))
        except Exception as exc:self.completed.emit(dict(error=str(exc)[-2500:]))


class Player(QDialog):
    def __init__(self,path,parent=None):
        super().__init__(parent);self.setWindowTitle('成片预览 · '+Path(path).name);self.resize(580,760)
        layout=QVBoxLayout(self);self.video=QVideoWidget();layout.addWidget(self.video,1)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.audio.setVolume(.8)
        self.player.setAudioOutput(self.audio);self.player.setVideoOutput(self.video)
        self.resume_after_seek=False
        self.timeline=SeekSlider(self);self.timeline.setRange(0,0);self.timeline.setEnabled(False)
        layout.addWidget(self.timeline)
        row=QHBoxLayout();self.play_button=button('暂停',self.toggle);row.addWidget(self.play_button)
        row.addStretch();self.time_label=QLabel('00:00 / 00:00');row.addWidget(self.time_label)
        layout.addLayout(row);self.state=QLabel();self.state.hide();layout.addWidget(self.state)
        self.timeline.sliderPressed.connect(self.begin_seek);self.timeline.sliderReleased.connect(self.end_seek)
        self.timeline.valueChanged.connect(self.seek_changed)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.seekableChanged.connect(lambda ready:self.timeline.setEnabled(ready and self.player.duration()>0))
        self.player.playbackStateChanged.connect(lambda state:self.play_button.setText('暂停' if state==QMediaPlayer.PlaybackState.PlayingState else '播放'))
        self.player.errorOccurred.connect(lambda e,t:(self.state.setText(t),self.state.show()))
        self.player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())));self.player.play()
    def toggle(self):
        if not self.player.isPlaying() and self.player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:self.player.setPosition(0)
        self.player.pause() if self.player.isPlaying() else self.player.play()
    @staticmethod
    def clock(milliseconds):
        seconds=max(0,milliseconds)//1000;hours,seconds=divmod(seconds,3600);minutes,seconds=divmod(seconds,60)
        return f'{hours:02}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'
    def show_time(self,position):
        self.time_label.setText(self.clock(position)+' / '+self.clock(self.player.duration()))
    def update_duration(self,duration):
        self.timeline.setRange(0,duration);self.timeline.setSingleStep(1000);self.timeline.setPageStep(5000)
        self.timeline.setEnabled(duration>0 and self.player.isSeekable());self.show_time(self.player.position())
    def update_position(self,position):
        if self.timeline.isSliderDown():return
        self.timeline.blockSignals(True);self.timeline.setValue(position);self.timeline.blockSignals(False);self.show_time(position)
    def begin_seek(self):
        self.resume_after_seek=self.player.isPlaying();self.player.pause()
    def seek_changed(self,position):
        self.show_time(position)
        if not self.timeline.isSliderDown():self.player.setPosition(position)
    def end_seek(self):
        self.player.setPosition(self.timeline.value())
        if self.resume_after_seek:self.player.play()
        self.resume_after_seek=False
    def done(self,result):
        self.player.stop();super().done(result)


SOUND=[('保留原声音（包含原音乐）','original'),('静音原片','mute'),('尝试去旧音乐，需试听','separate'),('使用独立口播/音效文件','external')]
MUSIC=[('不添加新音乐','none'),('整批指定同一首','one'),('按前贴随机固定一首','random_a'),('每条成片随机一首','random_job')]


class SoundControls(QGroupBox):
    def __init__(self,title,side,musics):
        super().__init__(title);self.side=side;self.musics=musics;f=QFormLayout(self)
        self.sound=combo(SOUND);self.volume=spin(0,3,1.,2);self.voice=QLineEdit()
        row=QHBoxLayout();row.addWidget(self.voice);row.addWidget(button('选择',self.pick_voice))
        self.mode=combo(MUSIC if side=='a' else [('不添加新音乐','none'),('整批指定同一首','one'),('每条成片随机一首','random_job')])
        self.music=QComboBox();self.refresh_music(musics)
        self.music_volume=spin(0,2,.3,2);self.offset=spin(0,86400,0.,2);self.offset.setSuffix(' 秒')
        f.addRow('原片声音',self.sound);f.addRow('口播/原声音量',self.volume);f.addRow('独立声音文件',row)
        f.addRow('新音乐分配',self.mode);f.addRow('指定音乐',self.music);f.addRow('新音乐音量',self.music_volume);f.addRow('音乐起点',self.offset)
        note=QLabel('混合音轨无法保证无损去音乐。分离也可能削弱游戏音效；请先试听样片。');note.setWordWrap(True);note.setProperty('muted',True);f.addRow(note)
    def refresh_music(self,musics):
        previous=self.music.currentData();self.music.clear();self.music.addItem('请选择音乐','')
        for a in musics:self.music.addItem(a['name'],a['path'])
        set_combo(self.music,previous)
    def pick_voice(self):
        p,_=QFileDialog.getOpenFileName(self,'选择独立口播/音效','', '声音 (*.wav *.mp3 *.m4a *.flac *.aac *.mp4);;所有文件 (*)')
        if p:self.voice.setText(p)
    def value(self):
        side=self.side
        return {side+'_sound':self.sound.currentData(),side+'_volume':self.volume.value(),side+'_voice':self.voice.text().strip(),
            side+'_music':self.music.currentData() or '',side+'_music_mode':self.mode.currentData(),side+'_music_volume':self.music_volume.value(),side+'_music_start':self.offset.value()}
    def load(self,s):
        x=self.side;set_combo(self.sound,s.get(x+'_sound','original'));self.volume.setValue(s.get(x+'_volume',1.))
        self.voice.setText(s.get(x+'_voice',''));set_combo(self.mode,s.get(x+'_music_mode','none'));set_combo(self.music,s.get(x+'_music',''))
        self.music_volume.setValue(s.get(x+'_music_volume',.3));self.offset.setValue(s.get(x+'_music_start',0.))


class IntroSoundDialog(QDialog):
    """Audition unsaved intro settings without creating jobs or history."""
    def __init__(self,assets,settings,overrides,musics,main_count,parent=None):
        super().__init__(parent);self.assets=copy.deepcopy(assets);self.settings=copy.deepcopy(settings)
        self.overrides=copy.deepcopy(overrides);self.musics=copy.deepcopy(musics);self.worker=None;self.preview_player=None;self.closing=False
        multiple=len(assets)>1;a=assets[0]
        self.setWindowTitle(f'批量设置 · {len(assets)} 条前贴' if multiple else '单独设置 · '+a['name']);self.resize(650,620)
        l=QVBoxLayout(self)
        self.apply_sound=QCheckBox('将下方声音设置应用到所有选中前贴');self.apply_sound.setChecked(True);self.apply_sound.setVisible(multiple);l.addWidget(self.apply_sound)
        self.controls=SoundControls('选中前贴的声音设置','a',musics)
        self.controls.load(dict(settings,**overrides.get(a['id'],{})));l.addWidget(self.controls)
        self.apply_fixed=QCheckBox('修改每条选中前贴的指定次数（未勾选时保留原次数）');self.apply_fixed.setChecked(not multiple);self.apply_fixed.setVisible(multiple);l.addWidget(self.apply_fixed)
        self.fixed=spin(-1,main_count,overrides.get(a['id'],{}).get('fixed',-1));self.fixed.setSpecialValueText('自动分配')
        f=QFormLayout();f.addRow('指定使用次数（0=不用）',self.fixed);l.addLayout(f)
        self.fixed.setEnabled(not multiple);self.apply_fixed.toggled.connect(self.fixed.setEnabled)
        self.inherit=QCheckBox('移除选中前贴的声音覆盖，使用整批声音设置');l.addWidget(self.inherit)
        self.apply_sound.toggled.connect(self.update_controls);self.inherit.toggled.connect(self.update_controls)
        self.source=QComboBox()
        for item in assets:self.source.addItem(item['name'],item['id'])
        f=QFormLayout();f.addRow('试听前贴',self.source);l.addLayout(f)
        note=QLabel('试听当前未保存的声音设置，仅播放所选前贴，不加字幕、不占用配对。随机模式试听一首示例，最终曲目以生成计划为准。');note.setWordWrap(True);l.addWidget(note)
        row=QHBoxLayout();self.preview_button=button('试听当前设置',self.preview,True);self.preview_button.setAutoDefault(False);row.addWidget(self.preview_button)
        self.cancel_preview=button('停止生成',self.stop_preview);self.cancel_preview.setEnabled(False);self.cancel_preview.setAutoDefault(False);row.addWidget(self.cancel_preview);l.addLayout(row)
        self.status=QLabel('修改音量或音乐起点后，点击试听重新生成。');self.status.setWordWrap(True);l.addWidget(self.status)
        self.bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.bb.button(QDialogButtonBox.StandardButton.Save).setText('保存');self.bb.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.bb.accepted.connect(self.accept);self.bb.rejected.connect(self.reject);l.addWidget(self.bb)
        self.last_result=None;self.last_settings=None
    def update_controls(self):
        self.controls.setEnabled(self.apply_sound.isChecked() and not self.inherit.isChecked())
    def audition_settings(self):
        a=self.assets[self.source.currentIndex()];s=copy.deepcopy(self.settings)
        if not self.inherit.isChecked():
            s.update(self.overrides.get(a['id'],{}))
            if self.apply_sound.isChecked():s.update(self.controls.value())
        mode=s.get('a_music_mode','none')
        if mode=='none':s['a_music']=''
        elif mode in ('random_a','random_job'):
            if not self.musics:raise ValueError('随机音乐需要先添加音乐库。')
            s['a_music']=random.Random(s['seed']).choice(self.musics)['path']
        elif mode=='one' and not s.get('a_music'):raise ValueError('指定音乐模式需要选择一首音乐。')
        if s['a_sound']=='external' and not s.get('a_voice'):raise ValueError('独立声音模式需要指定口播/音效文件。')
        s['subtitles']=False
        return a,s
    def preview(self):
        if self.worker is not None:return
        try:a,s=self.audition_settings()
        except Exception as exc:self.status.setText('无法试听：'+str(exc));return
        self.last_settings=copy.deepcopy(s);self.last_result=None
        music=Path(s['a_music']).name if s['a_music'] else '无新音乐'
        self.status.setText('正在生成试听 · '+a['name']+' · '+music+'（可停止）')
        self.preview_button.setEnabled(False);self.cancel_preview.setEnabled(True)
        def work(stop,notify):
            if identity(a['path'])!=a['id']:raise ValueError('前贴内容已改变，请重新导入。')
            engine=MediaEngine(stop)
            try:
                path,duration=engine.prepare(a['path'],s,'a')
                if stop.is_set():raise Cancelled()
                return dict(path=str(path),duration=duration,name=a['name'],music=music)
            finally:engine.close()
        self.worker=Worker(work,self);self.worker.completed.connect(self.preview_done);self.worker.start()
    def preview_done(self,result):
        worker=self.worker
        if worker is not None:
            worker.wait()
            if worker.stop.is_set():result=dict(cancelled=True)
            worker.deleteLater()
        self.worker=None
        if self.closing:return
        self.preview_button.setEnabled(True);self.cancel_preview.setEnabled(False);self.last_result=result
        if 'value' in result:
            value=result['value'];self.status.setText('试听已生成 · '+value['name']+' · '+value['music'])
            self.preview_player=Player(value['path'],self)
            self.preview_player.setWindowTitle('前贴声音试听 · '+value['name']+' · '+value['music'])
            self.preview_player.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self.preview_player.setWindowModality(Qt.WindowModality.WindowModal);self.preview_player.show()
        elif result.get('cancelled'):self.status.setText('已停止生成，可修改设置后重新试听。')
        else:self.status.setText('试听失败：'+result.get('error','未知错误'))
    def stop_preview(self):
        if self.worker is not None:self.worker.stop.set();self.cancel_preview.setEnabled(False);self.status.setText('正在停止生成…')
    def done(self,result):
        self.closing=True
        if self.worker is not None:self.worker.stop.set();self.worker.wait()
        # A parent can close while the child player is still open.
        for player in self.findChildren(Player):player.done(0)
        super().done(result)


class SubtitleDialog(QDialog):
    def __init__(self,source,settings,rows,parent):
        super().__init__(parent);self.source=source;self.settings=copy.deepcopy(settings);self.worker=None
        self.setWindowTitle('字幕校正 · '+source['name']);self.resize(1150,770)
        layout=QVBoxLayout(self);note=QLabel('识别后可直接改文字和起止时间。提供文稿可生成初步对齐，保存前请检查预览。');layout.addWidget(note)
        split=QSplitter();layout.addWidget(split,1);left=QWidget();l=QVBoxLayout(left);split.addWidget(left)
        self.rows_table=table(['开始（秒）','结束（秒）','字幕文字']);self.rows_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed)
        l.addWidget(self.rows_table,1);self.load_rows(rows or [])
        row=QHBoxLayout();row.addWidget(button('离线识别口播',self.recognize,True));row.addWidget(button('导入 SRT',self.import_srt));row.addWidget(button('导出 SRT',self.export_srt));l.addLayout(row)
        row=QHBoxLayout();row.addWidget(button('添加字幕',self.add_row));row.addWidget(button('删除选中',self.remove_rows));l.addLayout(row)
        self.script=QPlainTextEdit();self.script.setPlaceholderText('可粘贴完整口播文稿。建议先识别，再按文稿生成初步时间。');self.script.setMaximumHeight(100);l.addWidget(self.script)
        l.addWidget(button('按文稿初步对齐到当前时间',self.align))
        self.status=QLabel('尚未修改');self.status.setWordWrap(True);l.addWidget(self.status)
        self.frame=FramePreview(source['path'],settings,self,duration=source['duration']);split.addWidget(self.frame)
        self.frame.refresh.clicked.connect(self.preview)
        self.frame.seekRequested.connect(self.preview)
        split.setSizes([670,420])
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存字幕')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        # Enter in the precise time field commits a preview rather than closing.
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False);b.setDefault(False)
        QTimer.singleShot(0,self.preview)
    def load_rows(self,rows):
        self.rows_table.setRowCount(len(rows))
        for n,row in enumerate(rows):cells(self.rows_table,n,[f'{row["start"]:.3f}',f'{row["end"]:.3f}',row['text']])
    def rows(self):
        result=[];last=0.
        for n in range(self.rows_table.rowCount()):
            try:start=float(self.rows_table.item(n,0).text());end=float(self.rows_table.item(n,1).text());text=self.rows_table.item(n,2).text().strip()
            except (ValueError,AttributeError):raise ValueError(f'第{n+1}条时间或文字为空/无效。')
            if not text or not 0<=start<end<=self.source['duration']+.05 or start<last-.01:
                raise ValueError(f'第{n+1}条时间超出素材、重叠或为空，请修正。')
            last=end;result.append(dict(start=start,end=end,text=text))
        return result
    def add_row(self):
        n=self.rows_table.rowCount();self.rows_table.setRowCount(n+1)
        start=float(self.rows_table.item(n-1,1).text()) if n and self.rows_table.item(n-1,1) else 0
        cells(self.rows_table,n,[str(start),str(min(self.source['duration'],start+2)),'填写字幕'])
    def remove_rows(self):
        for row in sorted({i.row() for i in self.rows_table.selectedIndexes()},reverse=True):self.rows_table.removeRow(row)
    def recognize(self):
        if self.worker and self.worker.isRunning():return
        self.status.setText('正在本机离线识别，首次可能需要几十秒…')
        def work(stop,notify):
            e=MediaEngine(stop,lambda t:notify(dict(type='log',text=t)))
            try:return e.ensure_subtitles(self.source['path'],self.settings)
            finally:e.close()
        self.worker=Worker(work,self);self.worker.event.connect(lambda e:self.status.setText(e['text']));self.worker.completed.connect(self.recognized);self.worker.start()
    def recognized(self,result):
        self.worker.wait()
        if 'value' in result:self.load_rows(result['value']);self.status.setText('识别完成，请校正文字和时间。没有口播时可能没有字幕。')
        elif 'error' in result:self.status.setText(result['error'])
    def import_srt(self):
        p,_=QFileDialog.getOpenFileName(self,'导入字幕','','字幕 (*.srt)')
        if p:
            try:self.load_rows(read_srt(Path(p)));self.status.setText('已导入字幕，请检查时间。')
            except Exception as exc:QMessageBox.warning(self,'字幕错误',str(exc))
    def export_srt(self):
        try:
            rows=self.rows();p,_=QFileDialog.getSaveFileName(self,'保存字幕',self.source['name']+'.srt','字幕 (*.srt)')
            if p:write_srt(Path(p),rows)
        except Exception as exc:QMessageBox.warning(self,'字幕错误',str(exc))
    def align(self):
        try:self.load_rows(align_script(self.script.toPlainText(),self.rows(),self.source['duration']));self.status.setText('已生成可编辑的初步时间。文稿对齐不是精确音素对齐，务必检查。')
        except Exception as exc:QMessageBox.warning(self,'对齐问题',str(exc))
    def preview(self):
        try:self.frame.render(dict(self.settings,subtitles=True),self.rows())
        except Exception as exc:QMessageBox.warning(self,'字幕错误',str(exc))
    def save(self):
        try:self.result_rows=self.rows();self.accept()
        except Exception as exc:QMessageBox.warning(self,'字幕错误',str(exc))
    def done(self,result):
        if self.worker and self.worker.isRunning():self.worker.stop.set();self.worker.wait()
        self.frame.stop();super().done(result)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('混剪工坊 · Montage Studio '+__version__);self.resize(1280,880);self.setMinimumSize(1040,720)
        self.setWindowIcon(QIcon(str(asset('ui/MontageStudio.ico'))))
        self.dark=False;self.nav_buttons=[];self.icon_buttons=[]
        self.store=Store();self.assets={'a':[],'b':[],'music':[]};self.overrides={};self.plan=[];self.plan_settings=[];self.plan_assets={};self.bid=None;self.worker=None;self.last_preview='';self.api_key='';self.api_config={}
        self.thumbnail_loader=ThumbnailLoader(self);self.thumbnail_loader.ready.connect(self.thumbnail_ready)
        self.thumbnail_icons={};self.thumbnail_loader.start()
        self.thumbnail_placeholder=QIcon()
        self.setAcceptDrops(True)
        root=QWidget();self.setCentralWidget(root);shell=QHBoxLayout(root);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(190);sl=QVBoxLayout(sidebar);sl.setContentsMargins(16,24,16,18);sl.setSpacing(6)
        logo=QLabel();logo.setPixmap(QPixmap(str(asset('ui/logo.png'))).scaled(38,38,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        brand=QLabel('混剪工坊');brand.setObjectName('brand');brand_row=QHBoxLayout();brand_row.addWidget(logo);brand_row.addWidget(brand);brand_row.addStretch();sl.addLayout(brand_row)
        caption=QLabel('本机视频批量制作');caption.setProperty('muted',True);sl.addWidget(caption);sl.addSpacing(30)
        names=['素材','画面与声音','组合计划','导出队列','本机历史'];icons=['layout-grid','adjustments-horizontal','arrows-shuffle','player-play','history']
        for n,(name,glyph) in enumerate(zip(names,icons)):
            b=button(name,lambda checked=False,i=n:self.tabs.setCurrentIndex(i));b.setProperty('nav',True);b.setCheckable(True);b.setIconSize(QSize(18,18));sl.addWidget(b);self.nav_buttons.append(b);self.icon_buttons.append((b,glyph))
        sl.addStretch();self.theme_button=button('切换深色',self.toggle_theme);self.theme_button.setProperty('quiet',True);sl.addWidget(self.theme_button)
        help_button=button('使用说明',self.help);help_button.setProperty('quiet',True);sl.addWidget(help_button)
        offline=QLabel('离线处理，素材不上传');offline.setProperty('muted',True);sl.addWidget(offline);shell.addWidget(sidebar)
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(26,24,26,14);layout.setSpacing(8);shell.addWidget(content,1)
        self.page_title=QLabel('素材');self.page_title.setObjectName('pageTitle');layout.addWidget(self.page_title)
        self.page_description=QLabel();self.page_description.setObjectName('pageDescription');layout.addWidget(self.page_description);layout.addSpacing(12)
        self.tabs=QTabWidget();self.tabs.tabBar().hide();layout.addWidget(self.tabs,1)
        self.material_tab();self.settings_tab();self.plan_tab();self.queue_tab();self.history_tab()
        self.footer=QLabel('所有视频、字幕识别和音乐分离均在本机处理。');self.footer.setProperty('muted',True);layout.addWidget(self.footer)
        self.tabs.currentChanged.connect(self.update_navigation)
        self.load_session();self.refresh_assets();self.refresh_batches();self.update_navigation(0);self.set_theme(self.dark,save=False)
    def update_navigation(self,index):
        titles=['素材','画面与声音','组合计划','导出队列','本机历史']
        descriptions=['导入前贴、主视频与音乐，勾选后批量管理。','设置整批画面、声音与字幕，前贴可单独覆盖。','先检查配对与使用次数，再固定任务导出。','已完成成片保留，暂停后可继续。','配对历史只保存在本机，换音乐不算新配对。']
        self.page_title.setText(titles[index]);self.page_description.setText(descriptions[index])
        for n,b in enumerate(self.nav_buttons):b.setChecked(n==index)
        if index==4:self.refresh_cache_size()
        if index==0:self.update_quick_summary()
    def toggle_theme(self):self.set_theme(not self.dark)
    def set_theme(self,dark,save=True):
        self.dark=bool(dark);apply_theme(QApplication.instance(),self.dark);t=tokens(self.dark)
        for b,glyph in self.icon_buttons:b.setIcon(ui_icon(glyph,t['on_accent'] if b.property('primary') else t['ink']))
        self.theme_button.setText('切换浅色' if self.dark else '切换深色');self.theme_button.setIcon(ui_icon('sun' if self.dark else 'moon',t['ink']))
        for w in self.lists.values():w.dark=self.dark;w.viewport().update()
        self.cloud_panel.grid.dark=self.dark;self.cloud_panel.grid.viewport().update()
        if save:self.save_session()
    def notify_error(self,exc):QMessageBox.warning(self,'请检查',str(exc)[-2500:])
    def busy(self):return self.worker is not None and self.worker.isRunning()
    def start_work(self,func,done):
        if self.busy():self.notify_error('当前正在处理，请先暂停或等待结束。');return False
        self.worker=Worker(func,self);self.worker.event.connect(self.on_worker_event)
        def completed(result):
            self.worker.wait();self.cancel_work.setEnabled(False);self.footer.setText('就绪 · 数据保存在 '+str(data_dir()))
            if 'error' in result:self.notify_error(result['error'])
            done(result)
        self.worker.completed.connect(completed);self.cancel_work.setEnabled(True);self.worker.start();return True
    def on_worker_event(self,e):
        if e['type']=='log':self.log.appendPlainText(e['text']);self.footer.setText(e['text'][:160])
        elif e['type']=='job':
            if self.bid:
                row=e['number']-1;self.jobs_table.setItem(row,3,QTableWidgetItem(self.status_name(e['status'])))
                if 'output' in e:self.jobs_table.setItem(row,4,QTableWidgetItem(e['output']))
                if 'error' in e:self.jobs_table.setItem(row,5,QTableWidgetItem(e['error']))
                complete=sum(1 for n in range(self.jobs_table.rowCount()) if self.jobs_table.item(n,3) and self.jobs_table.item(n,3).text()=='完成')
                self.total_progress.setMaximum(max(1,self.jobs_table.rowCount()));self.total_progress.setValue(complete)
                self.queue_status.setText(f'完成 {complete} / {self.jobs_table.rowCount()} · 当前第{e["number"]}条')
        elif e['type']=='progress':self.current_progress.setValue(e['value'])
    def material_tab(self):
        page=QWidget();l=QVBoxLayout(page);l.setContentsMargins(0,0,0,0);l.setSpacing(12)
        row=QHBoxLayout();row.addWidget(QLabel('游戏 / 历史分组'));self.game=QLineEdit('默认游戏');self.game.setMaximumWidth(420);row.addWidget(self.game,1);row.addStretch();self.recursive=QCheckBox('包含子文件夹');self.recursive.setChecked(True);row.addWidget(self.recursive);l.addLayout(row)
        self.material_tabs=QTabWidget();self.material_tabs.setDocumentMode(True);self.lists={};self.counts={};l.addWidget(self.material_tabs,1)
        for role,title in [('a','A 前贴'),('b','B 主视频'),('music','音乐库')]:
            panel=QWidget();bl=QVBoxLayout(panel);bl.setContentsMargins(0,16,0,0);bl.setSpacing(10)
            br=QHBoxLayout();self.counts[role]=QLabel('0 条素材 · 已选 0 条');self.counts[role].setProperty('muted',True);br.addWidget(self.counts[role]);br.addStretch()
            for text,callback,glyph,primary in [('添加文件',lambda checked=False,r=role:self.import_files(r),'plus',True),('添加文件夹',lambda checked=False,r=role:self.import_folder(r),'folder',False)]:
                b=button(text,callback,primary);b.setIconSize(QSize(16,16));br.addWidget(b);self.icon_buttons.append((b,glyph))
            bl.addLayout(br)
            w=MaterialGrid(role);self.lists[role]=w;bl.addWidget(w,1)
            w.itemSelectionChanged.connect(lambda r=role:self.update_selection_count(r))
            w.itemDoubleClicked.connect(lambda item,r=role:self.play_source(r))
            br=QHBoxLayout();all_button=button('全选',w.selectAll);clear_button=button('取消选择',w.clearSelection)
            for b in [all_button,clear_button]:b.setProperty('quiet',True);br.addWidget(b)
            br.addStretch();br.addWidget(button('移除选中',lambda checked=False,r=role:self.remove_assets(r)));br.addWidget(button('播放原片',lambda checked=False,r=role:self.play_source(r)));bl.addLayout(br)
            if role=='a':
                br=QHBoxLayout();br.addWidget(button('设置选中前贴 / 指定使用次数',self.edit_intro));br.addWidget(button('编辑 / 识别字幕（单条）',self.edit_subtitles));br.addStretch();bl.addLayout(br)
            self.material_tabs.addTab(panel,title+' (0)')
        from .cloud_ui import CloudPanel
        self.cloud_panel=CloudPanel(self);self.material_tabs.addTab(self.cloud_panel,'云端前贴')
        quick=QGroupBox('一键拼接');ql=QVBoxLayout(quick)
        row=QHBoxLayout();self.quick_mode=combo([('最大可用数量','max'),('指定数量','count')]);row.addWidget(self.quick_mode)
        self.quick_quantity=spin(1,MAX_BATCH,1000);self.quick_quantity.setEnabled(False);row.addWidget(self.quick_quantity)
        self.quick_button=button('一键拼接并导出',self.quick_export,True);row.addWidget(self.quick_button);row.addStretch();ql.addLayout(row)
        self.quick_summary=QLabel('请勾选 A 前贴和 B 主视频。');self.quick_summary.setWordWrap(True);ql.addWidget(self.quick_summary)
        self.quick_output=QLabel();self.quick_output.setWordWrap(True);row=QHBoxLayout();row.addWidget(self.quick_output,1);row.addWidget(button('更改保存位置',self.pick_output));ql.addLayout(row)
        note=QLabel('默认：竖屏720p · 硬切 · A/B保留原声 · 随机不重复。换音乐、字幕或指定次数请用下方高级流程。');note.setWordWrap(True);note.setProperty('muted',True);ql.addWidget(note)
        self.quick_mode.currentIndexChanged.connect(self.update_quick_summary);self.game.textChanged.connect(self.update_quick_summary);l.addWidget(quick)
        row=QHBoxLayout();note=QLabel('直接勾选即可多选，双击播放。主视频默认保留原声。');note.setProperty('muted',True);row.addWidget(note);row.addStretch();row.addWidget(button('下一步：画面与声音',lambda:self.tabs.setCurrentIndex(1),True));l.addLayout(row)
        self.tabs.addTab(page,'① 素材')
    def settings_tab(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();scroll.setWidget(page);l=QVBoxLayout(page)
        row=QHBoxLayout();box=QGroupBox('画面与导出');f=QFormLayout(box)
        self.resolution=combo([('竖屏 720 × 1280','720x1280'),('竖屏 1080 × 1920','1080x1920'),('横屏 1280 × 720','1280x720'),('测试 360 × 640','360x640')])
        self.fps=combo([(str(n)+' fps',n) for n in [30,25,24,60]]);self.fit=combo([('完整显示，边缘留黑','pad'),('填满画面，裁切边缘','crop')])
        self.transition=combo([('硬切（推荐，最快）','cut'),('淡入淡出','fade'),('溶解','dissolve'),('向左擦除','wipeleft'),('向左滑动','slideleft')])
        self.transition_duration=spin(.1,3,.5,2);self.audio_transition=combo([('连接处直接切换','cut'),('声音交叉渐变','crossfade')])
        self.encoder=combo([('NVIDIA优先，失败自动CPU','nvidia'),('CPU兼容编码','cpu')]);self.performance=combo([('后台模式 · 顺序导出','background'),('全速模式 · 增加CPU线程','full')])
        self.crf=spin(16,28,20);self.output=QLineEdit(str(Path.home()/'Videos'/'混剪成片'))
        br=QHBoxLayout();br.addWidget(self.output);br.addWidget(button('选择',self.pick_output))
        for label,w in [('尺寸',self.resolution),('帧率',self.fps),('画面适配',self.fit),('转场',self.transition),('转场秒数',self.transition_duration),('声音连接',self.audio_transition),('编码',self.encoder),('性能',self.performance),('质量值（越低越清晰）',self.crf)]:f.addRow(label,w)
        f.addRow('输出文件夹',br);note=QLabel('非硬切转场会重叠两段视频，成片会缩短相应时长；可能遮住连接处口播。');note.setWordWrap(True);note.setProperty('muted',True);f.addRow(note)
        row.addWidget(box,1);subs=QGroupBox('前贴字幕');sf=QFormLayout(subs)
        self.subtitles=QCheckBox('自动识别并烧录前贴字幕');self.language=combo([('中文','zh'),('自动语言','auto'),('英文','en'),('日文','ja'),('韩文','ko')])
        self.vocabulary=QLineEdit();self.vocabulary.setPlaceholderText('游戏名、人名、专有词，帮助识别')
        self.font_size=spin(18,100,52);self.margin=spin(0,500,110);self.outline=spin(0,8,3);self.subtitle_position=combo([('底部','bottom'),('中间','center'),('顶部','top')]);self.font_color=QLineEdit('#FFFFFF')
        for label,w in [('',self.subtitles),('语言',self.language),('术语提示',self.vocabulary),('字号（按720p）',self.font_size),('距边缘（按720p）',self.margin),('描边',self.outline),('字幕位置',self.subtitle_position),('文字颜色',self.font_color)]:sf.addRow(label,w)
        sf.addRow(button('选择文字颜色',self.pick_color));note=QLabel('字幕可在“素材”中逐条校正。已有硬字幕不会自动消除，叠加前请检查。');note.setWordWrap(True);note.setProperty('muted',True);sf.addRow(note);row.addWidget(subs,1);l.addLayout(row)
        row=QHBoxLayout();self.a_sound=SoundControls('前贴声音', 'a',[]);self.b_sound=SoundControls('主视频声音','b',[]);row.addWidget(self.a_sound);row.addWidget(self.b_sound);l.addLayout(row)
        l.addWidget(button('下一步：生成组合计划',lambda:self.tabs.setCurrentIndex(2),True));self.tabs.addTab(scroll,'② 画面与声音')
    def plan_tab(self):
        page=QWidget();l=QVBoxLayout(page);l.setContentsMargins(16,16,16,16)
        self.instruction=QLineEdit();self.instruction.setPlaceholderText('例如：生成1000条，均匀分配，前贴01用200次，不重复')
        row=QHBoxLayout();row.addWidget(self.instruction,1);row.addWidget(button('理解规则',self.parse_text,True));row.addWidget(button('AI接口设置',self.api_dialog));l.addLayout(row)
        self.rule_hint=QLabel('默认使用离线规则解析。也可自行配置兼容接口；在线仅发送此处的指令文字。');self.rule_hint.setProperty('muted',True);l.addWidget(self.rule_hint)
        row=QHBoxLayout();row.addWidget(QLabel('输出数量'));self.quantity=spin(1,100000,1000);row.addWidget(self.quantity)
        self.mode=combo([('严格均匀（指定次数之外均匀）','balanced'),('随机分配','random')]);row.addWidget(self.mode);row.addWidget(QLabel('随机种子'));self.seed=spin(0,2147483647,42);row.addWidget(self.seed)
        row.addWidget(button('生成 / 重新生成计划',self.generate_plan,True));l.addLayout(row)
        self.plan_summary=QLabel('计划尚未生成。生成后可双击前贴或主视频列更换配对，再检查无重复和使用次数。');self.plan_summary.setWordWrap(True);l.addWidget(self.plan_summary)
        self.plan_table=table(['序号','前贴','主视频','前贴音乐','主视频音乐','转场']);self.plan_table.cellDoubleClicked.connect(self.edit_pair);l.addWidget(self.plan_table,1)
        row=QHBoxLayout();row.addWidget(button('预览选中成片',self.preview));row.addWidget(button('播放上次预览',self.play_last));row.addWidget(button('保存计划 CSV',self.export_plan));row.addStretch();l.addLayout(row)
        row=QHBoxLayout();row.addStretch();row.addWidget(button('固定计划并创建导出任务',self.create_batch,True));l.addLayout(row)
        self.tabs.addTab(page,'③ 组合计划')
    def queue_tab(self):
        page=QWidget();l=QVBoxLayout(page);l.setContentsMargins(16,16,16,16)
        row=QHBoxLayout();self.batch_combo=QComboBox();row.addWidget(self.batch_combo,1);row.addWidget(button('载入任务',self.load_batch));row.addWidget(button('刷新',self.refresh_batches));l.addLayout(row)
        self.queue_status=QLabel('尚未选择导出任务');l.addWidget(self.queue_status)
        self.total_progress=QProgressBar();self.current_progress=QProgressBar();l.addWidget(self.total_progress);l.addWidget(self.current_progress)
        self.jobs_table=table(['序号','前贴','主视频','状态','输出文件','错误']);self.jobs_table.cellDoubleClicked.connect(self.play_job);l.addWidget(self.jobs_table,1)
        row=QHBoxLayout();row.addWidget(button('开始 / 继续待处理',lambda:self.start_batch(False),True));row.addWidget(button('重试失败 + 继续',lambda:self.start_batch(True)))
        self.cancel_work=button('暂停当前处理',self.pause);self.cancel_work.setEnabled(False);row.addWidget(self.cancel_work)
        row.addStretch();l.addLayout(row)
        row=QHBoxLayout();row.addWidget(button('打开输出目录',self.open_output));row.addWidget(button('重定位遗失素材',self.relocate));row.addWidget(button('放弃未完成任务',self.abandon));row.addStretch();l.addLayout(row)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(800);self.log.setMaximumHeight(130);l.addWidget(self.log)
        self.tabs.addTab(page,'④ 导出队列')
    def history_tab(self):
        page=QWidget();l=QVBoxLayout(page);l.setContentsMargins(16,16,16,16)
        self.history_summary=QLabel();l.addWidget(self.history_summary);self.history_table=table(['游戏','前贴身份','主视频身份','完成时间','输出位置']);l.addWidget(self.history_table,1)
        row=QHBoxLayout();row.addWidget(button('刷新历史',self.refresh_history));self.delete_history_button=button('删除选中记录',self.delete_selected_history);row.addWidget(self.delete_history_button);row.addWidget(button('备份任务与历史',self.backup));row.addWidget(button('恢复备份',self.restore));row.addStretch();l.addLayout(row)
        self.cache_size_label=QLabel('点击刷新查看缓存大小');self.cache_size_label.setWordWrap(True);l.addWidget(self.cache_size_label)
        row=QHBoxLayout();row.addWidget(button('导出历史 CSV',self.export_history));row.addWidget(button('刷新缓存大小',self.refresh_cache_size));self.cache_button=button('清理处理缓存',self.clear_cache);row.addWidget(self.cache_button);row.addStretch();l.addLayout(row)
        note=QLabel('历史仅在本机保存，成功成片才记入历史。双击记录可预览成片；删除历史记录会释放该配对，输出文件和源视频保留。完整备份包含任务与配方，不包含源视频。');note.setWordWrap(True);note.setProperty('muted',True);l.addWidget(note)
        self.history_table.cellDoubleClicked.connect(self.preview_history)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.history_table.setToolTip('双击任意列预览成片；Ctrl / Shift 可选择多条记录。')
        self.tabs.addTab(page,'⑤ 本机历史');self.refresh_history()
    def settings(self):
        s=dict(SETTINGS)
        for key in ['resolution','fps','fit','transition','audio_transition','encoder','performance','subtitle_position','language']:s[key]=getattr(self,key).currentData()
        for key in ['transition_duration','crf','font_size','margin','outline']:s[key]=getattr(self,key).value()
        s.update(subtitles=self.subtitles.isChecked(),vocabulary=self.vocabulary.text(),font_color=self.font_color.text(),output=self.output.text().strip(),seed=self.seed.value())
        s.update(self.a_sound.value());s.update(self.b_sound.value());return s
    def apply_settings(self,s):
        for key in ['resolution','fps','fit','transition','audio_transition','encoder','performance','subtitle_position','language']:set_combo(getattr(self,key),s.get(key,SETTINGS[key]))
        for key in ['transition_duration','crf','font_size','margin','outline']:getattr(self,key).setValue(s.get(key,SETTINGS[key]))
        self.subtitles.setChecked(s.get('subtitles',False));self.vocabulary.setText(s.get('vocabulary',''));self.font_color.setText(s.get('font_color','#FFFFFF'));self.output.setText(s.get('output') or str(Path.home()/'Videos'/'混剪成片'))
        self.a_sound.load(s);self.b_sound.load(s)
        self.update_quick_summary()
    def save_session(self):
        write_json(data_dir()/'session.json',dict(assets=self.assets,overrides=self.overrides,settings=self.settings(),game=self.game.text(),quantity=self.quantity.value(),mode=self.mode.currentData(),seed=self.seed.value(),api=self.api_config,ui_theme='dark' if self.dark else 'light'))
    def load_session(self):
        try:
            s=json.loads((data_dir()/'session.json').read_text(encoding='utf-8'));self.assets=s.get('assets',self.assets);self.overrides=s.get('overrides',{})
            self.dark=s.get('ui_theme','light')=='dark'
            self.refresh_assets();self.apply_settings(s.get('settings',{}));self.game.setText(s.get('game','默认游戏'));self.quantity.setValue(s.get('quantity',1000));set_combo(self.mode,s.get('mode','balanced'));self.seed.setValue(s.get('seed',42));self.api_config=s.get('api',{})
        except (OSError,ValueError,KeyError):pass
    def refresh_assets(self):
        for role,w in self.lists.items():
            selected={i.data(Qt.ItemDataRole.UserRole) for i in w.selectedItems()}
            current=w.currentItem().data(Qt.ItemDataRole.UserRole) if w.currentItem() else None
            w.blockSignals(True)
            w.clear()
            for n,a in enumerate(self.assets[role],1):
                prefix=f'{n:02}  ' if role=='a' else ''
                extra=''
                if role=='a' and a['id'] in self.overrides:
                    override=self.overrides[a['id']]
                    extra=' · 单独设置'
                    if override.get('fixed',-1)>=0:extra+=f' · {override["fixed"]}次'
                    if override.get('subtitle_rows') is not None:extra+=' · 已校正字幕'
                detail=f'{a["duration"]:.1f}s' if role=='music' else f'{a["duration"]:.1f}s · {a["width"]}×{a["height"]}'
                item=QListWidgetItem(prefix+a['name']);item.setToolTip(a['name']+'\n'+a['path']+extra);item.setData(Qt.ItemDataRole.UserRole,a['id']);item.setData(NAME,prefix+a['name']);item.setData(DETAIL,detail);item.setData(EXTRA,extra.lstrip(' ·'));item.setData(KIND,role)
                if a.get('cloud'):
                    item.setToolTip(item.toolTip()+'\n云端备注：'+(a['cloud'].get('note') or '无')+'\n来源：'+a['cloud'].get('source_url',''))
                item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked);w.addItem(item)
                if role!='music':
                    item.setIcon(self.thumbnail_icons.get(a['id'],self.thumbnail_placeholder))
                    cached=self.thumbnail_loader.path(a['id'])
                    if a['id'] not in self.thumbnail_icons:
                        pixmap=QPixmap(str(cached)) if cached.exists() else QPixmap()
                        if not pixmap.isNull():
                            self.thumbnail_icons[a['id']]=QIcon(pixmap);item.setIcon(self.thumbnail_icons[a['id']])
                        else:
                            cached.unlink(missing_ok=True);self.thumbnail_loader.submit(a)
                if a['id']==current:w.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
                item.setSelected(a['id'] in selected)
            w.blockSignals(False);w.sync_checks();self.update_selection_count(role)
        self.a_sound.refresh_music(self.assets['music']);self.b_sound.refresh_music(self.assets['music'])
    def update_selection_count(self,role):
        self.counts[role].setText(f'{len(self.assets[role])} 条素材 · 已选 {len(self.lists[role].selectedItems())} 条')
        i={'a':0,'b':1,'music':2}[role]
        if i<self.material_tabs.count():self.material_tabs.setTabText(i,{'a':'A 前贴','b':'B 主视频','music':'音乐库'}[role]+f' ({len(self.assets[role])})')
        self.update_quick_summary()
    def quick_ids(self,role):
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.lists[role].selectedItems()]
    def update_quick_summary(self,*args):
        if not hasattr(self,'quick_summary') or not hasattr(self,'output'):return
        a,b=self.quick_ids('a'),self.quick_ids('b');n=available_count(a,b,self.store.excluded(self.game.text().strip()))
        self.quick_quantity.setEnabled(self.quick_mode.currentData()=='count')
        self.quick_summary.setText(f'已选 A {len(a)} 条 × B {len(b)} 条 · 扣除历史及任务占用后最多 {n} 条'+('（单任务上限100000，请使用指定数量分批）' if n>MAX_BATCH else ''))
        self.quick_output.setText('保存到：'+self.output.text())
    def quick_export(self):
        if self.busy():self.notify_error('正在处理，请先暂停或等待完成。');return
        try:
            a,b=self.quick_ids('a'),self.quick_ids('b');game=self.game.text().strip()
            if not a or not b:raise ValueError('请先分别勾选 A 前贴和 B 主视频。')
            if not game:raise ValueError('请填写游戏 / 历史分组。')
            if not self.output.text().strip():raise ValueError('请选择保存位置。')
            n=available_count(a,b,self.store.excluded(game))
            if not n:raise ValueError('选中的配对已被历史或其他任务使用，没有剩余配对。')
            count=n if self.quick_mode.currentData()=='max' else self.quick_quantity.value()
            if count>MAX_BATCH:raise ValueError('单任务最多100000条，请选择指定数量分批导出。')
            pairs=make_plan(a,b,count,'random',excluded=self.store.excluded(game))
            s=copy.deepcopy(SETTINGS);s['output']=self.output.text().strip()
            am={x['id']:copy.deepcopy(x) for role in ('a','b') for x in self.assets[role] if x['id'] in set(a+b)}
            bid=self.store.create(game,am,pairs,s,[copy.deepcopy(s) for _ in pairs],name=f'一键拼接 {count}条')
            self.bid=bid;self.refresh_batches();set_combo(self.batch_combo,bid);self.load_batch();self.tabs.setCurrentIndex(3);self.save_session();self.update_quick_summary();self.start_batch(False)
        except Exception as exc:self.notify_error(exc)
    def thumbnail_ready(self,key,path,error):
        if path:
            pixmap=QPixmap(path)
            if pixmap.isNull():error='无法读取缩略图'
            else:self.thumbnail_icons[key]=QIcon(pixmap)
        for role in ('a','b'):
            w=self.lists[role]
            for n in range(w.count()):
                item=w.item(n)
                if item.data(Qt.ItemDataRole.UserRole)==key:
                    if key in self.thumbnail_icons:item.setIcon(self.thumbnail_icons[key]);item.setData(ERROR,'')
                    elif error:
                        item.setToolTip(item.toolTip()+'\n缩略图不可用：'+error)
                        item.setData(ERROR,error);item.setIcon(QIcon())
    def import_files(self,role):
        paths,_=QFileDialog.getOpenFileNames(self,'选择素材','','媒体 (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wav *.mp3 *.m4a *.flac *.aac);;所有文件 (*)')
        if paths:self.import_paths(role,paths)
    def import_folder(self,role):
        p=QFileDialog.getExistingDirectory(self,'选择素材文件夹（支持网络路径）')
        if p:self.import_paths(role,[p])
    def import_paths(self,role,paths):
        if self.busy():self.notify_error('正在处理，请先暂停或等处理结束再导入。');return
        expanded=[];extensions={'.mp4','.mov','.mkv','.avi','.webm','.m4v'}
        if role=='music':extensions|={'.wav','.mp3','.m4a','.flac','.aac','.ogg'}
        for p in paths:
            p=Path(p)
            if p.is_dir():expanded.extend(str(x) for x in (p.rglob('*') if self.recursive.isChecked() else p.glob('*')) if x.is_file() and x.suffix.lower() in extensions)
            elif p.suffix.lower() in extensions:expanded.append(str(p))
        expanded=sorted(set(expanded))
        if not expanded:self.notify_error('没有找到支持的媒体文件。');return
        def done(result):
            if 'value' not in result:return
            value=result['value'];existing={a['id'] for a in self.assets[role]};self.assets[role].extend(a for a in value['assets'] if a['id'] not in existing);self.refresh_assets();self.save_session()
            if value['errors']:self.notify_error('以下素材未导入：\n'+'\n'.join(value['errors'][:12]))
            self.footer.setText(f'导入完成：{len(value["assets"])}条有效素材，相同内容自动去重。')
        self.start_work(lambda stop,notify:scan(expanded,role,stop,notify),done)
    def selected_assets(self,role):
        items=self.lists[role].selectedItems()
        if not items:raise ValueError('请先选中一条'+('前贴' if role=='a' else '素材')+'。')
        keys={i.data(Qt.ItemDataRole.UserRole) for i in items};return [a for a in self.assets[role] if a['id'] in keys]
    def selected(self,role):
        assets=self.selected_assets(role)
        if len(assets)>1:raise ValueError('此操作一次处理一条素材，请只选中一条。')
        return assets[0]
    def remove_assets(self,role):
        if self.busy():return
        selected={i.data(Qt.ItemDataRole.UserRole) for i in self.lists[role].selectedItems()};self.assets[role]=[a for a in self.assets[role] if a['id'] not in selected];self.refresh_assets();self.save_session()
    def play_source(self,role):
        try:
            current=self.lists[role].currentItem()
            if not current:raise ValueError('请先选中要播放的素材。')
            key=current.data(Qt.ItemDataRole.UserRole);a=next(a for a in self.assets[role] if a['id']==key)
            Player(a['path'],self).exec()
        except Exception as exc:self.notify_error(exc)
    def edit_intro(self):
        if self.busy():return
        try:assets=self.selected_assets('a');a=assets[0]
        except Exception as exc:self.notify_error(exc);return
        dialog=IntroSoundDialog(assets,self.settings(),self.overrides,self.assets['music'],len(self.assets['b']),self)
        if dialog.exec():
            self.apply_intro_overrides(assets,dialog.controls.value() if dialog.apply_sound.isChecked() else None,dialog.fixed.value() if dialog.apply_fixed.isChecked() else None,dialog.inherit.isChecked())
            self.refresh_assets();self.save_session()
    def apply_intro_overrides(self,assets,sound=None,fixed=None,inherit=False):
        for a in assets:
            override=self.overrides.setdefault(a['id'],{})
            if fixed is not None:override['fixed']=fixed
            if inherit:
                for key in list(override):
                    if key.startswith('a_'):override.pop(key)
            elif sound is not None:override.update(sound)
    def edit_subtitles(self):
        if self.busy():return
        try:a=self.selected('a')
        except Exception as exc:self.notify_error(exc);return
        override=self.overrides.get(a['id'],{});dialog=SubtitleDialog(a,self.settings(),override.get('subtitle_rows'),self)
        if dialog.exec():
            self.overrides.setdefault(a['id'],{})['subtitle_rows']=dialog.result_rows;self.subtitles.setChecked(True);self.refresh_assets();self.save_session()
    def pick_output(self):
        p=QFileDialog.getExistingDirectory(self,'选择成片保存位置',self.output.text())
        if p:self.output.setText(p);self.update_quick_summary();self.save_session()
    def pick_color(self):
        c=QColorDialog.getColor(QColor(self.font_color.text()),self)
        if c.isValid():self.font_color.setText(c.name().upper())
    def api_dialog(self):
        d=QDialog(self);d.setWindowTitle('可选语言模型接口');l=QVBoxLayout(d);f=QFormLayout();l.addLayout(f)
        endpoint=QLineEdit(self.api_config.get('endpoint','https://api.openai.com/v1'));model=QLineEdit(self.api_config.get('model',''));key=QLineEdit(self.api_key);key.setEchoMode(QLineEdit.EchoMode.Password);enabled=QCheckBox('点击“理解规则”时使用在线模型');enabled.setChecked(self.api_config.get('enabled',False))
        f.addRow('接口根地址（含 /v1）',endpoint);f.addRow('模型名称',model);f.addRow('API Key（仅本次会话）',key);f.addRow(enabled)
        note=QLabel('仅发送组合指令文字，不发送视频、音频或文件路径。调用费用由所选服务产生；不配置接口也可用离线规则和表单。密钥不保存到磁盘。');note.setWordWrap(True);l.addWidget(note)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);bb.accepted.connect(d.accept);bb.rejected.connect(d.reject);l.addWidget(bb)
        if d.exec():self.api_config=dict(endpoint=endpoint.text().strip(),model=model.text().strip(),enabled=enabled.isChecked());self.api_key=key.text().strip();self.save_session()
    def apply_rules(self,rules):
        if not 1<=rules['count']<=100000:raise ValueError('数量须在1～100000之间。')
        self.quantity.setValue(rules['count']);set_combo(self.mode,rules['mode'])
        for a in self.assets['a']:self.overrides.setdefault(a['id'],{})['fixed']=-1
        for index,n in rules['fixed'].items():self.overrides[self.assets['a'][int(index)]['id']]['fixed']=n
        self.refresh_assets();self.rule_hint.setText('规则已填入表单与前贴次数；请生成计划检查实际分配。');self.save_session()
    def parse_text(self):
        if self.busy():return
        text=self.instruction.text();n=len(self.assets['a'])
        if self.api_config.get('enabled'):
            if not self.api_config.get('model') or not self.api_key:self.notify_error('请先填写模型和本次会话密钥。');return
            config=self.api_config.copy();key=self.api_key
            def done(r):
                if 'value' in r:
                    try:self.apply_rules(r['value'])
                    except Exception as exc:self.notify_error(exc)
            self.start_work(lambda stop,notify:api_rules(text,n,config['endpoint'],config['model'],key),done)
        else:
            try:self.apply_rules(parse_instruction(text,n))
            except Exception as exc:self.notify_error(exc)
    def fixed(self):return {a['id']:self.overrides[a['id']]['fixed'] for a in self.assets['a'] if self.overrides.get(a['id'],{}).get('fixed',-1)>=0}
    def materialize(self,pairs,s):
        rng=random.Random(s['seed']);musics=self.assets['music'];am={a['id']:copy.deepcopy(a) for role in self.assets.values() for a in role};settings=[];by_a={}
        for a,b in pairs:
            job=copy.deepcopy(s);override=self.overrides.get(a,{})
            job.update({k:v for k,v in override.items() if k!='fixed'});media_ids={}
            for side in ['a','b']:
                mode=job.get(side+'_music_mode','none')
                if mode=='none':job[side+'_music']=''
                elif mode in ('random_a','random_job'):
                    if not musics:raise ValueError('随机音乐需要先添加音乐库。')
                    if mode=='random_a':
                        if a not in by_a:by_a[a]=rng.choice(musics)['path']
                        job[side+'_music']=by_a[a]
                    else:job[side+'_music']=rng.choice(musics)['path']
                elif mode=='one' and not job[side+'_music']:raise ValueError('指定音乐模式需要选择一首音乐。')
                for field in [side+'_music',side+'_voice']:
                    p=job.get(field,'')
                    if not p or field.endswith('_voice') and job[side+'_sound']!='external':continue
                    existing=next((key for key,asset in am.items() if asset['path']==p),None)
                    if not existing:
                        asset=scan([p],'music')['assets']
                        if not asset:raise ValueError('无法读取独立声音文件：'+p)
                        item=asset[0];existing=item['id'];am[existing]=item
                    media_ids[field]=existing
                if job[side+'_sound']=='external' and not job.get(side+'_voice'):raise ValueError('独立声音模式需要指定口播/音效文件。')
            job.update(media_ids=media_ids,dependency_ids=list(set(media_ids.values())));settings.append(job)
        used=set(x for p in pairs for x in p)|{x for j in settings for x in j['dependency_ids']}
        return {k:v for k,v in am.items() if k in used},settings
    def generate_plan(self):
        if self.busy():return
        try:
            s=self.settings()
            if not self.game.text().strip():raise ValueError('请填写游戏名称。')
            if not s['output']:raise ValueError('请选择成片保存位置。')
            if not __import__('re').fullmatch('#[0-9a-fA-F]{6}',s['font_color']):raise ValueError('字幕颜色请使用 #FFFFFF 这样的格式。')
            pairs=make_plan([a['id'] for a in self.assets['a']],[a['id'] for a in self.assets['b']],self.quantity.value(),self.mode.currentData(),self.fixed(),self.store.excluded(self.game.text().strip()),self.seed.value())
            am,settings=self.materialize(pairs,s)
            self.plan,self.plan_assets,self.plan_settings=pairs,am,settings;self.plan_base=s;self.plan_game=self.game.text().strip();self.plan_fixed=self.fixed();self.plan_mode=self.mode.currentData();self.plan_fingerprint=self.current_fingerprint();self.render_plan();self.save_session()
        except Exception as exc:self.notify_error(exc)
    def render_plan(self):
        self.plan_table.setRowCount(len(self.plan))
        for n,((a,b),s) in enumerate(zip(self.plan,self.plan_settings)):cells(self.plan_table,n,[n+1,self.plan_assets[a]['name'],self.plan_assets[b]['name'],Path(s['a_music']).name if s['a_music'] else '无',Path(s['b_music']).name if s['b_music'] else '无',s['transition']])
        ac,bc=Counter(a for a,b in self.plan),Counter(b for a,b in self.plan)
        self.plan_summary.setText(f'{len(self.plan)}条 · {len(set(self.plan))}个独立配对 · 前贴分配：'+ '，'.join(f'{n:02}用{ac[a["id"]]}次' for n,a in enumerate(self.assets['a'],1))+f' · 主视频使用{min([bc[x["id"]] for x in self.assets["b"]],default=0)}～{max(bc.values(),default=0)}次。计划已固定，改动整批设置后请重新生成。')
    def edit_pair(self,row,col):
        if self.busy() or col not in (1,2) or not self.plan:return
        try:self.check_current_plan()
        except Exception as exc:self.notify_error(exc);return
        role='a' if col==1 else 'b';options=self.assets[role];labels=[f'{n+1:03} · {a["name"]}' for n,a in enumerate(options)]
        text,ok=QInputDialog.getItem(self,'修改配对','选择素材',labels,0,False)
        if not ok:return
        key=options[labels.index(text)]['id'];old=self.plan[row];pair=(key,old[1]) if role=='a' else (old[0],key)
        proposed=self.plan.copy();proposed[row]=pair
        try:
            self.validate_plan(proposed);am,settings=self.materialize(proposed,self.plan_base);self.plan,self.plan_assets,self.plan_settings=proposed,am,settings;self.render_plan()
        except Exception as exc:self.notify_error(exc)
    def validate_plan(self,pairs=None):
        self.check_current_plan()
        pairs=self.plan if pairs is None else pairs
        if not pairs:raise ValueError('请先生成组合计划。')
        if len(set(pairs))!=len(pairs):raise ValueError('修改后出现重复配对。')
        if set(pairs)&self.store.excluded(self.plan_game):raise ValueError('配对已被历史或另一任务使用，请重新生成。')
        ac,bc=Counter(a for a,b in pairs),Counter(b for a,b in pairs)
        if any(ac[a]!=n for a,n in self.plan_fixed.items()):raise ValueError('修改后不满足已指定的前贴使用次数。')
        if self.plan_mode=='balanced':
            av=[ac[a['id']] for a in self.assets['a'] if a['id'] not in self.plan_fixed];bv=[bc[b['id']] for b in self.assets['b']]
            if av and max(av)-min(av)>1 or bv and max(bv)-min(bv)>1:raise ValueError('修改后不再严格均匀，请重新生成或使用随机计划。')
    def current_fingerprint(self):
        return json.dumps(dict(assets=self.assets,overrides=self.overrides,settings=self.settings(),game=self.game.text().strip(),quantity=self.quantity.value(),mode=self.mode.currentData()),sort_keys=True,ensure_ascii=False)
    def check_current_plan(self):
        if not self.plan:raise ValueError('请先生成组合计划。')
        if self.current_fingerprint()!=self.plan_fingerprint:raise ValueError('素材、声音、字幕或规则已修改，请重新生成计划后再预览或创建任务。已创建的任务仍保留原设置。')
    def preview(self):
        if self.busy():return
        try:
            self.check_current_plan()
            row=max(0,self.plan_table.currentRow());a,b=self.plan[row];s=copy.deepcopy(self.plan_settings[row]);am=copy.deepcopy(self.plan_assets)
            out=data_dir()/'previews'/(uuid.uuid4().hex+'.mp4')
            def work(stop,notify):
                for key in [a,b,*s['dependency_ids']]:
                    if identity(am[key]['path'])!=key:raise ValueError('素材内容改变，请重新导入并生成计划。')
                e=MediaEngine(stop,lambda t:notify(dict(type='log',text=t)))
                try:return str(e.render_pair(am[a]['path'],am[b]['path'],s,out))
                finally:e.close()
            def done(r):
                if 'value' in r:self.last_preview=r['value'];Player(self.last_preview,self).exec()
            self.start_work(work,done)
        except Exception as exc:self.notify_error(exc)
    def play_last(self):
        if self.last_preview and Path(self.last_preview).exists():Player(self.last_preview,self).exec()
        else:self.notify_error('请先生成一条成片预览。')
    def export_plan(self):
        try:
            if not self.plan:raise ValueError('请先生成计划。')
            p,_=QFileDialog.getSaveFileName(self,'导出计划','组合计划.csv','CSV (*.csv)')
            if p:self.table_csv(self.plan_table,p)
        except Exception as exc:self.notify_error(exc)
    def create_batch(self):
        if self.busy():return
        try:
            self.validate_plan();bid=self.store.create(self.plan_game,self.plan_assets,self.plan,self.plan_base,self.plan_settings,name=f'{len(self.plan)}条组合')
            self.bid=bid;self.refresh_batches();set_combo(self.batch_combo,bid);self.load_batch();self.tabs.setCurrentIndex(3);self.save_session()
        except Exception as exc:self.notify_error(exc)
    def refresh_batches(self):
        old=self.batch_combo.currentData();self.batch_combo.clear()
        for bid,game,created,name,total,complete in self.store.batches():self.batch_combo.addItem(time.strftime('%m-%d %H:%M',time.localtime(created))+f' · {game} · {complete}/{total} · {bid[:8]}',bid)
        if old:set_combo(self.batch_combo,old)
        self.refresh_history()
    @staticmethod
    def status_name(s):return dict(pending='待处理',running='处理中/上次中断',complete='完成',failed='失败',cancelled='已放弃')[s]
    def load_batch(self):
        if self.busy():return
        bid=self.batch_combo.currentData()
        if not bid:return
        self.bid=bid;batch=self.store.batch(bid);jobs=self.store.jobs(bid);self.jobs_table.setRowCount(len(jobs))
        for row,j in enumerate(jobs):cells(self.jobs_table,row,[j['number'],batch['assets'][j['a']]['name'],batch['assets'][j['b']]['name'],self.status_name(j['status']),j['output'],j['error']])
        counts=Counter(j['status'] for j in jobs);self.queue_status.setText(f'任务 {bid[:8]} · 完成{counts["complete"]}/{len(jobs)} · 失败{counts["failed"]} · 待处理{counts["pending"]+counts["running"]}')
        self.total_progress.setMaximum(max(1,len(jobs)));self.total_progress.setValue(counts['complete']);self.current_progress.setValue(0)
    def start_batch(self,retry=False):
        if self.busy():return
        if not self.bid:self.notify_error('请创建或载入一个导出任务。');return
        bid=self.bid
        def done(r):
            self.load_batch();self.refresh_batches()
            if 'value' in r:
                value=r['value'];self.log.appendPlainText(('已暂停' if value['paused'] else '本轮结束')+f' · {value["seconds"]}秒 · {value["counts"]}')
        self.start_work(lambda stop,notify:run_batch(bid,stop,notify,retry=retry),done)
    def pause(self):
        if self.busy():self.worker.stop.set();self.footer.setText('正在暂停：终止当前处理，已完成文件保留，当前条回到待处理。')
    def play_job(self,row,col):
        p=self.jobs_table.item(row,4).text()
        if p and Path(p).exists():Player(p,self).exec()
    def open_output(self):
        p=Path(self.output.text())
        if self.bid:p=Path(self.store.batch(self.bid)['settings']['output'])/('任务_'+self.bid[:8])
        p.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.resolve())))
    def relocate(self):
        if self.busy() or not self.bid:return
        batch=self.store.batch(self.bid);options=list(batch['assets']);labels=[batch['assets'][k]['name']+' · '+batch['assets'][k]['path'] for k in options]
        text,ok=QInputDialog.getItem(self,'重定位任务素材','只允许选择内容相同的原文件',labels,0,False)
        if not ok:return
        p,_=QFileDialog.getOpenFileName(self,'定位原文件')
        if p:
            try:self.store.relocate(self.bid,options[labels.index(text)],p);self.footer.setText('原文件路径已更新，可重试失败条目。')
            except Exception as exc:self.notify_error(exc)
    def abandon(self):
        if self.busy() or not self.bid:return
        if QMessageBox.question(self,'放弃未完成任务','完成文件与历史保留，未完成配对释放。放弃后此任务不能继续。')==QMessageBox.StandardButton.Yes:
            self.store.abandon(self.bid);self.load_batch();self.refresh_batches()
    def refresh_history(self):
        rows=self.store.history();self.history_summary.setText(f'本机成功配对 {len(rows)} 条 · 数据目录：{data_dir()}');self.history_table.setRowCount(len(rows))
        for n,(game,a,b,completed,output) in enumerate(rows):
            cells(self.history_table,n,[game,a[:12],b[:12],time.strftime('%Y-%m-%d %H:%M',time.localtime(completed)),output])
            self.history_table.item(n,0).setData(Qt.ItemDataRole.UserRole,(game,a,b,output))
    def preview_history(self,row,column=0):
        item=self.history_table.item(row,0)
        record=item.data(Qt.ItemDataRole.UserRole) if item else None
        output=record[3] if record else ''
        if not output or not Path(output).is_file():
            self.notify_error('历史记录对应的成片文件不存在，无法预览：'+str(output or '（空路径）'))
            return
        Player(output,self).exec()
    def delete_selected_history(self):
        if self.busy():
            self.notify_error('当前正在处理，请先暂停或等待结束。')
            return
        rows=sorted({index.row() for index in self.history_table.selectionModel().selectedRows()})
        if not rows:
            self.notify_error('请先选中要删除的历史记录。')
            return
        records=[]
        for row in rows:
            item=self.history_table.item(row,0)
            record=item.data(Qt.ItemDataRole.UserRole) if item else None
            if record:records.append(record[:3])
        if not records:return
        if QMessageBox.question(self,'删除历史记录',f'确定删除选中的 {len(records)} 条历史记录吗？\n只删除本机历史索引，不删除输出文件和源素材；删除后配对可以重新生成。')!=QMessageBox.StandardButton.Yes:
            return
        try:
            deleted=self.store.delete_histories(records)
            self.refresh_history()
            self.footer.setText(f'已删除 {deleted} 条历史记录；输出文件和源素材保留。请重新生成计划并创建新任务。')
        except Exception as exc:self.notify_error(exc)
    def backup(self):
        if self.busy():return
        p,_=QFileDialog.getSaveFileName(self,'备份任务与历史','混剪历史.sqlite3','数据库 (*.sqlite3)')
        if p:
            try:self.store.backup(p);self.footer.setText('备份已保存：'+p)
            except Exception as exc:self.notify_error(exc)
    def restore(self):
        if self.busy():return
        p,_=QFileDialog.getOpenFileName(self,'恢复任务与历史','','数据库 (*.sqlite3)')
        if p and QMessageBox.question(self,'恢复备份','恢复会替换本机任务和历史；当前数据库会先自动备份。继续吗？')==QMessageBox.StandardButton.Yes:
            try:self.store.restore(p);self.bid=None;self.jobs_table.setRowCount(0);self.refresh_batches();self.footer.setText('已恢复备份。')
            except Exception as exc:self.notify_error(exc)
    @staticmethod
    def table_csv(widget,path):
        import csv
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow([widget.horizontalHeaderItem(c).text() for c in range(widget.columnCount())])
            for r in range(widget.rowCount()):w.writerow([widget.item(r,c).text() if widget.item(r,c) else '' for c in range(widget.columnCount())])
    def export_history(self):
        p,_=QFileDialog.getSaveFileName(self,'导出历史','配对历史.csv','CSV (*.csv)')
        if p:self.table_csv(self.history_table,p)
    def clear_cache(self):
        if self.busy():self.notify_error('请先暂停当前处理。');return
        if QMessageBox.question(self,'清理处理缓存','删除处理片段、自动识别缓存和预览。保留云端下载素材、缩略图、历史、任务、手动校正字幕和源视频。下次导出会重新处理。继续吗？')==QMessageBox.StandardButton.Yes:
            try:
                before=cache_sizes(data_dir())['processing'];clear_processing_cache(data_dir());self.last_preview='';self.refresh_cache_size()
                self.footer.setText('已释放处理缓存 '+human_size(max(0,before-cache_sizes(data_dir())['processing'])))
            except Exception as exc:self.refresh_cache_size();self.notify_error(exc)
    def refresh_cache_size(self):
        sizes=cache_sizes(data_dir())
        self.cache_size_label.setText('可清理处理缓存：'+human_size(sizes['processing'])+' · 云端素材（保留）：'+human_size(sizes['cloud'])+' · 缩略图（保留）：'+human_size(sizes['thumbnails']))
    def help(self):
        d=QDialog(self);d.setWindowTitle('快速使用');d.resize(680,560);l=QVBoxLayout(d);text=QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText('① 导入前贴、主视频和音乐，填写游戏名称。相同内容自动去重。\n\n② 选择声音和字幕。默认保留原声；加新音乐会和原声音混合。想换掉旧音乐，选择“尝试去旧音乐”，先试听效果。主视频默认保留原声音。前贴可单独指定音乐、次数和校正字幕。\n\n③ 输入“生成1000条，均匀分配，前贴01用200次”，或直接填数量、规则。点击生成计划，再预览。20×500最多10000个配对；历史及未完成任务会占用配对。\n\n④ 固定计划创建任务，再点开始。计划和设置会保存在本机。暂停立即中断当前条，完成文件保留；重启可载入任务继续，失败可重试。素材移动后用“重定位”找回原文件。放弃释放未完成配对。\n\n⑤ 整个软件文件夹可复制给同事，不需要装Python。每台电脑历史独立。升级前备份data文件夹或数据库。源视频不包含在历史备份里。\n\n硬切最快，通常更能完整保留连接处口播。淡入淡出等转场会重叠并缩短成片。字幕与音乐分离的质量请在真实素材上检查。后台模式降低进程优先级并顺序导出，仍可能占用显卡和硬盘。\n\n在线AI接口是可选项；不配置也能使用。它只解析规则文字，不理解视频内容。密钥仅当前会话有效。')
        l.addWidget(text);l.addWidget(button('知道了',d.accept,True));d.exec()
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):
        if self.busy():return
        role,ok=QInputDialog.getItem(self,'导入拖入的素材','添加到哪个列表？',['A 前贴','B 主视频','音乐库'],0,False)
        if ok:self.import_paths({'A 前贴':'a','B 主视频':'b','音乐库':'music'}[role],[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
    def closeEvent(self,event):
        self.thumbnail_loader.shutdown()
        if self.busy():
            self.worker.completed.disconnect()
            self.worker.event.disconnect()
            self.worker.stop.set();self.footer.setText('正在停止处理并保存任务…');self.worker.wait()
        self.save_session();self.store.close();event.accept()


def launch(argv):
    app=QApplication(argv);app.setStyle('Fusion');apply_theme(app);app.setWindowIcon(QIcon(str(asset('ui/MontageStudio.ico'))))
    lock=QLockFile(str(data_dir()/'app.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None,'混剪工坊','软件已经运行，请回到已打开的窗口。');return 0
    window=MainWindow();window.show()
    if '--screenshot' in argv:
        i=argv.index('--screenshot');target=Path(argv[i+1]);target.parent.mkdir(parents=True,exist_ok=True)
        QTimer.singleShot(1000,lambda:window.grab().save(str(target)))
        QTimer.singleShot(1800,window.close)
    result=app.exec();lock.unlock();return result
