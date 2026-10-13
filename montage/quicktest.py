"""Targeted acceptance: real one-click exports and cache controls, synthetic media only."""
import hashlib
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer
from .runtime import data_dir, write_json
from . import __version__


def verify_layout(folder):
    """Offline layout acceptance, with synthetic cards and isolated data only."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap, QIcon, QColor
    from PySide6.QtWidgets import QListWidgetItem, QDialog, QLabel, QPushButton, QScrollArea
    from .gui import MainWindow
    from .gallery import NAME, DETAIL, EXTRA, KIND
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    if not data_dir().resolve().is_relative_to(folder):raise ValueError('Layout check requires isolated data inside report folder')
    started=time.monotonic();app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    w=MainWindow();w.show();checks=[]
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:
            import traceback
            checks.append(dict(name=name,passed=False,error=traceback.format_exc()))
    try:
        grids=[w.lists['a'],w.lists['b'],w.cloud_panel.grid]
        pix=QPixmap(140,116);pix.fill(QColor('#7e9bb3'))
        for grid in grids:
            for n in range(35):
                item=QListWidgetItem(f'合成布局示例 {n+1}');item.setData(Qt.ItemDataRole.UserRole,f'layout-{n}');item.setData(NAME,item.text())
                item.setData(DETAIL,'仅供布局验证');item.setData(EXTRA,'本机合成示例');item.setData(KIND,grid.role);item.setIcon(QIcon(pix));grid.addItem(item)
        w.cloud_panel.status.setText('免登录 · 合成布局目录 · 35 条示例（未访问飞书）')
        def sizes():
            result=[]
            for width,height in [(1536,824),(1040,720),(880,560)]:
                w.resize(width,height)
                for index,grid in [(0,grids[0]),(1,grids[1]),(3,grids[2])]:
                    w.material_tabs.setCurrentIndex(index);QTest.qWait(80)
                    assert grid.viewport().height()>=254,(width,height,index,grid.viewport().height())
                    grid.scrollToTop();item=grid.item(0);rect=grid.visualItemRect(item)
                    assert grid.viewport().rect().contains(rect),(rect,grid.viewport().rect())
                    QTest.mouseClick(grid.viewport(),Qt.MouseButton.LeftButton,pos=rect.topLeft()+QPoint(25,25))
                    assert item.isSelected() and item.checkState()==Qt.CheckState.Checked
                    QTest.mouseClick(grid.viewport(),Qt.MouseButton.LeftButton,pos=rect.topLeft()+QPoint(25,25));assert not item.isSelected()
                    grid.scrollToItem(grid.item(34));QTest.qWait(30);last=grid.visualItemRect(grid.item(34))
                    QTest.mouseClick(grid.viewport(),Qt.MouseButton.LeftButton,pos=last.topLeft()+QPoint(25,25));assert grid.item(34).isSelected()
                    grid.clearSelection();grid.scrollToTop()
                    result.append(dict(window=[w.width(),w.height()],tab=index,viewport_height=grid.viewport().height()))
                if width>=1040:w.grab().save(str(folder/f'cloud_{width}.png'))
            scroll=w.tabs.widget(0);assert isinstance(scroll,QScrollArea) and scroll.verticalScrollBar().maximum()>0
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum());QTest.qWait(50)
            assert scroll.viewport().rect().contains(w.quick_button.mapTo(scroll.viewport(),w.quick_button.rect().center()))
            w.grab().save(str(folder/'small_window_scrolled.png'));return result
        check('responsive grids, real mouse selection and small-window scrolling',sizes)
        def details():
            w.resize(1040,720);w.material_tabs.setCurrentIndex(3);w.tabs.widget(0).verticalScrollBar().setValue(0);QTest.qWait(50)
            p=w.cloud_panel;assert not p.url.isVisible();QTest.mouseClick(p.link_button,Qt.MouseButton.LeftButton);QTest.qWait(30)
            assert p.url.isVisible();QTest.mouseClick(p.link_button,Qt.MouseButton.LeftButton);assert not p.url.isVisible()
            seen=[]
            def inspect():
                d=app.activeModalWidget();seen.append(isinstance(d,QDialog) and any(w.output.text() in label.text() for label in d.findChildren(QLabel)) and any(b.text()=='更改保存位置' for b in d.findChildren(QPushButton)))
                d.reject()
            QTimer.singleShot(60,inspect);w.quick_details();assert seen==[True]
            w.set_theme(True);QTest.qWait(50);w.grab().save(str(folder/'cloud_dark.png'))
            return dict(link_toggle=True,output_settings_dialog=True,dark_theme=True)
        check('link disclosure and output/default settings access',details)
    finally:
        w.close();QTest.qWait(50)
    report=dict(version=__version__,passed=bool(checks) and all(c['passed'] for c in checks),checks=checks,seconds=round(time.monotonic()-started,2),data_directory=str(data_dir()),synthetic_cards_only=True,network_used=False)
    if getattr(sys,'frozen',False):report['exe_sha256']=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    write_json(folder/'layout_verification.json',report);return 0 if report['passed'] else 1


def verify(folder):
    from .gui import MainWindow, Player, set_combo
    from .selftest import fixtures
    from .service import scan
    from .core import Runner, probe
    from .workflow import cache_sizes
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    a,b,silent,music=fixtures(folder/'synthetic_media')
    source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a,b,silent,music)}
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    w=MainWindow();w.resize(1040,720);w.show();errors=[];w.notify_error=lambda e:errors.append(str(e))
    w.assets={'a':scan([a,silent],'a')['assets'],'b':scan([b],'b')['assets'],'music':[]}
    w.refresh_assets();w.output.setText(str(folder/'outputs'));w.game.setText('one-click test')
    checks=[];outputs=[]
    def wait_done():
        deadline=time.monotonic()+60
        while w.busy() and time.monotonic()<deadline:QTest.qWait(30)
        QTest.qWait(100)
        assert not w.busy() and not errors,errors
        jobs=w.store.jobs(w.bid);assert jobs and all(j['status']=='complete' for j in jobs),jobs
        for j in jobs:
            p=Path(j['output']);info=probe(p);assert (info['width'],info['height'])==(720,1280) and abs(info['duration']-4)<.15,info
            Runner().ffmpeg(['-i',p,'-f','null','-']);outputs.append(p)
        return jobs
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)))
    try:
        def guards():
            QTest.mouseClick(w.quick_button,Qt.MouseButton.LeftButton);assert errors and not w.store.batches();errors.clear()
            w.lists['a'].item(0).setSelected(True);w.lists['b'].selectAll();w.update_quick_summary()
            assert '最多 1 条' in w.quick_summary.text()
            set_combo(w.quick_mode,'count');w.quick_quantity.setValue(2);QTest.mouseClick(w.quick_button,Qt.MouseButton.LeftButton)
            assert errors and not w.store.batches();errors.clear()
            return dict(empty_selection_rejected=True,over_capacity_rejected=True)
        check('selection and quantity guards',guards)
        def specified():
            w.quick_quantity.setValue(1);set_combo(w.resolution,'360x640');w.subtitles.setChecked(True)
            w.overrides={w.assets['a'][0]['id']:dict(a_sound='mute',fixed=0)}
            QTest.mouseClick(w.quick_button,Qt.MouseButton.LeftButton);assert w.tabs.currentIndex()==3
            assert len(w.store.jobs(w.bid))==1;batch=w.store.batch(w.bid)
            assert batch['settings']['resolution']=='720x1280' and not batch['settings']['subtitles']
            assert batch['settings']['a_sound']=='original' and batch['settings']['transition']=='cut'
            jobs=wait_done();assert len(w.store.history())==1
            w.update_quick_summary();assert '最多 0 条' in w.quick_summary.text()
            w.lists['a'].selectAll();w.update_quick_summary();assert '最多 1 条' in w.quick_summary.text()
            w.tabs.setCurrentIndex(0);QTest.qWait(120);w.grab().save(str(folder/'one_click_light.png'))
            w.set_theme(True);QTest.qWait(100);w.grab().save(str(folder/'one_click_dark.png'));w.set_theme(False)
            assert w.resolution.currentData()=='360x640' and w.subtitles.isChecked() and w.overrides
            return dict(exported=1,defaults_used=True,advanced_settings_preserved=True,output=jobs[0]['output'])
        check('specified quantity real 720p export',specified)
        def maximum():
            w.tabs.setCurrentIndex(0);set_combo(w.quick_mode,'max');QTest.mouseClick(w.quick_button,Qt.MouseButton.LeftButton)
            jobs=wait_done();assert len(jobs)==1 and len(w.store.history())==2
            w.tabs.setCurrentIndex(0);QTest.mouseClick(w.quick_button,Qt.MouseButton.LeftButton);assert errors;errors.clear()
            assert len(w.store.batches())==2 and len(w.store.excluded('one-click test'))==2
            w.tabs.setCurrentIndex(3);w.grab().save(str(folder/'export_complete.png'))
            return dict(remaining_exported=1,no_repeat=True)
        check('maximum remaining real export and history exclusion',maximum)
        def cache():
            for name in ('cache','previews','frame_previews','cloud','thumbnails'):
                p=data_dir()/name/'quicktest_marker';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'keep' if name in ('cloud','thumbnails') else b'remove')
            before=cache_sizes(data_dir())['processing'];assert before>0
            preserved={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (*outputs,data_dir()/'session.json',data_dir()/'cloud/quicktest_marker',data_dir()/'thumbnails/quicktest_marker')}
            w.tabs.setCurrentIndex(4);w.refresh_cache_size();QTest.qWait(100);w.grab().save(str(folder/'cache_sizes.png'))
            original_busy=w.busy;w.busy=lambda:True;QTest.mouseClick(w.cache_button,Qt.MouseButton.LeftButton);assert errors;errors.clear();w.busy=original_busy
            def respond(answer):
                def click():
                    d=app.activeModalWidget();assert isinstance(d,QMessageBox);QTest.mouseClick(d.button(answer),Qt.MouseButton.LeftButton)
                QTimer.singleShot(100,click);QTest.mouseClick(w.cache_button,Qt.MouseButton.LeftButton)
            respond(QMessageBox.StandardButton.No);assert cache_sizes(data_dir())['processing']==before
            respond(QMessageBox.StandardButton.Yes);assert cache_sizes(data_dir())['processing']==0
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in preserved.items())
            assert len(w.store.history())==2 and len(w.store.batches())==2
            return dict(released_bytes=before,cancel_preserved=True,busy_rejected=True,cloud_sources_outputs_session_history_preserved=True)
        check('cache size and real cleanup controls',cache)
        def playback():
            d=Player(str(outputs[0]),w);frames=[];d.video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.toImage()) if f.isValid() else None)
            timer=QTimer();deadline=time.monotonic()+12;result={}
            def poll():
                if frames and d.player.position()>300:
                    result.update(position_ms=d.player.position(),no_error=d.player.error()==QMediaPlayer.Error.NoError)
                    frames[-1].save(str(folder/'decoded_frame.png'));timer.stop();d.done(0)
                elif time.monotonic()>deadline:timer.stop();d.done(0)
            timer.timeout.connect(poll);timer.start(30);d.exec();timer.stop()
            assert result.get('no_error') and frames,result
            return result
        check('output actual Qt video decoding',playback)
        def reopen():
            w.close();second=MainWindow()
            try:
                assert len(second.store.history())==2 and len(second.store.batches())==2
                assert len(second.assets['a'])==2 and second.output.text()==str(folder/'outputs')
                assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source_hashes.items())
            finally:second.close()
            return dict(session_tasks_history_retained=True,synthetic_sources_unchanged=True)
        check('isolated session reopening',reopen)
    finally:
        if w.isVisible():w.close()
    report=dict(version=__version__,passed=len(checks)==6 and all(c['passed'] for c in checks),checks=checks,seconds=round(time.monotonic()-started,2),data_directory=str(data_dir()),synthetic_media_only=True,manual_listening=False,physical_computers=1,exe_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() if getattr(sys,'frozen',False) else None)
    write_json(folder/'quick_verification.json',report)
    return 0 if report['passed'] else 1
