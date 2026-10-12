"""Controls that leave wheel gestures to the surrounding page."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QComboBox, QSpinBox, QDoubleSpinBox


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
