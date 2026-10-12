"""Controls that leave wheel gestures to the surrounding page."""
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QWheelEvent, QPainter, QColor
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QStyle

from .theme import tokens


def scroll_page(control, event):
    parent = control.parentWidget()
    while parent:
        if isinstance(parent, QAbstractScrollArea):
            viewport = parent.viewport()
            forwarded = QWheelEvent(QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                event.globalPosition(), event.pixelDelta(), event.angleDelta(), event.buttons(),
                event.modifiers(), event.phase(), event.inverted())
            QApplication.sendEvent(viewport, forwarded)
            event.accept()
            return
        parent = parent.parentWidget()
    event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        scroll_page(self, event)


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        scroll_page(self, event)


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        scroll_page(self, event)



class SeekSlider(QSlider):
    """Track clicks and drags seek directly; wheel gestures never skip video."""
    def __init__(self,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent)
        self.setAccessibleName('视频播放进度');self.setMinimumHeight(28)
    def at(self,event):
        return QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),
            round(event.position().x()-7),max(1,self.width()-14))
    def paintEvent(self,event):
        t=tokens(self.palette().window().color().lightness()<128)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(t['line']))
        y=self.height()/2;span=max(1,self.width()-14)
        x=7+QStyle.sliderPositionFromValue(self.minimum(),self.maximum(),self.sliderPosition(),span)
        painter.drawRoundedRect(QRectF(7,y-2,span,4),2,2)
        painter.setBrush(QColor(t['accent'] if self.isEnabled() else t['line']))
        painter.drawRoundedRect(QRectF(7,y-2,max(0,x-7),4),2,2)
        painter.drawEllipse(QRectF(x-7,y-7,14,14))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QColor(t['muted']))
            painter.drawEllipse(QRectF(x-10,y-10,20,20))
        painter.end()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.isEnabled():
            self.setSliderDown(True);self.setSliderPosition(self.at(event));event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.isSliderDown():self.setSliderPosition(self.at(event));event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setSliderPosition(self.at(event));self.setSliderDown(False);event.accept()
        else:super().mouseReleaseEvent(event)
    def wheelEvent(self,event):event.ignore()
