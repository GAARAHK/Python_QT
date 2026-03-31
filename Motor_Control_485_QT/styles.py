# -*- coding: gbk -*-
"""全局暗色工业风 QSS 样式表"""

DARK_QSS = """
/* ===================== 基础 ===================== */
QMainWindow, QDialog {
    background-color: #0C1020;
}
QWidget {
    background-color: #0C1020;
    color: #C8D6F0;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif;
    font-size: 13px;
}

/* ===================== 菜单栏 ===================== */
QMenuBar {
    background-color: #080C18;
    color: #C8D6F0;
    border-bottom: 1px solid #1A2A44;
    padding: 2px 4px;
    spacing: 4px;
}
QMenuBar::item { padding: 4px 12px; border-radius: 3px; }
QMenuBar::item:selected { background-color: #1A3060; color: #00CCEE; }
QMenu {
    background-color: #111827;
    border: 1px solid #1E3050;
    padding: 4px 0;
}
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background-color: #1A3060; color: #00CCEE; }
QMenu::separator { height: 1px; background: #1A2A44; margin: 3px 8px; }

/* ===================== 标签页 ===================== */
QTabWidget::pane {
    border: 1px solid #1A2A44;
    background-color: #0C1020;
}
QTabBar {
    background-color: #080C18;
}
QTabBar::tab {
    background-color: #080C18;
    color: #5A7090;
    border: 1px solid #1A2A44;
    border-bottom: none;
    padding: 9px 22px;
    margin-right: 2px;
    font-size: 13px;
    font-weight: 500;
    min-width: 90px;
}
QTabBar::tab:selected {
    background-color: #0C1020;
    color: #00CCEE;
    border-top: 2px solid #00AADD;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #10192E;
    color: #88BBDD;
}

/* ===================== GroupBox ===================== */
QGroupBox {
    background-color: #0E1628;
    border: 1px solid #1A2A44;
    border-radius: 5px;
    margin-top: 14px;
    padding-top: 6px;
    font-weight: bold;
    color: #00AADD;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    color: #00AADD;
    background-color: #0E1628;
    font-size: 13px;
}

/* ===================== 按钮 ===================== */
QPushButton {
    background-color: #0E1E3A;
    color: #88AACC;
    border: 1px solid #1E3A60;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #162A50;
    color: #00CCEE;
    border-color: #0088BB;
}
QPushButton:pressed {
    background-color: #080E20;
    border-color: #00AADD;
}
QPushButton:disabled {
    background-color: #080C18;
    color: #2A3A50;
    border-color: #101828;
}

/* ===================== 输入控件 ===================== */
QLineEdit, QTextEdit {
    background-color: #060A14;
    color: #C8D6F0;
    border: 1px solid #1A2A44;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #1A3060;
}
QLineEdit:focus, QTextEdit:focus { border-color: #0077AA; }
QLineEdit:read-only { color: #4A6080; background-color: #08101C; }

QComboBox {
    background-color: #060A14;
    color: #C8D6F0;
    border: 1px solid #1A2A44;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QComboBox:hover { border-color: #0077AA; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #5A7090;
}
QComboBox QAbstractItemView {
    background-color: #0E1628;
    color: #C8D6F0;
    border: 1px solid #1E3050;
    selection-background-color: #1A3060;
    outline: none;
}

QSpinBox, QDoubleSpinBox {
    background-color: #060A14;
    color: #C8D6F0;
    border: 1px solid #1A2A44;
    border-radius: 4px;
    padding: 4px 6px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #0077AA; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #0E1E3A;
    border: none;
    width: 18px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #5A7090;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #5A7090;
}

/* ===================== 表格 ===================== */
QTableWidget {
    background-color: #060A14;
    color: #C8D6F0;
    gridline-color: #141E30;
    border: 1px solid #1A2A44;
    selection-background-color: #1A3060;
    alternate-background-color: #0A0E1C;
}
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected { background-color: #1A3060; color: #00CCEE; }
QHeaderView::section {
    background-color: #0E1628;
    color: #00AADD;
    border: 1px solid #1A2A44;
    padding: 5px 8px;
    font-weight: bold;
}
QHeaderView::section:horizontal { border-bottom: 1px solid #0077AA; }

/* ===================== 滚动条 ===================== */
QScrollBar:vertical {
    background: #080C18;
    width: 7px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #1E3050;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #0077AA; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #080C18;
    height: 7px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: #1E3050;
    border-radius: 3px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #0077AA; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ===================== 状态栏 ===================== */
QStatusBar {
    background-color: #060A14;
    color: #5A7090;
    border-top: 1px solid #1A2A44;
    font-size: 12px;
    padding: 2px 8px;
}
QStatusBar::item { border: none; }

/* ===================== 弹窗 ===================== */
QMessageBox {
    background-color: #0E1628;
}
QMessageBox QLabel { color: #C8D6F0; }

/* ===================== 分割线 ===================== */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #1A2A44;
}

/* ===================== ScrollArea ===================== */
QScrollArea { border: none; }
QScrollArea > QWidget > QWidget { background-color: #0C1020; }
"""

