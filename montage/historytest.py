"""History interaction acceptance using only isolated generated media."""
import hashlib
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QMediaPlayer
from .runtime import write_json, data_dir


def verify(folder):
    from .gui import MainWindow, Player
    from .selftest import fixtures
    from .service import scan, SETTINGS, run_batch
    from .planner import make_plan
    from .core import Runner, probe
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    a,b,silent,_=fixtures(folder/'合成素材')
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
    window=MainWindow();window.show();errors=[];window.notify_error=lambda e:errors.append(str(e))
    assets=scan([a,b,silent],'a')['assets'];am={x['id']:x for x in assets};keys=[x['id'] for x in assets]
    pairs=[(keys[0],keys[1]),(keys[0],keys[2])];settings=dict(SETTINGS,resolution='360x640',subtitles=False,encoder='cpu',output=str(folder/'重新生成'))
    bid=window.store.create('历史测试',am,pairs,settings,[settings,settings])
    outputs=[]
    for n in (1,2):
        output=folder/f'已完成_{n}.mp4';output.write_bytes(a.read_bytes());outputs.append(output)
        window.store.update(bid,n,'complete',str(output))
    # Same content in another game must survive selected deletion.
    other=window.store.create('另一个游戏',am,[pairs[0]],settings,[settings]);window.store.update(other,1,'complete',str(outputs[0]))
    window.refresh_history();window.tabs.setCurrentIndex(4);checks=[]
    before_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a,b,silent,*outputs]}
    def row_for(game,pair):
        return next(r for r in range(window.history_table.rowCount()) if tuple(window.history_table.item(r,0).data(Qt.ItemDataRole.UserRole)[:3])==(game,*pair))
    def select(rows):
        window.history_table.clearSelection()
        for r in rows:
            window.history_table.selectionModel().select(window.history_table.model().index(r,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
    def check(name,func):
        try:checks.append(dict(name=name,passed=True,result=func()))
        except Exception as exc:checks.append(dict(name=name,passed=False,error=str(exc)))
        write_json(folder/'历史记录验证.json',dict(passed=all(c['passed'] for c in checks),checks=checks,synthetic_media_only=True,data_directory=str(data_dir()),
            exe_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() if getattr(sys,'frozen',False) else None))
    def confirm(answer):
        outcome=[]
        def respond():
            dialog=app.activeModalWidget()
            if isinstance(dialog,QMessageBox):
                outcome.append(dialog.text());QTest.mouseClick(dialog.button(answer),Qt.MouseButton.LeftButton)
            else:outcome.append('未打开确认框')
        QTimer.singleShot(150,respond)
        QTest.mouseClick(window.delete_history_button,Qt.MouseButton.LeftButton)
        assert outcome and '只删除本机历史索引' in outcome[0]
    try:
        def playback():
            row=row_for('历史测试',pairs[0]);window.history_table.scrollToItem(window.history_table.item(row,4));QTest.qWait(100)
            frames=[];result={};deadline=time.monotonic()+15;attached=False
            timer=QTimer()
            def poll():
                nonlocal attached
                dialog=app.activeModalWidget()
                if isinstance(dialog,Player):
                    if not attached:
                        dialog.video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.toImage()) if f.isValid() else None);attached=True
                    if frames and dialog.player.position()>300:
                        result.update(position_ms=dialog.player.position(),source=dialog.player.source().toLocalFile(),no_error=dialog.player.error()==QMediaPlayer.Error.NoError)
                        frames[-1].save(str(folder/'历史双击实际解码帧.png'));dialog.grab().save(str(folder/'历史播放器.png'));timer.stop();dialog.done(0)
                    elif time.monotonic()>deadline:timer.stop();dialog.done(0)
                elif time.monotonic()>deadline:timer.stop()
            timer.timeout.connect(poll);timer.start(25)
            rect=window.history_table.visualItemRect(window.history_table.item(row,4))
            QTest.mouseClick(window.history_table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
            QTest.mouseDClick(window.history_table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
            timer.stop()
            assert attached and frames and result.get('no_error'),result
            assert Path(result['source'])==outputs[0]
            window.grab().save(str(folder/'历史页浅色.png'))
            return dict(result,double_click_real_dialog=True,decoded=True)
        check('真实双击预览与视频解码',playback)
        def missing_and_cancel():
            row=row_for('历史测试',pairs[1]);original=outputs[1];moved=original.with_suffix('.temporarily-moved')
            original.rename(moved)
            try:window.preview_history(row,4);assert errors and '不存在' in errors[-1];errors.clear()
            finally:moved.rename(original)
            select([row]);confirm(QMessageBox.StandardButton.No)
            assert len(window.store.history())==3 and window.store.excluded('历史测试')==set(pairs)
            return dict(missing_file_prompt=True,cancel_keeps_history=True)
        check('文件缺失提示与取消删除',missing_and_cancel)
        def delete_one():
            select([row_for('历史测试',pairs[0])]);confirm(QMessageBox.StandardButton.Yes)
            assert window.history_table.rowCount()==2
            assert window.store.excluded('历史测试')=={pairs[1]}
            assert window.store.excluded('另一个游戏')=={pairs[0]}
            assert all(j['status']=='complete' for j in window.store.jobs(bid))
            return dict(selected_only=True,other_game_preserved=True,completed_jobs_preserved=True)
        check('指定删除仅释放所选配对',delete_one)
        def regenerate():
            plan=make_plan([keys[0]],keys[1:],1,excluded=window.store.excluded('历史测试'))
            assert plan==[pairs[0]]
            replacement=window.store.create('历史测试',am,plan,settings,[settings])
            result=run_batch(replacement,folder=data_dir());assert result['counts']=={'complete':1},result
            generated=Path(window.store.jobs(replacement)[0]['output']);info=probe(generated)
            Runner().ffmpeg(['-i',generated,'-f','null','-'])
            assert generated not in outputs and info['duration']>3.5
            window.refresh_history()
            return dict(new_task=replacement,new_output=str(generated),full_decode=True,duration=info['duration'])
        check('删除后同配对重新规划并实际导出',regenerate)
        def bulk_and_reopen():
            select([row_for('历史测试',p) for p in pairs]);confirm(QMessageBox.StandardButton.Yes)
            assert window.store.excluded('历史测试')==set() and len(window.store.history())==1
            assert {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a,b,silent,*outputs]}==before_files
            window.set_theme(True,save=False);window.grab().save(str(folder/'历史页深色.png'));window.close()
            reopened=MainWindow();reopened.show()
            try:
                assert reopened.store.excluded('历史测试')==set()
                assert reopened.history_table.rowCount()==1
                assert reopened.store.jobs(bid)[0]['status']=='complete'
            finally:reopened.close()
            return dict(multi_select_delete=True,output_and_sources_unchanged=True,reopen_persisted=True)
        check('多选删除_原片成片保留_重开持久化',bulk_and_reopen)
    finally:
        if window.isVisible():window.close()
        app.processEvents()
    return 0 if len(checks)==5 and all(c['passed'] for c in checks) else 1
