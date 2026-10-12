"""Original Qt styling inspired by neutral desktop tools, not official Codex tokens."""
from functools import lru_cache
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette
from PySide6.QtSvg import QSvgRenderer
from .runtime import asset

LIGHT = dict(bg='#fafafa', side='#f3f3f3', surface='#ffffff', ink='#242424', muted='#666666',
             line='#dfdfdf', hover='#eeeeee', selected='#e8e8e8', accent='#242424', on_accent='#fafafa',
             preview='#f0f0f0', placeholder='#737373')
DARK = dict(bg='#212121', side='#191919', surface='#272727', ink='#ededed', muted='#b0b0b0',
            line='#505050', hover='#353535', selected='#424242', accent='#ededed', on_accent='#242424',
            preview='#303030', placeholder='#aaaaaa')

def tokens(dark=False):
    return DARK if dark else LIGHT

@lru_cache(maxsize=64)
def icon(name, color='#666666'):
    path = asset('ui/tabler') / (name + '.svg')
    if not path.is_file():
        return QIcon()
    svg = path.read_text(encoding='utf-8').replace('currentColor', color)
    renderer = QSvgRenderer(svg.encode())
    pixmap = QPixmap(48, 48); pixmap.fill(QColor('transparent'))
    painter = QPainter(pixmap); renderer.render(painter); painter.end()
    return QIcon(pixmap)

CSS = '''
QWidget { font-family: "Microsoft YaHei UI"; font-size: 13px; color: @ink; }
QMainWindow, QDialog { background: @bg; }
QWidget#sidebar { background: @side; border-right: 1px solid @line; }
QLabel[muted="true"] { color: @muted; }
QLabel#pageTitle { font-size: 22px; font-weight: 600; }
QLabel#brand { font-size: 18px; font-weight: 600; }
QLabel#pageDescription { color: @muted; }
QTabWidget::pane { background: @bg; border: none; }
QTabBar::tab { background: transparent; color: @muted; padding: 10px 18px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @ink; border-bottom: 2px solid @ink; }
QTabBar::tab:hover { background: @hover; }
QGroupBox { background: @surface; border: 1px solid @line; border-radius: 12px; margin-top: 18px; padding: 18px 12px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 6px; }
QPushButton { background: @surface; border: 1px solid @line; border-radius: 8px; padding: 8px 14px; }
QPushButton:hover { background: @hover; border-color: @muted; }
QPushButton:pressed { background: @selected; }
QPushButton:focus { border: 1px solid @ink; }
QPushButton:disabled { color: @muted; background: @side; border-color: @line; }
QPushButton[primary="true"] { background: @accent; color: @on_accent; border-color: @accent; font-weight: 600; }
QPushButton[primary="true"]:hover { background: @muted; border-color: @muted; }
QPushButton[nav="true"] { background: transparent; border: none; text-align: left; padding: 12px 14px; }
QPushButton[nav="true"]:hover { background: @hover; }
QPushButton[nav="true"]:checked { background: @selected; font-weight: 600; }
QPushButton[quiet="true"] { background: transparent; border-color: transparent; }
QPushButton[quiet="true"]:hover { background: @hover; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { background: @surface; border: 1px solid @line; border-radius: 8px; padding: 7px 9px; selection-background-color: @accent; selection-color: @on_accent; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus { border-color: @ink; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url("@down_path"); width: 14px; height: 14px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@up_path"); width: 12px; height: 12px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@down_path"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @surface; color: @ink; selection-background-color: @selected; selection-color: @ink; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid @muted; border-radius: 4px; background: @surface; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; image: url("@check_path"); }
QTableWidget, QListWidget { background: @surface; border: 1px solid @line; border-radius: 8px; gridline-color: @line; alternate-background-color: @bg; selection-background-color: @selected; selection-color: @ink; }
QListWidget#assetGrid { background: @bg; border: none; border-radius: 0; }
QHeaderView::section { background: @side; color: @muted; padding: 10px; border: none; border-bottom: 1px solid @line; }
QProgressBar { background: @hover; border: none; border-radius: 4px; text-align: center; color: @ink; min-height: 18px; }
QProgressBar::chunk { background: @muted; border-radius: 4px; }
QScrollArea { border: none; background: @bg; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @line; min-height: 30px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: @muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: @surface; color: @ink; border: 1px solid @line; padding: 6px; }
'''

def stylesheet(dark=False):
    result = CSS
    mode='dark' if dark else 'light'
    values = dict(tokens(dark), check_path=(asset('ui') / ('check-'+mode+'.svg')).as_posix(),
                  up_path=(asset('ui') / ('chevron-up-'+mode+'.svg')).as_posix(),
                  down_path=(asset('ui') / ('chevron-down-'+mode+'.svg')).as_posix())
    for key, value in values.items():
        result = result.replace('@' + key, value)
    return result

def apply(app, dark=False):
    t = tokens(dark); palette = QPalette()
    for role, key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.WindowText,'ink'),
                      (QPalette.ColorRole.Base,'surface'),(QPalette.ColorRole.AlternateBase,'bg'),
                      (QPalette.ColorRole.Text,'ink'),(QPalette.ColorRole.Button,'surface'),
                      (QPalette.ColorRole.ButtonText,'ink'),(QPalette.ColorRole.Highlight,'selected'),
                      (QPalette.ColorRole.HighlightedText,'ink'),(QPalette.ColorRole.PlaceholderText,'placeholder')]:
        palette.setColor(role, QColor(t[key]))
    app.setPalette(palette); app.setStyleSheet(stylesheet(dark))
