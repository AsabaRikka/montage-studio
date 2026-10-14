"""Virtualized native material gallery: explicit check states and additive selection."""
from PySide6.QtCore import Qt, QSize, QRect, QRectF, QItemSelectionModel, QItemSelection
from PySide6.QtGui import QColor, QPen, QFont, QPainter
from PySide6.QtWidgets import QListWidget, QAbstractItemView, QStyledItemDelegate, QStyle
from .theme import tokens, icon

NAME = int(Qt.ItemDataRole.UserRole) + 1
DETAIL = NAME + 1
EXTRA = NAME + 2
KIND = NAME + 3
ERROR = NAME + 4

class MaterialDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view); self.view = view

    def sizeHint(self, option, index):
        return self.view.gridSize()

    def paint(self, painter, option, index):
        t = tokens(self.view.dark); selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(5, 5, -5, -5)
        painter.setPen(QPen(QColor(t['ink'] if selected else t['line']), 1.5 if selected else 1))
        painter.setBrush(QColor(t['selected'] if selected else t['surface']))
        painter.drawRoundedRect(QRectF(r), 12, 12)
        check = QRect(r.left()+12, r.top()+12, 20, 20)
        painter.setPen(QPen(QColor(t['ink'] if selected else t['muted']), 1))
        painter.setBrush(QColor(t['accent'] if selected else t['surface']))
        painter.drawRoundedRect(QRectF(check), 4, 4)
        if selected:
            icon('check', t['on_accent']).paint(painter, check.adjusted(2,2,-2,-2))
        small = QFont(option.font); small.setPixelSize(11); painter.setFont(small)
        painter.setPen(QColor(t['muted']))
        painter.drawText(QRect(check.right()+8, check.top(), r.width()-52, 20), Qt.AlignmentFlag.AlignVCenter, '已选择' if selected else '选择素材')
        preview = QRect(r.left()+12, r.top()+42, r.width()-24, 116)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(t['preview']))
        painter.drawRoundedRect(QRectF(preview), 8, 8)
        material_icon = index.data(Qt.ItemDataRole.DecorationRole)
        if index.data(KIND) == 'music':
            icon('music', t['muted']).paint(painter, QRect(preview.center().x()-20, preview.center().y()-20,40,40))
        elif material_icon and not material_icon.isNull():
            pix = material_icon.pixmap(QSize(preview.width(), preview.height()))
            size=pix.size().scaled(preview.size(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRect(preview.center().x()-size.width()//2,preview.center().y()-size.height()//2,size.width(),size.height())
            painter.drawPixmap(target,pix,pix.rect())
        else:
            icon('video', t['muted']).paint(painter, QRect(preview.center().x()-16, preview.center().y()-22,32,32))
            painter.setPen(QColor(t['muted']))
            painter.drawText(preview.adjusted(0,60,0,0),Qt.AlignmentFlag.AlignCenter,'预览不可用' if index.data(ERROR) else '预览加载中')
        font = QFont(option.font); font.setPixelSize(12); font.setWeight(QFont.Weight.Medium)
        painter.setFont(font); painter.setPen(QColor(t['ink']))
        metrics = painter.fontMetrics(); name = index.data(NAME) or index.data(Qt.ItemDataRole.DisplayRole) or ''
        # Two genuinely measured lines; the full filename/path remains in the tooltip.
        cut = 0
        while cut < len(name) and metrics.horizontalAdvance(name[:cut+1]) <= preview.width(): cut += 1
        painter.drawText(QRect(preview.left(),preview.bottom()+10,preview.width(),18),name[:cut])
        painter.drawText(QRect(preview.left(),preview.bottom()+28,preview.width(),18),metrics.elidedText(name[cut:],Qt.TextElideMode.ElideRight,preview.width()))
        painter.setFont(small); painter.setPen(QColor(t['muted']))
        painter.drawText(QRect(preview.left(),r.bottom()-40,preview.width(),16),index.data(DETAIL) or '')
        painter.drawText(QRect(preview.left(),r.bottom()-22,preview.width(),16),painter.fontMetrics().elidedText(index.data(EXTRA) or '',Qt.TextElideMode.ElideRight,preview.width()))
        if hovered or option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor(t['muted']),1,Qt.PenStyle.DotLine));painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(r.adjusted(3,3,-3,-3)),9,9)
        painter.restore()

