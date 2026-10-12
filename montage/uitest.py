"""Native interaction regression for thumbnails, bulk edits and wheel safety."""
import time
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QAbstractSpinBox, QCheckBox, QDialogButtonBox, QScrollArea
from PySide6.QtTest import QTest
from .runtime import write_json


def verify(folder):
    from .gui import MainWindow, STYLE
    from .selftest import fixtures
    from .service import scan
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    a,b,silent,music=fixtures(folder/'素材')
    window=MainWindow();errors=[];window.notify_error=lambda exc:errors.append(str(exc));window.show()
    checks=[]
    def wait(condition):
        end=time.monotonic()+30
        while not condition():
            if time.monotonic()>end:raise TimeoutError('界面验证超时')
            app.processEvents();QTest.qWait(25)
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)))
        write_json(folder/'界面改进验证.json',dict(passed=all(x['passed'] for x in checks),checks=checks))
    try:
        window.assets={'a':scan([a,b,silent],'a')['assets'],'b':scan([b,silent],'b')['assets'],'music':scan([music],'music')['assets']}
        window.overrides={};window.refresh_assets();QTest.qWait(100)
        def thumbnails():
            keys={x['id'] for role in ('a','b') for x in window.assets[role]}
            wait(lambda:keys <= window.thumbnail_icons.keys())
            for key in keys:assert window.thumbnail_loader.path(key).is_file()
            window.grab().save(str(folder/'缩略图与多选.png'))
            return dict(video_thumbnails=len(keys),background=True)
        check('后台真实视频缩略图',thumbnails)
        def empty_and_error():
            import copy
            from .gallery import ERROR
            saved=copy.deepcopy(window.assets);window.assets={role:[] for role in saved};window.refresh_assets();QTest.qWait(80)
            window.grab().save(str(folder/'空库引导.png'))
            window.assets=saved;window.refresh_assets();QTest.qWait(80)
            key=saved['a'][0]['id'];cached=window.thumbnail_icons.pop(key)
            window.thumbnail_ready(key,'','验证用取帧失败')
            assert window.lists['a'].item(0).data(ERROR)=='验证用取帧失败'
            window.grab().save(str(folder/'缩略图失败提示.png'))
            window.thumbnail_icons[key]=cached;window.refresh_assets();QTest.qWait(50)
            return dict(empty_guide=True,failure_inline=True,source_files_untouched=True)
        check('空库引导和缩略图失败状态',empty_and_error)
        def multi():
            w=window.lists['a'];w.clearSelection()
            # The visible check affordance is the primary selection path.
            first=w.item(0);first.setCheckState(Qt.CheckState.Checked)
            assert first.isSelected() and len(w.selectedItems())==1
            first.setCheckState(Qt.CheckState.Unchecked)
            assert not first.isSelected() and len(w.selectedItems())==0
            for n in (0,1):
                r=w.visualItemRect(w.item(n));QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,pos=r.topLeft()+QPoint(26,26))
            assert len(w.selectedItems())==2 and all(w.item(n).checkState()==Qt.CheckState.Checked for n in (0,1))
            r=w.visualItemRect(first);QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,pos=r.topLeft()+QPoint(26,26))
            assert len(w.selectedItems())==1 and not first.isSelected()
            w.setCurrentItem(first);QTest.keyClick(w,Qt.Key.Key_Space)
            assert not first.isSelected(),'空格应切换当前勾选'
            w.clearSelection()
            QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,pos=w.visualItemRect(w.item(0)).center())
            QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,pos=w.visualItemRect(w.item(1)).center())
            assert len(w.selectedItems())==2
            QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=w.visualItemRect(w.item(2)).center())
            assert len(w.selectedItems())==3
            w.selectAll();assert len(w.selectedItems())==3 and '已选 3' in window.counts['a'].text()
            window.refresh_assets();assert len(w.selectedItems())==3
            window.grab().save(str(folder/'缩略图与多选.png'))
            assert all(w.item(n).checkState()==Qt.CheckState.Checked for n in range(3))
            rects=[w.visualItemRect(w.item(n)) for n in range(3)]
            assert rects[0].top()==rects[1].top() and rects[0].left()!=rects[1].left()
            return dict(checkbox_click=True,additive_without_ctrl=True,checkbox_unchecked=True,space=True,ctrl=True,shift=True,select_all=True,selection_survives_refresh=True,columns=max(1,w.viewport().width()//w.gridSize().width()))
        check('鼠标Ctrl_Shift多选与全选',multi)
        def bulk():
            ids=[x['id'] for x in window.assets['a']]
            for n,key in enumerate(ids):window.overrides[key]={'fixed':n,'a_volume':.2+n*.1,'subtitle_rows':[dict(start=0,end=1,text=f'独立字幕{n}')]}
            before={key:dict(value) for key,value in window.overrides.items()}
            window.lists['a'].selectAll()
            def edit_dialog():
                dialog=app.activeModalWidget();assert dialog
                boxes=dialog.findChildren(QCheckBox)
                next(c for c in boxes if '下方声音' in c.text()).setChecked(False)
                next(c for c in boxes if '指定次数' in c.text()).setChecked(True)
                from .widgets import NoWheelSpinBox
                dialog.findChild(NoWheelSpinBox).setValue(1)
                dialog.grab().save(str(folder/'批量设置.png'))
                QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
            QTimer.singleShot(150,edit_dialog);window.edit_intro()
            for key in ids:
                assert window.overrides[key]['fixed']==1
                assert window.overrides[key]['a_volume']==before[key]['a_volume']
                assert window.overrides[key]['subtitle_rows']==before[key]['subtitle_rows']
            window.apply_intro_overrides(window.assets['a'],{'a_volume':.75})
            assert all(window.overrides[key]['a_volume']==.75 for key in ids)
            window.apply_intro_overrides(window.assets['a'],inherit=True)
            assert all('a_volume' not in window.overrides[key] and window.overrides[key]['subtitle_rows']==before[key]['subtitle_rows'] for key in ids)
            window.edit_subtitles();assert errors and '一次处理一条' in errors[-1];errors.clear()
            return dict(dialog_save=True,subtitles_preserved=True,unchanged_fields_preserved=True,multi_subtitle_guard=True)
        check('批量设置保存且保留各条字幕和未勾选项',bulk)
        def wheel():
            window.tabs.setCurrentIndex(1);QTest.qWait(100)
            controls=window.findChildren(QComboBox)+window.findChildren(QAbstractSpinBox)
            def send(widget,delta):
                local=QPointF(widget.rect().center());global_pos=QPointF(widget.mapToGlobal(widget.rect().center()))
                QApplication.sendEvent(widget,QWheelEvent(local,global_pos,QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False))
            for control in controls:
                original=control.currentIndex() if isinstance(control,QComboBox) else control.value()
                for focused in (False,True):
                    control.setFocus() if focused else control.clearFocus()
                    for delta in (-120,120):send(control,delta)
                assert (control.currentIndex() if isinstance(control,QComboBox) else control.value())==original,type(control).__name__
                if isinstance(control,QAbstractSpinBox) and control.lineEdit():
                    send(control.lineEdit(),-120);assert control.value()==original
            scroll=window.tabs.widget(1);assert isinstance(scroll,QScrollArea)
            bar=scroll.verticalScrollBar();bar.setValue(0);send(window.crf,-120);app.processEvents()
            assert bar.value()>0,'滚轮未交给页面滚动'
            old=window.crf.value();QTest.keyClick(window.crf,Qt.Key.Key_Up);assert window.crf.value()==old+1;window.crf.setValue(old)
            window.resolution.setFocus();QTest.keyClick(window.resolution,Qt.Key.Key_Down);assert window.resolution.currentIndex()==1;window.resolution.setCurrentIndex(0)
            window.grab().save(str(folder/'滚轮安全设置页.png'))
            return dict(controls=len(controls),focused_and_unfocused=True,editor_children=True,page_scroll=True,keyboard_still_works=True)
        check('下拉和数字禁止滚轮改值_页面仍滚动',wheel)
        def theme():
            assert not window.windowIcon().isNull()
            for dark,label in [(False,'浅色'),(True,'深色')]:
                window.set_theme(dark,save=False)
                assert window.dark==dark
                for n,b in enumerate(window.nav_buttons):
                    QTest.mouseClick(b,Qt.MouseButton.LeftButton);QTest.qWait(60)
                    assert window.tabs.currentIndex()==n and b.isChecked()
                    if n==1:window.tabs.widget(1).verticalScrollBar().setValue(0)
                    window.grab().save(str(folder/f'{label}_页面{n+1}.png'))
            window.tabs.setCurrentIndex(0);window.grab().save(str(folder/'深色界面.png'))
            window.set_theme(False,save=False);assert window.dark is False
            window.tabs.setCurrentIndex(1);QTest.qWait(50)
            old=window.crf.value()
            QTest.mouseClick(window.crf,Qt.MouseButton.LeftButton,pos=QPoint(window.crf.width()-10,8))
            assert window.crf.value()==old+1;window.crf.setValue(old)
            QTest.mouseClick(window.resolution,Qt.MouseButton.LeftButton,pos=QPoint(window.resolution.width()-12,window.resolution.height()//2))
            QTest.qWait(60);assert window.resolution.view().isVisible()
            QTest.keyClick(window.resolution,Qt.Key.Key_Escape)
            window.tabs.setCurrentIndex(0)
            return dict(light_pages=5,dark_pages=5,sidebar_navigation=True,logo=True,toggle_restores=True)
        check('浅色深色主题切换',theme)
        def gallery_scale():
            import copy,hashlib
            saved=copy.deepcopy(window.assets);base=saved['b'][0];base_icon=window.thumbnail_icons[base['id']]
            fake=[]
            for n in range(500):
                key=hashlib.sha256(f'ui-only-{n}'.encode()).hexdigest()
                fake.append(dict(base,id=key,name=f'{n+1:03}_游戏主视频_横向多列显示与长文件名.mp4'))
                window.thumbnail_icons[key]=base_icon
            window.assets['b']=fake;window.refresh_assets();window.material_tabs.setCurrentIndex(1);QTest.qWait(80)
            w=window.lists['b'];t=time.monotonic();w.selectAll()
            assert len(w.selectedItems())==500 and all(w.item(n).checkState()==Qt.CheckState.Checked for n in range(500))
            select_seconds=round(time.monotonic()-t,3)
            w.clearSelection();assert not w.selectedItems()
            w.scrollToItem(w.item(499));QTest.qWait(50)
            QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,pos=w.visualItemRect(w.item(499)).topLeft()+QPoint(26,26))
            assert w.item(499).isSelected();window.grab().save(str(folder/'500项网格.png'))
            sizes=[]
            for width,height in [(1040,720),(1280,880)]:
                window.resize(width,height);w.scrollToTop();QTest.qWait(100)
                first=w.visualItemRect(w.item(0));second=w.visualItemRect(w.item(1))
                assert first.top()==second.top() and first.left()!=second.left()
                assert w.horizontalScrollBar().maximum()==0
                sizes.append(dict(requested=[width,height],actual=[window.width(),window.height()],columns=w.viewport().width()//w.gridSize().width()))
                assert window.width()==width and window.height()==height,'窗口最小宽度被内部控件撑大'
                window.grab().save(str(folder/f'网格_{width}.png'))
            window.assets=saved;window.refresh_assets();window.material_tabs.setCurrentIndex(2);QTest.qWait(80)
            w=window.lists['music'];QTest.mouseClick(w.viewport(),Qt.MouseButton.LeftButton,pos=w.visualItemRect(w.item(0)).topLeft()+QPoint(26,26))
            assert w.item(0).checkState()==Qt.CheckState.Checked
            window.grab().save(str(folder/'音乐勾选.png'));w.clearSelection()
            window.material_tabs.setCurrentIndex(0);window.lists['a'].selectAll();QTest.qWait(80)
            window.grab().save(str(folder/'缩略图与多选.png'))
            return dict(items=500,ui_fixture_only=True,select_all_seconds=select_seconds,last_item_click=True,music_checkbox=True,sizes=sizes)
        check('500项网格_窗口缩放_音乐勾选',gallery_scale)
        def removal():
            window.tabs.setCurrentIndex(0);window.lists['b'].selectAll();window.remove_assets('b');assert not window.assets['b']
            window.lists['a'].clearSelection();assert '已选 0' in window.counts['a'].text()
            window.lists['a'].item(0).setSelected(True);window.lists['a'].item(1).setSelected(True);window.remove_assets('a')
            assert len(window.assets['a'])==1 and all(Path(p).exists() for p in (a,b,silent))
            key=window.assets['a'][0]['id'];window.close()
            reopened=MainWindow();reopened.show();QTest.qWait(100)
            try:
                assert len(reopened.assets['a'])==1 and key in reopened.thumbnail_icons
                assert reopened.overrides[key]['subtitle_rows']
            finally:reopened.close()
            return dict(batch_remove=True,originals_preserved=True,session_and_cached_thumbnail_reopened=True)
        check('批量移除_原片保留_重开缓存和校正仍在',removal)
    finally:
        if window.isVisible():window.close()
    return 0 if all(x['passed'] for x in checks) else 1
