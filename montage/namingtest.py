"""Focused offline acceptance against the actual executable, isolated data only."""
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QDialog, QComboBox
from PySide6.QtTest import QTest
from .runtime import data_dir, write_json
from . import __version__


def verify(folder):
    from .gui import MainWindow, set_combo, Player
    from .gallery import NAME
    from .service import scan
    from .selftest import fixtures
    from .core import Runner, probe
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    if not data_dir().resolve().is_relative_to(folder):raise ValueError('Requires isolated diagnostic data')
    started=time.monotonic();app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    a,b,_,_=fixtures(folder/'synthetic_media')
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a,b)}
    app.setQuitOnLastWindowClosed(False)
    w=MainWindow();w.resize(1040,720);w.show();QTest.qWait(100);errors=[];w.notify_error=lambda e:errors.append(str(e));checks=[];outputs=[]
    intro=scan([a],'a')['assets'][0];intro.update(name='不烧心 · 旧附件.mp4',cloud=dict(name='不烧心',filename='旧附件.mp4'))
    main=scan([b],'b')['assets'][0];main['name']='游戏广告.mp4'
    w.assets=dict(a=[intro],b=[main],music=[]);w.refresh_assets();w.output.setText(str(folder/'outputs'))
    w.lists['a'].selectAll();w.lists['b'].selectAll()
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception:
            import traceback
            checks.append(dict(name=name,passed=False,error=traceback.format_exc()))
    try:
        def rename():
            grid=w.lists['a'];item=grid.item(0);assert item.data(NAME)=='不烧心'
            selected=w.quick_ids('a');key=intro['id'];pos=grid.visualItemRect(item).center()
            seen=[]
            def enter():
                dialog=app.activeModalWidget();assert isinstance(dialog,QInputDialog)
                dialog.setTextValue('本机前贴名');dialog.accept();seen.append('rename')
            def choose():
                menu=app.activePopupWidget();assert isinstance(menu,QMenu)
                action=menu.actions()[0];QTimer.singleShot(80,enter)
                QTest.mouseClick(menu,Qt.MouseButton.LeftButton,pos=menu.actionGeometry(action).center())
            QTimer.singleShot(80,choose)
            event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,grid.viewport().mapToGlobal(pos))
            QApplication.sendEvent(grid.viewport(),event)
            assert seen==['rename'] and intro['custom_name']=='本机前贴名'
            assert w.quick_ids('a')==selected and grid.item(0).data(NAME)=='本机前贴名'
            assert not w.store.history() and intro['id']==key
            QTest.qWait(150);w.grab().save(str(folder/'a_custom_name.png'))
            return dict(description_only=True,context_menu_and_dialog=True,selection_and_identity_unchanged=True)
        check('Feishu description default and right-click local naming',rename)
        def settings():
            seen=[]
            def choose():
                dialog=app.activeModalWidget();assert isinstance(dialog,QDialog)
                combo=next(c for c in dialog.findChildren(QComboBox) if c.count()==3)
                set_combo(combo,'a_date_b');seen.append(True);dialog.reject()
            QTimer.singleShot(80,choose);w.quick_details()
            assert seen==[True] and w.settings()['naming_rule']=='a_date_b'
            w.tabs.setCurrentIndex(1);QTest.qWait(80);w.grab().save(str(folder/'naming_settings.png'))
            return dict(shared_rule_setting=True)
        check('one-click naming dialog shares advanced setting',settings)
        def exports():
            result=[]
            for rule,expected in [('b_a','游戏广告_不烧心.mp4'),('a_date_b','不烧心'+datetime.now().strftime('%m.%d')+'_游戏广告.mp4'),('custom_b','本机前贴名_游戏广告.mp4')]:
                w.game.setText('naming-'+rule);set_combo(w.naming_rule,rule);w.tabs.setCurrentIndex(0)
                QTest.qWait(100)
                QTest.mouseClick(w.quick_button,Qt.MouseButton.LeftButton)
                deadline=time.monotonic()+60
                while w.busy() and time.monotonic()<deadline:QTest.qWait(30)
                QTest.qWait(100);assert not w.busy() and not errors,errors
                jobs=w.store.jobs(w.bid);assert len(jobs)==1 and jobs[0]['status']=='complete',jobs
                path=Path(jobs[0]['output']);assert path.name==expected,(path.name,expected)
                info=probe(path);assert (info['width'],info['height'])==(720,1280)
                Runner().ffmpeg(['-i',path,'-f','null','-']);outputs.append(path)
                result.append(dict(rule=rule,output=str(path),full_decode=True,resolution=[info['width'],info['height']]))
            return result
        check('all three rules via actual one-click 720p export',exports)
        def advanced():
            w.quantity.setValue(1);w.game.setText('naming-advanced');w.generate_plan()
            assert w.plan and not errors,errors
            assert w.plan_base['naming_rule']=='custom_b'
            w.create_batch();assert not errors,errors
            bid=w.bid
            assert w.store.jobs(bid)[0]['settings']['output_name']=='本机前贴名_游戏广告.mp4'
            w.store.abandon(bid)
            return dict(advanced_plan_name_snapshot=True)
        check('advanced plan uses selected rule',advanced)
        def playback():
            from PySide6.QtMultimedia import QMediaPlayer
            dialog=Player(str(outputs[0]),w);frames=[];result={};timer=QTimer();deadline=time.monotonic()+10
            dialog.video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.toImage()) if f.isValid() else None)
            def poll():
                if frames and dialog.player.position()>300:
                    result.update(decoded=True,no_error=dialog.player.error()==QMediaPlayer.Error.NoError)
                    frames[-1].save(str(folder/'decoded_frame.png'));timer.stop();dialog.done(0)
                elif time.monotonic()>deadline:timer.stop();dialog.done(0)
            timer.timeout.connect(poll);timer.start(30);dialog.exec();timer.stop()
            assert result.get('no_error'),result
            return result
        check('real Qt video playback decoding',playback)
        def reopen():
            w.close();second=MainWindow()
            try:
                assert second.naming_rule.currentData()=='custom_b'
                assert second.assets['a'][0]['custom_name']=='本机前贴名' and len(second.store.history())==3
                assert second.lists['a'].item(0).data(NAME)=='本机前贴名'
                second.edit_intro_name(intro['id'],True)
                assert second.lists['a'].item(0).data(NAME)=='不烧心'
                assert len(second.store.history())==3 and second.assets['a'][0]['id']==intro['id']
                assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
            finally:second.close()
            return dict(custom_name_and_rule_persisted=True,reset_description=True,history_identity_sources_preserved=True)
        check('session reopening and reset without affecting history',reopen)
    finally:
        if w.isVisible():w.close()
    report=dict(version=__version__,passed=len(checks)==6 and all(c['passed'] for c in checks),checks=checks,seconds=round(time.monotonic()-started,2),data_directory=str(data_dir()),synthetic_media_only=True,network_used=False,manual_listening=False,physical_computers=1)
    if getattr(sys,'frozen',False):report['exe_sha256']=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    write_json(folder/'naming_verification.json',report);return 0 if report['passed'] else 1