class MaterialGrid(QListWidget):
    def __init__(self, role, parent=None):
        super().__init__(parent); self.role=role; self.dark=False; self.syncing=False;self.anchor=-1
        self.setObjectName('assetGrid');self.setAccessibleName({'a':'前贴素材勾选网格','b':'主视频素材勾选网格','music':'音乐素材勾选网格'}[role])
        self.setViewMode(QListWidget.ViewMode.IconMode);self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(True);self.setResizeMode(QListWidget.ResizeMode.Adjust);self.setMovement(QListWidget.Movement.Static)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionRectVisible(False);self.setMouseTracking(True);self.setSpacing(0)
        self.setGridSize(QSize(164,254));self.setUniformItemSizes(True)
        self.setMinimumHeight(264)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(MaterialDelegate(self));self.itemSelectionChanged.connect(self.sync_checks)
        self.itemChanged.connect(self.check_changed)

    def sync_checks(self):
        if self.syncing:return
        self.syncing=True
        try:
            for n in range(self.count()):
                item=self.item(n);state=Qt.CheckState.Checked if item.isSelected() else Qt.CheckState.Unchecked
                if item.checkState()!=state:item.setCheckState(state)
        finally:self.syncing=False

    def check_changed(self,item):
        if not self.syncing:item.setSelected(item.checkState()==Qt.CheckState.Checked)

    def mousePressEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if event.button()==Qt.MouseButton.RightButton and self.role=='a':
            event.accept();return
        if event.button()==Qt.MouseButton.LeftButton and item and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
            self.anchor=self.row(item);item.setSelected(not item.isSelected());event.accept();return
        # Shift extends a range, but never asks the delegate to flip check state again.
        if event.button()==Qt.MouseButton.LeftButton and item:
            end=self.row(item);start=self.anchor if 0<=self.anchor<self.count() else end
            selection=QItemSelection(self.model().index(min(start,end),0),self.model().index(max(start,end),0))
            self.selectionModel().select(selection,QItemSelectionModel.SelectionFlag.Select)
            self.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
            event.accept();return
        if event.button()==Qt.MouseButton.LeftButton:event.accept();return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if item:
            self.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
            self.itemDoubleClicked.emit(item);event.accept();return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Space and self.currentItem():
            self.currentItem().setSelected(not self.currentItem().isSelected());event.accept();return
        super().keyPressEvent(event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        available=max(150,self.viewport().width()-12);columns=max(1,available//164)
        self.setGridSize(QSize(min(192,available//columns),254))

    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.count():
            painter=QPainter(self.viewport());t=tokens(self.dark);r=self.viewport().rect();center=r.center()
            icon('music' if self.role=='music' else 'video',t['muted']).paint(painter,QRect(center.x()-22,center.y()-75,44,44))
            painter.setPen(QColor(t['ink']));font=QFont(self.font());font.setPixelSize(16);painter.setFont(font)
            painter.drawText(r.adjusted(0,0,0,15),Qt.AlignmentFlag.AlignCenter,getattr(self,'empty_title',{'a':'添加你的 AI 前贴','b':'添加游戏主视频','music':'添加背景音乐'}[self.role]))
            painter.setFont(self.font());painter.setPen(QColor(t['muted']))
            painter.drawText(r.adjusted(0,50,0,50),Qt.AlignmentFlag.AlignCenter,getattr(self,'empty_hint','点击上方添加文件，或将素材拖入窗口'))
            painter.end()