# ── 专用按钮样式 ─────────────────────────────────────────────────────────

BTN_START = """
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #0D3D18, stop:1 #082410);
        color: #44EE66;
        border: 1px solid #186628;
        border-radius: 4px;
        font-weight: bold;
        font-size: 12px;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #165C22, stop:1 #0C3A16);
        border-color: #22AA44;
        color: #88FFAA;
    }
    QPushButton:disabled {
        background-color: #080C18;
        color: #1A3020;
        border-color: #0E1E14;
    }
"""

BTN_STOP = """
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #3D0D0D, stop:1 #240808);
        color: #EE4444;
        border: 1px solid #661818;
        border-radius: 4px;
        font-weight: bold;
        font-size: 12px;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #5C1616, stop:1 #3A0C0C);
        border-color: #AA2222;
        color: #FFAAAA;
    }
    QPushButton:disabled {
        background-color: #080C18;
        color: #301A1A;
        border-color: #1E0E0E;
    }
"""

BTN_PRIMARY = """
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #0D2850, stop:1 #081834);
        color: #00CCEE;
        border: 1px solid #1A4A7A;
        border-radius: 4px;
        font-size: 14px;
        font-weight: bold;
        padding: 7px 18px;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #153A6E, stop:1 #0C2450);
        border-color: #00AADD;
    }
    QPushButton:pressed {
        background-color: #060E22;
    }
"""

BTN_SERIAL_OPEN = """
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #0D3050, stop:1 #081E34);
        color: #22AAEE;
        border: 1px solid #1A4A6A;
        border-radius: 4px;
        font-weight: bold;
        padding: 5px 14px;
    }
    QPushButton:hover { border-color: #00AADD; color: #44CCFF; }
"""

BTN_SERIAL_CLOSE = """
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #3A1008, stop:1 #240A04);
        color: #CC4422;
        border: 1px solid #5A2210;
        border-radius: 4px;
        font-weight: bold;
        padding: 5px 14px;
    }
    QPushButton:hover { border-color: #AA3311; color: #EE6644; }
"""

NAV_BTN_QSS = """
    QPushButton {
        background: transparent;
        color: #4A6080;
        border: none;
        border-left: 3px solid transparent;
        padding: 0 0 0 16px;
        font-size: 13px;
        text-align: left;
    }
    QPushButton:hover {
        background: #0E1A2C;
        color: #88AACC;
        border-left-color: #1E3A60;
    }
    QPushButton:checked {
        background: #0E1A2C;
        color: #00CCEE;
        border-left-color: #00AADD;
        font-weight: bold;
    }
"""

ROW_HEADER_QSS = """
    QFrame {
        background-color: #0A1528;
        border: 1px solid #1E3050;
        border-radius: 4px;
    }
"""

CARD_INPUT_QSS = """
    QLineEdit {
        background:#050810;
        color:#7AAAC0;
        border:1px solid #162030;
        border-radius:3px;
        padding:0 5px;
        font-family:Consolas;
        font-size:9pt;
    }
    QLineEdit:focus { border-color:#0066AA; color:#9ACCDD; }
    QLineEdit:read-only { color:#2A4050; background:#030608; border-color:#0E1620; }
"""
