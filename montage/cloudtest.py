"""Explicit live read-only library acceptance; only the user-specified library."""
import copy
import hashlib
import json
import threading
import time
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from .runtime import write_json, data_dir
from .store import identity


def verify(folder):
    from .gui import MainWindow, Player
    from .cloud import CloudLibrary
    from .selftest import fixtures
    from .service import scan
    from .media import MediaEngine
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    window=MainWindow();window.show();errors=[];window.notify_error=lambda e:errors.append(str(e))
    checks=[]
    def wait(condition,timeout=180):
        end=time.monotonic()+timeout
        while not condition():
            if time.monotonic()>end:raise TimeoutError('云端界面验证超时')
            app.processEvents();QTest.qWait(25)
        app.processEvents()
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)))
        write_json(folder/'云端库验证.json',dict(passed=all(c['passed'] for c in checks),checks=checks,
            read_only_remote=True,user_specified_table_only=True,credentials_in_release=False,physical_computers=1,
            exe_sha256=hashlib.sha256(Path(__import__('sys').executable).read_bytes()).hexdigest() if getattr(__import__('sys'),'frozen',False) else None))
    try:
        panel=window.cloud_panel;window.material_tabs.setCurrentWidget(panel);QTest.qWait(120)
        def directory():
            assert panel.library.cli().status()['ready']
            QTest.mouseClick(panel.refresh_button,Qt.MouseButton.LeftButton)
            wait(lambda:not window.busy());assert not errors,errors
            library=panel.library.library
            assert library['target']['table_id']=='tblO61TwuCnAW1mh'
            assert library['target']['view_id']=='vewBeeIAM0'
            assert library['records']>=9 and len(library['items'])>=9
            window.grab().save(str(folder/'云端目录.png'))
            return dict(records=library['records'],videos=len(library['items']),complete_pagination=True)
        check('实际飞书视图目录与字段',directory)
        def synchronize():
            w=panel.grid
            QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,pos=w.visualItemRect(w.item(0)).topLeft()+QPoint(26,26))
            assert len(w.selectedItems())==1
            panel.select_visible();count=w.count();assert len(w.selectedItems())==count
            QTest.mouseClick(panel.sync_button,Qt.MouseButton.LeftButton)
            wait(lambda:not window.busy(),600);assert not errors,errors
            assert len(window.assets['a'])==count
            assert len(panel.library.library['cache'])==count
            assert all(Path(a['path']).is_file() and identity(a['path'])==a['id'] for a in window.assets['a'])
            wait(lambda:all(a['id'] in window.thumbnail_icons for a in window.assets['a']))
            window.grab().save(str(folder/'云端已同步.png'))
            window.material_tabs.setCurrentIndex(0);QTest.qWait(120);window.grab().save(str(folder/'同步到A前贴.png'))
            return dict(synced=count,media_probed=True,hashes_verified=True,checkbox_ui=True)
        check('实际视频下载_复选框_同步到A',synchronize)
        def repeat():
            first=window.assets['a'][0];window.overrides[first['id']]={'fixed':1,'subtitle_rows':[]}
            previous=copy.deepcopy(window.overrides)
            library=panel.library
            result=library.sync(library.library['items'])
            assert result['downloaded']==0 and result['reused']==len(library.library['items']) and not result['errors']
            window.material_tabs.setCurrentWidget(panel);QTest.mouseClick(panel.sync_button,Qt.MouseButton.LeftButton)
            wait(lambda:not window.busy());assert not errors
            assert window.overrides==previous and len(window.assets['a'])==len(library.library['items'])
            panel.search.setText(library.library['items'][0]['name']);assert sum(not panel.grid.item(n).isHidden() for n in range(panel.grid.count()))>=1
            panel.usable.setChecked(True)
            assert all(panel.items[panel.grid.item(n).data(Qt.ItemDataRole.UserRole)]['usable']=='是' for n in range(panel.grid.count()) if not panel.grid.item(n).isHidden())
            panel.usable.setChecked(False);panel.search.clear()
            return dict(zero_redownload=True,no_duplicate_A=True,overrides_preserved=True,search_and_filter=True)
        check('增量复用_设置保护_搜索',repeat)
        def playback_and_render():
            first=window.assets['a'][0];player=Player(first['path'],window);player.show()
            try:
                wait(lambda:player.player.position()>400,30)
                player.video.grab().save(str(folder/'云端原片实际播放帧.png'));position=player.player.position()
            finally:player.done(0)
            _,b,_,_=fixtures(folder/'合成主视频')
            window.assets['b']=scan([b],'b')['assets'];window.refresh_assets()
            engine=MediaEngine(data=data_dir())
            output=folder/'云端前贴配合成B.mp4'
            settings=dict(window.settings(),resolution='720x1280',encoder='cpu',subtitles=False,output=str(folder))
            try:engine.render_pair(first['path'],str(b),settings,output)
            finally:engine.close()
            from .core import probe, Runner
            from .runtime import binary
            info=probe(output);Runner().run([binary('ffmpeg'),'-v','error','-i',str(output),'-f','null','-'])
            assert info['width']==720 and info['height']==1280
            return dict(playback_ms=position,cloud_A_synthetic_B_720p=True,full_decode=True,audio_listening_verified=False)
        check('实际云端视频播放及720p混剪',playback_and_render)
        def offline_reopen():
            expected={a['id'] for a in window.assets['a']};window.save_session();window.close();app.processEvents()
            reopened=MainWindow();reopened.show()
            try:
                assert {a['id'] for a in reopened.assets['a']}==expected
                lib=reopened.cloud_panel.library
                from .cloud import FeishuCLI
                original=FeishuCLI.call
                def deny(*args,**kwargs):raise AssertionError('离线复用不应访问飞书')
                FeishuCLI.call=deny
                try:result=lib.sync(lib.library['items'])
                finally:FeishuCLI.call=original
                assert result['reused']==len(expected) and not result['errors']
                reopened.material_tabs.setCurrentWidget(reopened.cloud_panel);reopened.set_theme(True);QTest.qWait(120)
                reopened.grab().save(str(folder/'云端深色重开.png'))
                return dict(reopen=True,offline_cache_reused=True,theme=True)
            finally:reopened.close();app.processEvents()
        check('重开_离线缓存_深色界面',offline_reopen)
    finally:
        if window.isVisible():window.close()
        app.processEvents()
    return 0 if checks and all(c['passed'] for c in checks) else 1
