"""Native cloud-library panel with explicit refresh, selection and local sync."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDialog, QFormLayout, QDialogButtonBox, QListWidgetItem, QCheckBox)
from .cloud import CloudLibrary, FeishuCLI, DEFAULT_URL, READ_SCOPES
from .gallery import MaterialGrid, NAME, DETAIL, EXTRA, KIND


class CloudPanel(QWidget):
    def __init__(self, window):
        super().__init__(); self.window = window; self.pending = None; self.items = {}
        self.library = None
        layout = QVBoxLayout(self); layout.setContentsMargins(0,16,0,0); layout.setSpacing(10)
        row = QHBoxLayout(); self.url = QLineEdit(DEFAULT_URL); self.url.setAccessibleName('飞书前贴库链接')
        row.addWidget(self.url,1); self.connect_button = QPushButton('飞书连接'); self.connect_button.clicked.connect(self.connection)
        row.addWidget(self.connect_button); layout.addLayout(row)
        row = QHBoxLayout(); self.status = QLabel('首次使用请刷新目录，再勾选要同步的成品视频。'); self.status.setWordWrap(True); self.status.setProperty('muted', True)
        row.addWidget(self.status,1); self.refresh_button = QPushButton('刷新云端目录'); self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button); self.open_button = QPushButton('打开飞书表格'); self.open_button.clicked.connect(self.open_table); row.addWidget(self.open_button)
        layout.addLayout(row)
        filters = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText('搜索描述、文件名、备注或制作人')
        self.search.textChanged.connect(self.filter_items); filters.addWidget(self.search,1)
        self.usable = QCheckBox('仅看标记“是”'); self.usable.stateChanged.connect(self.filter_items); filters.addWidget(self.usable); layout.addLayout(filters)
        self.grid = MaterialGrid('a'); self.grid.setAccessibleName('云端前贴勾选网格'); layout.addWidget(self.grid,1)
        self.grid.empty_title='飞书云端前贴库'; self.grid.empty_hint='刷新云端目录，勾选视频后同步到 A 前贴'
        self.grid.itemSelectionChanged.connect(self.count_selection); self.grid.itemDoubleClicked.connect(self.play)
        row = QHBoxLayout(); self.select_button = QPushButton('全选当前结果'); self.select_button.clicked.connect(self.select_visible)
        row.addWidget(self.select_button); clear = QPushButton('取消选择'); clear.clicked.connect(self.grid.clearSelection); row.addWidget(clear)
        row.addStretch(); self.count = QLabel('0 条视频 · 已选 0 条'); row.addWidget(self.count)
        self.sync_button = QPushButton('同步选中到 A 前贴'); self.sync_button.setProperty('primary',True); self.sync_button.clicked.connect(self.sync)
        row.addWidget(self.sync_button); layout.addLayout(row)
        note = QLabel('只读取“成品文件”中的视频。已同步素材可离线使用；备注仅作提示，不自动改片。移出 A 前贴不会删除云端附件。')
        note.setWordWrap(True); note.setProperty('muted',True); layout.addWidget(note)
        window.thumbnail_loader.ready.connect(self.thumbnail_ready)
        try:
            self.library = CloudLibrary(); self.url.setText(self.library.config.get('url',DEFAULT_URL)); self.render()
        except Exception as exc:
            self.status.setText(str(exc)); self.refresh_button.setEnabled(False); self.connect_button.setEnabled(False)

    def open_table(self):
        try:
            self.save_link(); QDesktopServices.openUrl(QUrl(self.url.text().strip()))
        except Exception as exc: self.window.notify_error(exc)

    def save_link(self):
        self.library.save_config(self.url.text().strip(), self.library.config.get('profile',''))

    def start(self, func, done):
        if self.window.busy(): self.window.notify_error('正在处理，请先暂停或等处理结束。'); return False
        self.set_running(True)
        def complete(result):
            self.set_running(False)
            if 'error' in result: self.status.setText('操作失败；本地已有素材保留。可检查连接后重试。')
            if 'cancelled' in result: self.status.setText('已取消，已有下载保留。')
            done(result)
        return self.window.start_work(func, complete)

    def set_running(self, running):
        for widget in (self.refresh_button,self.sync_button,self.url,self.connect_button,self.select_button): widget.setEnabled(not running)
        if not running: self.count_selection()

    def refresh(self):
        try: self.save_link()
        except Exception as exc: self.window.notify_error(exc); return
        def done(result):
            if 'value' in result: self.render()
        self.start(lambda stop,notify:self.library.refresh(stop,notify),done)

    def render(self):
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.grid.selectedItems()}
        self.grid.clear(); self.items = {item['key']:item for item in self.library.library['items']}
        for key, record in self.items.items():
            cached = self.library.cached(record)
            item = QListWidgetItem(record['name']); item.setData(Qt.ItemDataRole.UserRole,key)
            item.setData(NAME,record['name']); item.setData(KIND,'a')
            item.setData(DETAIL,('已下载 · ' if cached else '云端 · ')+f'{record["size"]/1024/1024:.1f} MB')
            item.setData(EXTRA,record['creator']+' · '+record['date'])
            item.setToolTip(record['name']+'\n'+record['filename']+'\n备注：'+(record['note'] or '无')+'\n是否直接可用：'+(record['usable'] or '未标记'))
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Unchecked); self.grid.addItem(item)
            item.setSelected(key in selected)
            if cached:
                icon = self.window.thumbnail_icons.get(cached['id'])
                if not icon:
                    path=self.window.thumbnail_loader.path(cached['id'])
                    pixmap=QPixmap(str(path)) if path.exists() else QPixmap()
                    if not pixmap.isNull():
                        icon=QIcon(pixmap);self.window.thumbnail_icons[cached['id']]=icon
                if icon: item.setIcon(icon)
                else: self.window.thumbnail_loader.submit(cached)
            else:
                from .gallery import ERROR
                item.setData(ERROR,'未下载，同步后显示视频缩略图')
        catalog = self.library.library
        if catalog.get('refreshed'):
            self.status.setText(f'{catalog["target"].get("title","云端前贴库")} · {catalog.get("records",0)} 条记录 / {len(self.items)} 个视频 · 更新于 {catalog["refreshed"]}')
        self.filter_items(); self.grid.sync_checks()

    def thumbnail_ready(self, key, path, error):
        if not self.library or not path: return
        for index in range(self.grid.count()):
            item = self.grid.item(index); record = self.items.get(item.data(Qt.ItemDataRole.UserRole))
            cached = self.library.cached(record) if record else None
            if cached and cached['id']==key: item.setIcon(QIcon(path))

    def filter_items(self):
        query = self.search.text().strip().casefold()
        for index in range(self.grid.count()):
            item = self.grid.item(index); record = self.items[item.data(Qt.ItemDataRole.UserRole)]
            hide = (query and query not in ' '.join(str(v) for v in record.values()).casefold()) or (self.usable.isChecked() and record['usable']!='是')
            item.setHidden(bool(hide))
            if hide: item.setSelected(False)
        self.count_selection()

    def select_visible(self):
        for index in range(self.grid.count()):
            item = self.grid.item(index)
            if not item.isHidden(): item.setSelected(True)

    def count_selection(self):
        visible = sum(not self.grid.item(i).isHidden() for i in range(self.grid.count()))
        count = len(self.grid.selectedItems()); self.count.setText(f'{visible} 条视频 · 已选 {count} 条')
        self.sync_button.setEnabled(bool(count) and not self.window.busy())

    def sync(self):
        items = [self.items[item.data(Qt.ItemDataRole.UserRole)] for item in self.grid.selectedItems()]
        if not items: return
        def done(result):
            if 'value' not in result: return
            value = result['value']; existing = {item['id'] for item in self.window.assets['a']}
            added = [item for item in value['assets'] if item['id'] not in existing]
            # content identity remains the sole pairing key; cloud titles do not alter history.
            for item in added:
                if item['id'] not in existing: self.window.assets['a'].append(item); existing.add(item['id'])
            self.window.refresh_assets(); self.window.save_session(); self.render()
            self.status.setText(f'{"同步已暂停" if value["cancelled"] else "同步完成"}：新下载 {value["downloaded"]}、复用 {value["reused"]}、失败 {len(value["errors"])}；已加入 A 前贴。')
            if value['errors']: self.window.notify_error('\n'.join(value['errors'][:12]))
        self.start(lambda stop,notify:self.library.sync(items,stop,notify),done)

    def play(self, item):
        record = self.items[item.data(Qt.ItemDataRole.UserRole)]; cached = self.library.cached(record)
        if not cached: self.status.setText('请先勾选并同步，此后可双击离线播放。'); return
        from .gui import Player
        Player(cached['path'],self.window).exec()

    def connection(self):
        if self.window.busy(): self.window.notify_error('正在处理，请先暂停或等处理结束。'); return
        dialog = ConnectionDialog(self); dialog.exec()


class ConnectionDialog(QDialog):
    def __init__(self, panel):
        super().__init__(panel); self.panel=panel; self.pending=None; self.worker=None
        self.setWindowTitle('飞书连接'); self.resize(600,540)
        layout=QVBoxLayout(self)
        note=QLabel('本机已有飞书连接时可直接检查。新电脑需配置公司飞书应用并登录有此表权限的账号；软件包不含任何账号凭据。'); note.setWordWrap(True); layout.addWidget(note)
        form=QFormLayout(); self.profile=QLineEdit(panel.library.config.get('profile','')); self.profile.setPlaceholderText('留空使用本机现有默认连接')
        form.addRow('本机连接名称',self.profile); layout.addLayout(form)
        row=QHBoxLayout(); self.check=QPushButton('保存连接并检查'); self.check.clicked.connect(self.check_account); row.addWidget(self.check)
        self.login=QPushButton('登录 / 重新授权'); self.login.clicked.connect(self.begin_login); row.addWidget(self.login); layout.addLayout(row)
        self.status=QLabel('尚未检查'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.link=QLabel(); self.link.setWordWrap(True); self.link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction); self.link.setOpenExternalLinks(True); layout.addWidget(self.link)
        self.qr=QLabel(); self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.qr)
        self.finish=QPushButton('我已完成授权，继续连接'); self.finish.setEnabled(False); self.finish.clicked.connect(self.finish_login); layout.addWidget(self.finish)
        self.setup=QPushButton('新电脑：填写公司应用配置'); self.setup.clicked.connect(self.configure); layout.addWidget(self.setup)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close); close.rejected.connect(self.reject); layout.addWidget(close)

    def run(self,func,done):
        from .gui import Worker
        if self.worker and self.worker.isRunning(): return
        for widget in (self.check,self.login,self.finish,self.setup): widget.setEnabled(False)
        self.worker=Worker(func,self)
        def completed(result):
            self.worker.wait()
            for widget in (self.check,self.login,self.setup): widget.setEnabled(True)
            self.finish.setEnabled(bool(self.pending))
            if 'error' in result: self.status.setText(result['error'])
            if 'value' in result: done(result['value'])
        self.worker.completed.connect(completed); self.worker.start()

    def save(self):
        self.panel.library.save_config(self.panel.url.text().strip(),self.profile.text().strip())

    def check_account(self):
        try: self.save()
        except Exception as exc: self.status.setText(str(exc)); return
        self.run(lambda stop,notify:self.panel.library.cli().status(stop),self.show_status)

    def show_status(self,result):
        self.status.setText('已连接：'+result['name'] if result['ready'] else ('已配置应用，请登录授权。' if result['configured'] else '此电脑尚未配置飞书应用，请点击下方“新电脑”按钮。'))

    def begin_login(self):
        try: self.save()
        except Exception as exc: self.status.setText(str(exc)); return
        self.pending=None; self.qr.clear(); self.link.clear()
        def work(stop,notify):
            cli=self.panel.library.cli()
            result=cli.call(['auth','login','--scope',READ_SCOPES,'--no-wait','--json'],stop)
            data=result.get('data',result)
            url=data.get('verification_url') or data.get('verification_uri_complete')
            if not url or not data.get('device_code'): raise RuntimeError('没有取得授权链接，请检查公司应用配置。')
            cli.call(['auth','qrcode',url,'--output','authorization.png'],stop,require_json=False)
            return dict(url=url,device_code=data['device_code'],qr=str(cli.work/'authorization.png'))
        def done(result):
            import html
            self.pending=result['device_code']; self.link.setText('<a href="'+html.escape(result['url'],quote=True)+'">'+html.escape(result['url'])+'</a>')
            self.qr.setPixmap(QPixmap(result['qr']).scaled(210,210,Qt.AspectRatioMode.KeepAspectRatio)); Path(result['qr']).unlink(missing_ok=True)
            self.finish.setEnabled(True); self.status.setText('打开上方链接或扫描二维码完成授权，再点“我已完成授权”。')
        self.run(work,done)

    def finish_login(self):
        if not self.pending: return
        code=self.pending
        def work(stop,notify):
            cli=self.panel.library.cli(); cli.call(['auth','login','--device-code',code,'--json'],stop,timeout=180)
            return cli.status(stop)
        def done(result):
            self.pending=None; self.finish.setEnabled(False); self.qr.clear(); self.link.clear(); self.show_status(result)
        self.run(work,done)

    def configure(self):
        dialog=QDialog(self); dialog.setWindowTitle('配置本机公司应用'); layout=QVBoxLayout(dialog)
        note=QLabel('请向公司飞书管理员获取已开通多维表格读取、知识库读取及附件下载权限的应用配置。保存到独立的 montage-studio 连接，不修改现有默认连接。'); note.setWordWrap(True); layout.addWidget(note)
        form=QFormLayout(); app_id=QLineEdit(); secret=QLineEdit(); secret.setEchoMode(QLineEdit.EchoMode.Password); form.addRow('App ID',app_id); form.addRow('App Secret',secret); layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted: return
        identifier=app_id.text().strip(); value=secret.text().strip(); secret.clear()
        if not identifier or not value: self.status.setText('应用配置不能为空。'); return
        def work(stop,notify):
            cli=FeishuCLI(self.panel.library.folder)
            return cli.call(['config','init','--name','montage-studio','--app-id',identifier,'--app-secret-stdin','--brand','feishu'],stop,secret=value,require_json=False)
        def done(result):
            self.profile.setText('montage-studio'); self.save(); self.status.setText('应用配置已保存到本机，请点击“登录 / 重新授权”。')
        self.run(work,done)

    def done(self,result):
        if self.worker and self.worker.isRunning(): self.worker.stop.set(); self.worker.wait()
        self.pending=None; super().done(result)
