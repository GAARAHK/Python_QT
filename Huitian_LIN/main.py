#!/usr/bin/env python3
# -*- coding: gbk -*-
"""
汇天 LIN 上位机控制软件 v2.4
六页面：控制面板 / 串口设置 / 通信日志 / 测试记录 / 参数配置 / 关于
新增：SQLite 测试记录存储、查询页面、环形进度条
"""

import sys
import time
import sqlite3
import os
import math
import csv
from queue import Queue

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QDateTime, QSettings, QDate
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QFont, QPainter, QPen, QBrush

from qfluentwidgets import (
    FluentWindow, FluentIcon as FIF, NavigationItemPosition,
    PushButton, PrimaryPushButton, ComboBox, SpinBox,
    TextEdit, ProgressBar, ProgressRing,
    StrongBodyLabel, BodyLabel, CaptionLabel, SubtitleLabel, TitleLabel,
    CardWidget, InfoBar, InfoBarPosition,
    setTheme, setThemeColor, Theme, isDarkTheme,
    ToolButton, HorizontalSeparator,
    StateToolTip, SmoothScrollArea, SegmentedWidget,
    DatePicker, TableWidget,
)

import serial
import serial.tools.list_ports

# ─────────────────────────────────────────────
#  常量
# ─────────────────────────────────────────────
APP_VERSION         = "v2.4"
APP_NAME            = "汇天 LIN 上位机控制软件"
APP_AUTHOR          = "GAARAHK"

RESP_LEN            = 13
CMD_QUERY_STATUS    = bytes([0x02, 0x00, 0x06, 0x00, 0x02])
CMD_QUERY_VER       = bytes([0x02, 0x00, 0x08, 0x00, 0x02])
CMD_QUERY_INNER_VER = bytes([0x02, 0x00, 0x07, 0x00, 0x02])
CMD_UNFOLD          = bytes([0x02, 0x08, 0x25, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02])
CMD_FOLD            = bytes([0x02, 0x08, 0x25, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02])
CMD_ENABLE_LIN      = bytes([0x02, 0x08, 0x29, 0x43, 0x48, 0x49, 0x4E, 0x41, 0x48, 0x51, 0x00, 0x00, 0x02])
CMD_CALIBRATE       = bytes([0x02, 0x08, 0x24, 0x00, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02])
CMD_POWER_CYCLE     = bytes([0x02, 0x08, 0x24, 0x00, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02])

CALIB_POLL_MS    = 2000
CALIB_TIMEOUT_S  = 120
LOOP_POLL_MS     = 30000

RESP_CMD_STATUS    = 0x06
RESP_CMD_INNER_VER = 0x00
RESP_CMD_OUTER_VER = 0x08

_THEME_COLORS = [
    ("默认蓝",  "#0078d4"),
    ("天空蓝",  "#00b4d8"),
    ("薰衣草",  "#7c3aed"),
    ("玫瑰红",  "#e11d48"),
    ("珊瑚橙",  "#ea580c"),
    ("翡翠绿",  "#059669"),
    ("深青色",  "#0891b2"),
    ("金棕色",  "#b45309"),
]

# 数据库文件路径（与 main.py 同目录）
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_records.db")


def make_loop_cmd(count: int) -> bytes:
    count = max(1, min(255, count))
    return bytes([0x02, 0x08, 0x24, 0x00, 0x13, 0xB8, 0x0B, count, 0x00, 0x00, 0x00, 0x00, 0x02])


def to_hex(data: bytes) -> str:
    return ' '.join(f'{b:02X}' for b in data)


# ─────────────────────────────────────────────
#  SQLite 数据库层
# ─────────────────────────────────────────────
class TestDB:
    """SQLite 测试记录数据库。"""

    @staticmethod
    def _conn():
        return sqlite3.connect(_DB_PATH)

    @classmethod
    def init(cls):
        with cls._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS test_records (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    qr_code     TEXT    NOT NULL,
                    start_time  TEXT    NOT NULL,
                    end_time    TEXT    NOT NULL,
                    duration_s  REAL    NOT NULL,
                    loop_count  INTEGER NOT NULL,
                    result      TEXT    NOT NULL
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_qr ON test_records(qr_code)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_start ON test_records(start_time)")
            con.commit()

    @classmethod
    def insert(cls, qr_code, start_time, end_time, duration_s, loop_count, result):
        with cls._conn() as con:
            con.execute(
                "INSERT INTO test_records"
                "(qr_code,start_time,end_time,duration_s,loop_count,result) "
                "VALUES(?,?,?,?,?,?)",
                (qr_code, start_time, end_time, duration_s, loop_count, result)
            )
            con.commit()

    @classmethod
    def query(cls, qr_code="", date_from="", date_to=""):
        sql = ("SELECT id,qr_code,start_time,end_time,duration_s,loop_count,result "
               "FROM test_records WHERE 1=1")
        params = []
        if qr_code.strip():
            sql += " AND qr_code LIKE ?"
            params.append("%" + qr_code.strip() + "%")
        if date_from.strip():
            sql += " AND start_time >= ?"
            params.append(date_from.strip())
        if date_to.strip():
            sql += " AND start_time <= ?"
            params.append(date_to.strip() + " 23:59:59")
        sql += " ORDER BY start_time DESC LIMIT 500"
        with cls._conn() as con:
            cur = con.execute(sql, params)
            return cur.fetchall()

    @classmethod
    def delete_by_ids(cls, ids):
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        with cls._conn() as con:
            con.execute(
                "DELETE FROM test_records WHERE id IN (" + placeholders + ")",
                ids
            )
            con.commit()


# ─────────────────────────────────────────────
#  串口工作线程
# ─────────────────────────────────────────────
class SerialWorker(QThread):
    data_received  = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    port_opened    = pyqtSignal()

    def __init__(self, port, baudrate, parent=None):
        super().__init__(parent)
        self.port     = port
        self.baudrate = baudrate
        self._running = False
        self._serial  = None
        self._queue   = Queue()

    def send(self, data: bytes):
        if self._running:
            self._queue.put(data)

    def stop(self):
        self._running = False
        self.wait(3000)

    def run(self):
        try:
            self._serial = serial.Serial(
                port=self.port, baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, timeout=0.05,
            )
        except serial.SerialException as exc:
            self.error_occurred.emit(f"无法打开串口 {self.port}: {exc}")
            return

        self._running = True
        self.port_opened.emit()
        rx_buf = b""

        while self._running:
            while not self._queue.empty():
                try:
                    self._serial.write(self._queue.get_nowait())
                    self._serial.flush()
                except Exception as exc:
                    self.error_occurred.emit(f"发送错误: {exc}")
            waiting = self._serial.in_waiting
            if waiting:
                rx_buf += self._serial.read(waiting)
                rx_buf = self._parse_frames(rx_buf)
            else:
                self.msleep(10)

        if self._serial and self._serial.is_open:
            self._serial.close()

    def _parse_frames(self, buf: bytes) -> bytes:
        while len(buf) >= RESP_LEN:
            idx = buf.find(b'\x02')
            if idx == -1:
                return b""
            if idx > 0:
                buf = buf[idx:]
            if len(buf) < RESP_LEN:
                break
            candidate = buf[:RESP_LEN]
            if candidate[-1] == 0x02:
                self.data_received.emit(bytes(candidate))
                buf = buf[RESP_LEN:]
            else:
                buf = buf[1:]
        return buf


# ─────────────────────────────────────────────
#  全局日志总线
# ─────────────────────────────────────────────
class LogBus(QFrame):
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._log = TextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 10))
        lay.addWidget(self._log)

    _LOG_COLORS = {
        "tx":      "#3b82f6",
        "rx":      "#10b981",
        "error":   "#ef4444",
        "warning": "#f59e0b",
        "success": "#22c55e",
        "info":    None,
    }

    def append(self, msg: str, level: str = "info"):
        ts    = QDateTime.currentDateTime().toString("HH:mm:ss.zzz")
        color = self._LOG_COLORS.get(level)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        else:
            fmt.setForeground(self._log.palette().text().color())
        cursor.setCharFormat(fmt)
        cursor.insertText(f"[{ts}] {msg}\n")
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def clear(self):
        self._log.clear()


def log(msg: str, level: str = "info"):
    LogBus.instance().append(msg, level)


# ─────────────────────────────────────────────
#  公共控件
# ─────────────────────────────────────────────
def _sep():
    return HorizontalSeparator()


def _card(parent=None):
    return CardWidget(parent)


# ─────────────────────────────────────────────
#  全局配置（持久化）
# ─────────────────────────────────────────────
class AppConfig:
    """使用 QSettings 持久化存储用户参数。"""
    _ORG = "GAARAHK"
    _APP = "HuiTianLIN"
    _DEFAULTS = {
        "exp_outer_ver":   "",
        "exp_inner_ver":   "",
        "loop_count":      20,
        "unload_delay_ms": 350,
        "serial_port":     "",
        "serial_baud":     "115200",
        "theme":           "auto",
        "theme_color":     "#0078d4",
    }

    def __init__(self):
        self._qs = QSettings(self._ORG, self._APP)

    def get(self, key):
        default = self._DEFAULTS.get(key)
        v = self._qs.value(key, default)
        if isinstance(default, int):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default
        return v if v is not None else default

    def set(self, key, value):
        self._qs.setValue(key, value)
        self._qs.sync()


_APP_CFG = AppConfig()


# ─────────────────────────────────────────────
#  环形进度控件（自绘 + 旋转加载动画）
# ─────────────────────────────────────────────
class RingProgressWidget(QWidget):
    """可自定义颜色/文字的环形进度控件（0-100），支持旋转加载动画。"""

    def __init__(self, size=200, parent=None):
        super().__init__(parent)
        self._size      = size
        self._value     = 0
        self._text      = "0%"
        self._color     = QColor("#0078d4")
        self._animating = False
        self._angle     = 0
        self.setFixedSize(size, size)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_anim)

    def setAnimating(self, on: bool):
        self._animating = on
        if on:
            self._anim_timer.start(25)
        else:
            self._anim_timer.stop()
            self._angle = 0
        self.update()

    def _tick_anim(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def setValue(self, v: int):
        self._value = max(0, min(100, v))
        self._text  = f"{self._value}%"
        self.update()

    def setText(self, t: str):
        self._text = t
        self.update()

    def setRingColor(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen_w  = max(14, self._size // 8)
        margin = pen_w // 2 + 2
        rect   = self.rect().adjusted(margin, margin, -margin, -margin)

        # 背景轨道
        dark     = isDarkTheme()
        bg_color = QColor("#3a3d42") if dark else QColor("#e2e8f0")
        painter.setPen(QPen(bg_color, pen_w, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)

        # 前景圆弧（从12点钟顺时针）
        if self._value > 0:
            painter.setPen(QPen(self._color, pen_w, Qt.SolidLine, Qt.RoundCap))
            span = int(self._value * 360 / 100) * 16
            painter.drawArc(rect, 90 * 16, -span)

        # 旋转加载动画——内圈 8 个渐变小圆点
        if self._animating:
            cx      = self.rect().center().x()
            cy      = self.rect().center().y()
            inner_r = (rect.width() / 2) * 0.44
            dot_r   = max(3, self._size // 22)
            for i in range(8):
                a  = math.radians((self._angle + i * 45) % 360)
                dx = cx + inner_r * math.sin(a)
                dy = cy - inner_r * math.cos(a)
                alpha = int(35 + 220 * (i / 7))
                c = QColor(self._color)
                c.setAlpha(alpha)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(c))
                painter.drawEllipse(int(dx - dot_r), int(dy - dot_r),
                                    dot_r * 2, dot_r * 2)

        # 中心文字
        painter.setPen(self.palette().text().color())
        f = QFont()
        f.setPointSize(max(8, self._size // 12))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)


# ─────────────────────────────────────────────
#  二维码扫码输入框
# ─────────────────────────────────────────────
class QrScanInput(CardWidget):
    """工业扫码枪输入框，有文字变化即自动确认（200ms 防抖）。"""
    scanned = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 12, 20, 14)
        lay.setSpacing(8)

        t_row = QHBoxLayout()
        ico = ToolButton(FIF.QRCODE)
        ico.setEnabled(False)
        ico.setFixedSize(28, 28)
        t_row.addWidget(ico)
        t_row.addWidget(StrongBodyLabel("扫码录入（标定 / 循环开始前必须先扫码）"))
        t_row.addStretch()
        self._lbl_result = SubtitleLabel("等待扫码…")
        self._lbl_result.setStyleSheet("color: #718096;")
        t_row.addWidget(self._lbl_result)
        lay.addLayout(t_row)
        lay.addWidget(_sep())

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("点击此处→扫码枪扫描，无需按 Enter，扫完自动确认")
        f = QFont()
        f.setPointSize(13)
        self._edit.setFont(f)
        self._edit.setMinimumHeight(54)
        lay.addWidget(self._edit)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._commit)
        self._edit.textChanged.connect(self._on_changed)

    def _on_changed(self, text: str):
        if text.strip():
            self._debounce.start(200)

    def _commit(self):
        code = self._edit.text().strip()
        if code:
            self._lbl_result.setText(code)
            self._lbl_result.setStyleSheet("color: #22c55e; font-weight: bold;")
            self._edit.blockSignals(True)
            self._edit.clear()
            self._edit.blockSignals(False)
            self.scanned.emit(code)
            log(f"扫码录入: {code}", "success")

    def clear_code(self):
        self._lbl_result.setText("等待扫码…")
        self._lbl_result.setStyleSheet("color: #718096;")


# ═════════════════════════════════════════════
#  页面 1：控制面板
# ═════════════════════════════════════════════
class ControlPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlPage")
        self._worker        = None
        self._connected     = None
        self._calibrating   = False
        self._calib_start   = 0.0
        self._state_tooltip = None
        self._loop_running  = False
        self._loop_target   = 0
        self._qr_scanned    = False
        self._current_qr    = ""
        self._loop_start_dt = None   # QDateTime

        self._calib_timer = QTimer(self)
        self._calib_timer.timeout.connect(self._on_calib_poll)
        self._loop_timer = QTimer(self)
        self._loop_timer.timeout.connect(self._on_loop_poll)

        self._build()
        self._apply_connection_state(False)

    # ── 整体布局 ─────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 12)
        root.setSpacing(10)

        self._conn_banner = _card()
        bl = QHBoxLayout(self._conn_banner)
        bl.setContentsMargins(14, 7, 14, 7)
        hint = BodyLabel("?  当前未连接串口，请前往「串口设置」页面进行连接")
        hint.setStyleSheet("color: #d97706;")
        bl.addWidget(hint)
        root.addWidget(self._conn_banner)

        self._qr = QrScanInput()
        self._qr.scanned.connect(self._on_qr_scanned)
        root.addWidget(self._qr)

        main_row = QHBoxLayout()
        main_row.setSpacing(10)
        main_row.addWidget(self._build_calib_card(), 2)
        main_row.addWidget(self._build_loop_card(), 2)
        main_row.addWidget(self._build_action_card(), 1)
        root.addLayout(main_row)

        aux_row = QHBoxLayout()
        aux_row.setSpacing(10)
        aux_row.addWidget(self._build_version_card())
        aux_row.addWidget(self._build_motion_card())
        aux_row.addWidget(self._build_power_card())
        aux_row.addWidget(self._build_lin_card())
        root.addLayout(aux_row)

    # ── 标定卡片 ──────────────────────────────────
    def _build_calib_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(10)

        t = QHBoxLayout()
        ico = ToolButton(FIF.SETTING)
        ico.setEnabled(False)
        ico.setFixedSize(36, 36)
        t.addWidget(ico)
        t.addWidget(TitleLabel("标  定"))
        t.addStretch()
        self._lbl_calib_status = SubtitleLabel("待  机")
        self._lbl_calib_status.setStyleSheet("color: #718096;")
        t.addWidget(self._lbl_calib_status)
        lay.addLayout(t)
        lay.addWidget(_sep())

        # 弹性空间填充至环形上方
        lay.addStretch(1)

        # 环形进度（大尺寸居中，占据中间空白）
        ring_row = QHBoxLayout()
        ring_row.addStretch()
        self._ring_calib = RingProgressWidget(size=150)
        self._ring_calib.setRingColor(QColor("#0078d4"))
        ring_row.addWidget(self._ring_calib)
        ring_row.addStretch()
        lay.addLayout(ring_row)

        # 以下均与底部按钮固定间距
        self._calib_caption = BodyLabel("等待开始标定…")
        self._calib_caption.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._calib_caption)

        self._calib_bar = ProgressBar()
        self._calib_bar.setRange(0, CALIB_TIMEOUT_S)
        self._calib_bar.setValue(0)
        self._calib_bar.setFixedHeight(6)
        lay.addWidget(self._calib_bar)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._btn_calib_start = PrimaryPushButton(FIF.PLAY, "开始标定")
        self._btn_calib_start.setMinimumHeight(100)
        self._btn_calib_start.clicked.connect(self._start_calibration)
        btn_row.addWidget(self._btn_calib_start, 3)
        self._btn_calib_stop = PushButton(FIF.PAUSE, "停止标定")
        self._btn_calib_stop.setMinimumHeight(100)
        self._btn_calib_stop.clicked.connect(self._stop_calibration_action)
        btn_row.addWidget(self._btn_calib_stop, 2)
        lay.addLayout(btn_row)
        return card

    # ── 循环运行卡片 ───────────────────────────────
    def _build_loop_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(10)

        t = QHBoxLayout()
        ico = ToolButton(FIF.ROTATE)
        ico.setEnabled(False)
        ico.setFixedSize(36, 36)
        t.addWidget(ico)
        t.addWidget(TitleLabel("循环运行"))
        t.addStretch()
        self._lbl_loop_status = SubtitleLabel("待  机")
        self._lbl_loop_status.setStyleSheet("color: #718096;")
        t.addWidget(self._lbl_loop_status)
        lay.addLayout(t)
        lay.addWidget(_sep())

        cr = QHBoxLayout()
        cr.addWidget(BodyLabel("设定次数"))
        self._spin_loop = SpinBox()
        self._spin_loop.setRange(1, 255)
        self._spin_loop.setValue(_APP_CFG.get("loop_count"))
        self._spin_loop.setSuffix("  次")
        self._spin_loop.setFixedWidth(120)
        cr.addWidget(self._spin_loop)
        cr.addStretch()
        self._lbl_loop_cnt = SubtitleLabel("—  /  —")
        self._lbl_loop_cnt.setStyleSheet("color: #3b82f6; font-weight: bold;")
        cr.addWidget(self._lbl_loop_cnt)
        lay.addLayout(cr)

        # 弹性空间填充至环形上方
        lay.addStretch(1)

        # 环形进度（大尺寸居中，占据中间空白）
        ring_row = QHBoxLayout()
        ring_row.addStretch()
        self._ring_loop = RingProgressWidget(size=150)
        self._ring_loop.setRingColor(QColor("#059669"))
        ring_row.addWidget(self._ring_loop)
        ring_row.addStretch()
        lay.addLayout(ring_row)

        # 以下均与底部按钮固定间距
        self._loop_caption = BodyLabel("等待开始循环运行…")
        self._loop_caption.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._loop_caption)

        self._loop_bar = ProgressBar()
        self._loop_bar.setRange(0, 100)
        self._loop_bar.setValue(0)
        self._loop_bar.setFixedHeight(6)
        lay.addWidget(self._loop_bar)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._btn_loop_start = PrimaryPushButton(FIF.PLAY, "开始运行")
        self._btn_loop_start.setMinimumHeight(100)
        self._btn_loop_start.clicked.connect(self._start_loop)
        btn_row.addWidget(self._btn_loop_start, 3)
        self._btn_loop_stop = PushButton(FIF.PAUSE, "停止运行")
        self._btn_loop_stop.setMinimumHeight(100)
        self._btn_loop_stop.clicked.connect(self._stop_loop_action)
        btn_row.addWidget(self._btn_loop_stop, 2)
        lay.addLayout(btn_row)
        return card

    # ── 操作卡片 ──────────────────────────────────
    def _build_action_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)

        t = QHBoxLayout()
        ico = ToolButton(FIF.MOVE)
        ico.setEnabled(False)
        ico.setFixedSize(36, 36)
        t.addWidget(ico)
        t.addWidget(TitleLabel("操  作"))
        lay.addLayout(t)
        lay.addWidget(_sep())

        tip1 = CaptionLabel("下料：展开后延迟断电重启")
        tip1.setStyleSheet("color: #718096;")
        lay.addWidget(tip1)
        self._btn_unload = PrimaryPushButton(FIF.DOWN, "下  料")
        self._btn_unload.setMinimumHeight(100)
        self._btn_unload.clicked.connect(self._send_unload)
        lay.addWidget(self._btn_unload)

        lay.addSpacing(4)

        tip2 = CaptionLabel("回到原位：发送折叠命令")
        tip2.setStyleSheet("color: #718096;")
        lay.addWidget(tip2)
        self._btn_home = PushButton(FIF.UP, "回到原位")
        self._btn_home.setMinimumHeight(100)
        self._btn_home.clicked.connect(self._send_home)
        lay.addWidget(self._btn_home)

        lay.addSpacing(4)
        lay.addWidget(_sep())

        tip3 = CaptionLabel("直接发送断电重启（不启用LIN）")
        tip3.setStyleSheet("color: #ef4444;")
        lay.addWidget(tip3)
        self._btn_emergency = PushButton(FIF.POWER_BUTTON, "紧急停止")
        self._btn_emergency.setMinimumHeight(100)
        self._btn_emergency.setStyleSheet(
            "PushButton{background:#ef4444;color:white;border-radius:6px;border:none;}"
            "PushButton:hover{background:#dc2626;}"
            "PushButton:pressed{background:#b91c1c;}"
            "PushButton:disabled{background:#fca5a5;color:#fff;}"
        )
        self._btn_emergency.clicked.connect(self._send_emergency_stop)
        lay.addWidget(self._btn_emergency)

        lay.addStretch()
        return card

    # ── 辅助小卡片 ─────────────────────────────────
    def _build_version_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(7)
        t = QHBoxLayout()
        ico = ToolButton(FIF.INFO)
        ico.setEnabled(False)
        ico.setFixedSize(26, 26)
        t.addWidget(ico)
        t.addWidget(StrongBodyLabel("版本信息"))
        lay.addLayout(t)
        lay.addWidget(_sep())

        r1 = QHBoxLayout()
        r1.addWidget(CaptionLabel("外部版本"))
        r1.addStretch()
        self._lbl_ver_outer = BodyLabel("—")
        self._lbl_ver_outer.setStyleSheet("color: #3b82f6;")
        r1.addWidget(self._lbl_ver_outer)
        lay.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(CaptionLabel("内部版本"))
        r2.addStretch()
        self._lbl_ver_inner = BodyLabel("—")
        self._lbl_ver_inner.setStyleSheet("color: #3b82f6;")
        r2.addWidget(self._lbl_ver_inner)
        lay.addLayout(r2)

        lay.addWidget(_sep())
        br = QHBoxLayout()
        br.setSpacing(6)
        self._btn_ver_outer = PushButton(FIF.SEARCH, "外部版本")
        self._btn_ver_outer.clicked.connect(self._query_version_outer)
        br.addWidget(self._btn_ver_outer)
        self._btn_ver_inner = PushButton(FIF.CODE, "内部版本")
        self._btn_ver_inner.clicked.connect(self._query_version_inner)
        br.addWidget(self._btn_ver_inner)
        lay.addLayout(br)
        return card

    def _build_motion_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(7)
        t = QHBoxLayout()
        ico = ToolButton(FIF.ALIGNMENT)
        ico.setEnabled(False)
        ico.setFixedSize(26, 26)
        t.addWidget(ico)
        t.addWidget(StrongBodyLabel("展开 / 折叠"))
        lay.addLayout(t)
        lay.addWidget(_sep())
        self._btn_unfold = PushButton(FIF.UP, "同步展开")
        self._btn_unfold.clicked.connect(self._send_unfold)
        lay.addWidget(self._btn_unfold)
        self._btn_fold = PushButton(FIF.DOWN, "同步折叠")
        self._btn_fold.clicked.connect(self._send_fold)
        lay.addWidget(self._btn_fold)
        return card

    def _build_power_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(7)
        t = QHBoxLayout()
        ico = ToolButton(FIF.POWER_BUTTON)
        ico.setEnabled(False)
        ico.setFixedSize(26, 26)
        t.addWidget(ico)
        t.addWidget(StrongBodyLabel("断电重启"))
        lay.addLayout(t)
        lay.addWidget(_sep())
        tip = CaptionLabel("? 重启后首次指令\n将自动重新启用 LIN")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #d97706;")
        lay.addWidget(tip)
        self._btn_power = PushButton(FIF.POWER_BUTTON, "执行重启")
        self._btn_power.clicked.connect(self._send_power_cycle)
        lay.addWidget(self._btn_power)
        return card

    def _build_lin_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(7)
        t = QHBoxLayout()
        ico = ToolButton(FIF.COMMAND_PROMPT)
        ico.setEnabled(False)
        ico.setFixedSize(26, 26)
        t.addWidget(ico)
        t.addWidget(StrongBodyLabel("LIN 控制"))
        lay.addLayout(t)
        lay.addWidget(_sep())
        tip = CaptionLabel("标定/循环/重启前\n自动发送启用指令")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #718096;")
        lay.addWidget(tip)
        self._btn_lin = PushButton(FIF.SEND, "手动启用 LIN")
        self._btn_lin.clicked.connect(self._send_enable_lin)
        lay.addWidget(self._btn_lin)
        return card

    # ── Worker 挂载 ───────────────────────────────
    def attach_worker(self, worker):
        self._worker = worker
        self._worker.port_opened.connect(lambda: self._apply_connection_state(True))
        self._worker.data_received.connect(self._on_data_received)
        self._worker.error_occurred.connect(self._on_serial_error)

    def detach_worker(self):
        self._worker = None

    def on_disconnected(self):
        self._stop_calib_internal(False)
        self._stop_loop_internal(False, 0)
        self._apply_connection_state(False)
        log("串口已断开", "warning")

    # ── 扫码 ─────────────────────────────────────
    def _on_qr_scanned(self, code: str):
        self._qr_scanned = True
        self._current_qr = code
        self._update_start_buttons()

    def _update_start_buttons(self):
        ok = bool(self._connected) and self._qr_scanned
        self._btn_calib_start.setEnabled(ok and not self._loop_running)
        self._btn_loop_start.setEnabled(ok and not self._calibrating)

    # ── 连接状态 ──────────────────────────────────
    def _apply_connection_state(self, on: bool):
        if on == self._connected:
            return
        self._connected = bool(on)
        self._conn_banner.setVisible(not on)

        aux = [
            self._btn_ver_outer, self._btn_ver_inner,
            self._btn_unfold, self._btn_fold,
            self._btn_power, self._btn_lin,
            self._btn_unload, self._btn_home, self._btn_emergency,
        ]
        for b in aux:
            b.setEnabled(on)

        self._btn_calib_stop.setEnabled(on and self._calibrating)
        self._btn_loop_stop.setEnabled(on and self._loop_running)
        self._update_start_buttons()

        if on:
            InfoBar.success(
                title="连接成功", content="串口已连接，请先扫码后开始操作。",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2000, parent=self,
            )

    def _on_serial_error(self, msg: str):
        log(f"[串口错误] {msg}", "error")
        InfoBar.error(
            title="串口错误", content=msg,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=4000, parent=self,
        )

    # ── 发送 ──────────────────────────────────────
    def _send(self, cmd: bytes, label: str):
        if not (self._worker and self._worker.isRunning()):
            log("串口未连接，无法发送命令", "error")
            return
        self._worker.send(cmd)
        log(f"TX [{label}]  {to_hex(cmd)}", "tx")

    def _send_with_lin(self, cmd: bytes, label: str):
        self._send(CMD_ENABLE_LIN, "启用LIN控制")
        self._send(cmd, label)

    def _query_version_outer(self):
        self._send(CMD_QUERY_VER, "查询外部版本")

    def _query_version_inner(self):
        self._send(CMD_QUERY_INNER_VER, "查询内部版本")

    def _send_unfold(self):
        self._send(CMD_UNFOLD, "同步展开")

    def _send_fold(self):
        self._send(CMD_FOLD, "同步折叠")

    def _send_enable_lin(self):
        self._send(CMD_ENABLE_LIN, "启用LIN控制")

    def _send_power_cycle(self):
        InfoBar.warning(
            title="断电重启", content="命令已发送。",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3000, parent=self,
        )
        self._send_with_lin(CMD_POWER_CYCLE, "断电重启")
        log("断电重启命令已发送", "warning")

    def _send_unload(self):
        delay = _APP_CFG.get("unload_delay_ms")
        self._send(CMD_UNFOLD, "下料-展开")
        QTimer.singleShot(delay, lambda: self._send_with_lin(CMD_POWER_CYCLE, "下料-断电重启"))
        log(f"下料指令已发送（展开 + {delay}ms + 断电重启）", "info")

    def _send_home(self):
        self._send(CMD_FOLD, "回到原位-折叠")

    def _send_emergency_stop(self):
        if not (self._worker and self._worker.isRunning()):
            log("串口未连接，无法发送命令", "error")
            return
        self._worker.send(CMD_POWER_CYCLE)
        log(f"TX [紧急停止]  {to_hex(CMD_POWER_CYCLE)}", "tx")
        InfoBar.error(
            title="紧急停止！", content="断电重启指令已发送！",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3000, parent=self,
        )

    # ── 标定 ──────────────────────────────────────
    def _start_calibration(self):
        if self._calibrating or self._loop_running:
            return
        self._calibrating = True
        self._calib_start = time.monotonic()
        self._calib_bar.setValue(0)
        self._ring_calib.setValue(0)
        self._ring_calib.setRingColor(QColor("#0078d4"))
        self._ring_calib.setAnimating(True)
        self._calib_caption.setText("标定中…")
        self._lbl_calib_status.setText("标定中…")
        self._lbl_calib_status.setStyleSheet("color: #d97706; font-weight: bold;")
        self._btn_calib_start.setEnabled(False)
        self._btn_calib_stop.setEnabled(True)
        self._btn_loop_start.setEnabled(False)
        self._state_tooltip = StateToolTip("标定进行中", "请等待设备完成标定…", self)
        self._state_tooltip.move(self.width() // 2 - 150, 20)
        self._state_tooltip.show()
        self._send_with_lin(CMD_CALIBRATE, "标定")
        self._calib_timer.start(CALIB_POLL_MS)
        log(f"标定已启动，每 {CALIB_POLL_MS/1000:.0f}s 查询状态，超时 {CALIB_TIMEOUT_S}s", "info")

    def _stop_calib_internal(self, success: bool):
        if not self._calibrating:
            return
        self._calibrating = False
        self._calib_timer.stop()
        self._ring_calib.setAnimating(False)
        self._btn_calib_stop.setEnabled(False)
        if self._state_tooltip:
            self._state_tooltip.setContent("标定完成!" if success else "已停止")
            self._state_tooltip.setState(success)
            self._state_tooltip = None
        if not success:
            self._lbl_calib_status.setText("已停止")
            self._lbl_calib_status.setStyleSheet("color: #718096;")
            self._calib_caption.setText("等待开始标定…")
        self._update_start_buttons()

    def _stop_calibration_action(self):
        self._stop_calib_internal(False)
        if self._worker and self._worker.isRunning():
            self._send_with_lin(CMD_POWER_CYCLE, "停止标定-断电重启")
            log("标定已停止，已发送断电重启", "warning")

    def _on_calib_poll(self):
        elapsed = int(time.monotonic() - self._calib_start)
        pct = int(elapsed * 100 / CALIB_TIMEOUT_S)
        self._calib_bar.setValue(min(elapsed, CALIB_TIMEOUT_S))
        self._ring_calib.setValue(min(pct, 100))
        self._ring_calib.setText(f"{elapsed}s")
        self._calib_caption.setText(f"标定中… {elapsed}s / {CALIB_TIMEOUT_S}s")
        self._send(CMD_QUERY_STATUS, "查询标定状态")
        if elapsed >= CALIB_TIMEOUT_S:
            self._stop_calib_internal(False)
            self._lbl_calib_status.setText("超时!")
            self._lbl_calib_status.setStyleSheet("color: #e53e3e; font-weight: bold;")
            self._ring_calib.setRingColor(QColor("#ef4444"))
            self._calib_caption.setText("标定超时，请检查设备")
            log(f"标定超时（已等待 {CALIB_TIMEOUT_S}s）", "error")
            InfoBar.error(
                title="标定超时",
                content=f"已等待 {CALIB_TIMEOUT_S}s，设备未完成标定",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self,
            )

    def _on_calibration_done(self):
        self._calib_bar.setValue(CALIB_TIMEOUT_S)
        self._ring_calib.setValue(100)
        self._ring_calib.setText("完成")
        self._ring_calib.setRingColor(QColor("#22c55e"))
        self._calib_caption.setText("标定完成 ?")
        self._lbl_calib_status.setText("完成 ?")
        self._lbl_calib_status.setStyleSheet("color: #38a169; font-weight: bold;")
        self._stop_calib_internal(True)
        log("? 标定成功完成！", "success")
        InfoBar.success(
            title="标定完成", content="设备标定已成功完成！",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=4000, parent=self,
        )

    # ── 循环运行 ──────────────────────────────────
    def _start_loop(self):
        if self._loop_running or self._calibrating:
            return
        self._loop_target   = self._spin_loop.value()
        self._loop_running  = True
        self._loop_start_dt = QDateTime.currentDateTime()
        self._loop_bar.setValue(0)
        self._ring_loop.setValue(0)
        self._ring_loop.setRingColor(QColor("#059669"))
        self._ring_loop.setAnimating(True)
        self._lbl_loop_cnt.setText(f"0  /  {self._loop_target}")
        self._loop_caption.setText("循环运行中…")
        self._lbl_loop_status.setText("运行中…")
        self._lbl_loop_status.setStyleSheet("color: #d97706; font-weight: bold;")
        self._btn_loop_start.setEnabled(False)
        self._btn_loop_stop.setEnabled(True)
        self._btn_calib_start.setEnabled(False)
        self._send_with_lin(make_loop_cmd(self._loop_target), f"循环测试 × {self._loop_target}")
        self._loop_timer.start(LOOP_POLL_MS)
        log(f"循环运行已启动，目标 {self._loop_target} 次，每 {LOOP_POLL_MS//1000}s 查询次数", "info")

    def _save_loop_record(self, result: str, actual_count: int):
        if not self._loop_start_dt:
            return
        start_str = self._loop_start_dt.toString("yyyy-MM-dd HH:mm:ss")
        end_dt    = QDateTime.currentDateTime()
        end_str   = end_dt.toString("yyyy-MM-dd HH:mm:ss")
        duration  = round(self._loop_start_dt.secsTo(end_dt), 1)
        qr        = self._current_qr if self._current_qr else "(未扫码)"
        try:
            TestDB.insert(qr, start_str, end_str, duration, actual_count, result)
            log(f"测试记录已保存：{qr}  {result}  {actual_count}次  {duration}s", "success")
        except Exception as e:
            log(f"保存测试记录失败: {e}", "error")

    def _stop_loop_internal(self, finished: bool, actual_count: int = 0):
        if not self._loop_running:
            return
        self._loop_running = False
        self._loop_timer.stop()
        self._ring_loop.setAnimating(False)
        self._btn_loop_stop.setEnabled(False)
        if not finished:
            self._lbl_loop_status.setText("已停止")
            self._lbl_loop_status.setStyleSheet("color: #718096;")
            self._loop_caption.setText("等待开始循环运行…")
            self._save_loop_record("中止", actual_count)
        else:
            self._ring_loop.setValue(100)
            self._ring_loop.setText("完成")
            self._ring_loop.setRingColor(QColor("#22c55e"))
            self._save_loop_record("完成", actual_count)
            self._qr.clear_code()
            self._qr_scanned = False
        self._loop_start_dt = None
        self._update_start_buttons()

    def _stop_loop_action(self):
        cnt = self._parse_current_loop_cnt()
        self._stop_loop_internal(False, cnt)
        if self._worker and self._worker.isRunning():
            self._send_with_lin(CMD_POWER_CYCLE, "停止循环-断电重启")
            log("循环运行已停止，已发送断电重启", "warning")

    def _parse_current_loop_cnt(self) -> int:
        txt = self._lbl_loop_cnt.text()
        try:
            return int(txt.split("/")[0].strip())
        except Exception:
            return 0

    def _on_loop_poll(self):
        self._send(CMD_QUERY_STATUS, "查询循环次数")

    def _on_loop_count_update(self, current: int):
        target = self._loop_target
        self._lbl_loop_cnt.setText(f"{current}  /  {target}")
        pct = int(current * 100 / target) if target > 0 else 0
        self._loop_bar.setValue(min(pct, 100))
        self._ring_loop.setValue(min(pct, 100))
        self._loop_caption.setText(f"已运行 {current} 次 / 共 {target} 次")
        log(f"循环进度: {current} / {target}", "info")
        if current >= target:
            self._loop_bar.setValue(100)
            self._lbl_loop_status.setText("运行结束 ?")
            self._lbl_loop_status.setStyleSheet("color: #38a169; font-weight: bold;")
            self._loop_caption.setText("循环运行结束 ?")
            self._stop_loop_internal(True, current)
            log(f"? 循环运行结束，共完成 {current} 次", "success")
            InfoBar.success(
                title="循环运行结束",
                content=f"已完成全部 {current} 次循环！",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self,
            )

    # ── 数据解析 ──────────────────────────────────
    def _on_data_received(self, data: bytes):
        log(f"RX  {to_hex(data)}", "rx")
        if len(data) != RESP_LEN or data[1] != 0x08:
            return

        cmd_byte = data[2]

        if cmd_byte == RESP_CMD_STATUS:
            calib_st = data[4]
            loop_cnt = data[5] | (data[6] << 8)
            calib_map = {0: "未标定", 1: "标定中", 2: "标定成功"}
            log(f"状态: 标定={calib_map.get(calib_st, hex(calib_st))}  循环次数={loop_cnt}", "info")
            if self._calibrating and calib_st == 2:
                self._on_calibration_done()
            if self._loop_running:
                self._on_loop_count_update(loop_cnt)

        elif cmd_byte == RESP_CMD_INNER_VER:
            ver = "".join(chr(b) for b in data[3:10] if 0x20 <= b <= 0x7E)
            if ver:
                exp = _APP_CFG.get("exp_inner_ver").strip()
                if exp:
                    if ver == exp:
                        self._lbl_ver_inner.setText(ver + " ?")
                        self._lbl_ver_inner.setStyleSheet("color: #22c55e; font-weight: bold;")
                    else:
                        self._lbl_ver_inner.setText(f"{ver}  ≠{exp} ?")
                        self._lbl_ver_inner.setStyleSheet("color: #ef4444; font-weight: bold;")
                else:
                    self._lbl_ver_inner.setText(ver)
                    self._lbl_ver_inner.setStyleSheet("color: #3b82f6;")
                log(f"内部版本: {ver}", "success")

        elif cmd_byte == RESP_CMD_OUTER_VER:
            ver = "".join(chr(b) for b in data[3:11] if 0x20 <= b <= 0x7E)
            if ver:
                exp = _APP_CFG.get("exp_outer_ver").strip()
                if exp:
                    if ver == exp:
                        self._lbl_ver_outer.setText(ver + " ?")
                        self._lbl_ver_outer.setStyleSheet("color: #22c55e; font-weight: bold;")
                    else:
                        self._lbl_ver_outer.setText(f"{ver}  ≠{exp} ?")
                        self._lbl_ver_outer.setStyleSheet("color: #ef4444; font-weight: bold;")
                else:
                    self._lbl_ver_outer.setText(ver)
                    self._lbl_ver_outer.setStyleSheet("color: #3b82f6;")
                log(f"外部版本: {ver}", "success")


# ═════════════════════════════════════════════
#  页面 2：串口设置
# ═════════════════════════════════════════════
class SerialSettingPage(QWidget):
    connect_requested    = pyqtSignal(str, int)
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SerialSettingPage")
        self._connected = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(16)
        root.addWidget(TitleLabel("串口设置"))
        root.addWidget(_sep())

        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 18, 24, 18)
        cl.setSpacing(14)

        t_row = QHBoxLayout()
        ico = ToolButton(FIF.LINK)
        ico.setEnabled(False)
        ico.setFixedSize(32, 32)
        t_row.addWidget(ico)
        t_row.addWidget(StrongBodyLabel("串口参数配置"))
        t_row.addStretch()
        self._lbl_status = BodyLabel("● 未连接")
        self._lbl_status.setStyleSheet("color: #e53e3e; font-weight: bold;")
        t_row.addWidget(self._lbl_status)
        cl.addLayout(t_row)
        cl.addWidget(_sep())

        param = QHBoxLayout()
        param.setSpacing(10)
        param.addWidget(BodyLabel("串  口"))
        self._cb_port = ComboBox()
        self._cb_port.setMinimumWidth(130)
        param.addWidget(self._cb_port)
        self._btn_refresh = ToolButton(FIF.SYNC)
        self._btn_refresh.setToolTip("刷新串口列表")
        self._btn_refresh.clicked.connect(self._refresh_ports)
        param.addWidget(self._btn_refresh)
        param.addSpacing(20)
        param.addWidget(BodyLabel("波特率"))
        self._cb_baud = ComboBox()
        for b in ("9600", "19200", "38400", "57600", "115200", "230400"):
            self._cb_baud.addItem(b)
        self._cb_baud.setCurrentText("115200")
        self._cb_baud.setMinimumWidth(130)
        param.addWidget(self._cb_baud)
        param.addStretch()
        cl.addLayout(param)
        cl.addWidget(_sep())

        br = QHBoxLayout()
        br.addStretch()
        self._btn_connect = PrimaryPushButton(FIF.LINK, "连  接")
        self._btn_connect.setMinimumWidth(140)
        self._btn_connect.setMinimumHeight(36)
        self._btn_connect.clicked.connect(self._toggle)
        br.addWidget(self._btn_connect)
        cl.addLayout(br)
        root.addWidget(card)

        info_card = _card()
        il = QVBoxLayout(info_card)
        il.setContentsMargins(24, 18, 24, 18)
        il.setSpacing(10)
        il.addWidget(StrongBodyLabel("连接信息"))
        il.addWidget(_sep())
        self._lbl_info = BodyLabel("当前未建立串口连接")
        self._lbl_info.setStyleSheet("color: #718096;")
        il.addWidget(self._lbl_info)
        root.addWidget(info_card)
        root.addStretch()
        self._refresh_ports()

    def _refresh_ports(self):
        self._cb_port.clear()
        for p in serial.tools.list_ports.comports():
            self._cb_port.addItem(p.device)
        if self._cb_port.count() == 0:
            self._cb_port.addItem("(无可用串口)")

    def _toggle(self):
        if self._connected:
            self.disconnect_requested.emit()
        else:
            port = self._cb_port.currentText()
            if not port or port.startswith("("):
                InfoBar.warning(
                    title="无可用串口", content="请先插入设备并刷新。",
                    orient=Qt.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=3000, parent=self,
                )
                return
            self.connect_requested.emit(port, int(self._cb_baud.currentText()))

    def set_connected(self, on: bool, port: str = "", baud: int = 0):
        self._connected = on
        self._cb_port.setEnabled(not on)
        self._cb_baud.setEnabled(not on)
        self._btn_refresh.setEnabled(not on)
        if on:
            self._btn_connect.setText("断开连接")
            self._btn_connect.setIcon(FIF.CLOSE)
            self._lbl_status.setText("● 已连接")
            self._lbl_status.setStyleSheet("color: #38a169; font-weight: bold;")
            self._lbl_info.setText(f"已连接到  {port}  @  {baud} bps")
            self._lbl_info.setStyleSheet("color: #38a169;")
        else:
            self._btn_connect.setText("连  接")
            self._btn_connect.setIcon(FIF.LINK)
            self._lbl_status.setText("● 未连接")
            self._lbl_status.setStyleSheet("color: #e53e3e; font-weight: bold;")
            self._lbl_info.setText("当前未建立串口连接")
            self._lbl_info.setStyleSheet("color: #718096;")

    def apply_defaults(self, port: str, baud_str: str):
        self._refresh_ports()
        if port:
            idx = self._cb_port.findText(port)
            if idx >= 0:
                self._cb_port.setCurrentIndex(idx)
        if baud_str:
            idx = self._cb_baud.findText(baud_str)
            if idx >= 0:
                self._cb_baud.setCurrentIndex(idx)


# ═════════════════════════════════════════════
#  页面 3：通信日志
# ═════════════════════════════════════════════
class LogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPage")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)

        t = QHBoxLayout()
        t.addWidget(TitleLabel("通信日志"))
        t.addStretch()
        btn_clr = PushButton(FIF.DELETE, "清  空")
        btn_clr.clicked.connect(LogBus.instance().clear)
        t.addWidget(btn_clr)
        lay.addLayout(t)
        lay.addWidget(_sep())

        bus = LogBus.instance()
        bus.setParent(self)
        lay.addWidget(bus, 1)


# ═════════════════════════════════════════════
#  页面 4：测试记录查询
# ═════════════════════════════════════════════
class QueryPage(QWidget):
    _COLS = ["ID", "二维码", "开始时间", "结束时间", "时长(s)", "循环次数", "结果"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QueryPage")
        self._last_rows = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        # 标题
        title_row = QHBoxLayout()
        title_row.addWidget(TitleLabel("测试记录"))
        title_row.addStretch()
        self._lbl_count = CaptionLabel("共 0 条记录")
        self._lbl_count.setStyleSheet("color: #718096;")
        title_row.addWidget(self._lbl_count)
        root.addLayout(title_row)
        root.addWidget(_sep())

        # 查询条件卡片
        fc = _card()
        fl = QVBoxLayout(fc)
        fl.setContentsMargins(20, 14, 20, 14)
        fl.setSpacing(10)

        fh = QHBoxLayout()
        fh.addWidget(ToolButton(FIF.SEARCH))
        fh.addWidget(StrongBodyLabel("查询条件"))
        fh.addStretch()
        fl.addLayout(fh)
        fl.addWidget(_sep())

        cond_row = QHBoxLayout()
        cond_row.setSpacing(14)

        cond_row.addWidget(BodyLabel("二维码:"))
        self._le_qr = QLineEdit()
        self._le_qr.setPlaceholderText("输入二维码关键词（留空不过滤）")
        self._le_qr.setMinimumWidth(200)
        cond_row.addWidget(self._le_qr)

        cond_row.addSpacing(10)
        cond_row.addWidget(BodyLabel("起始日期:"))
        self._dp_from = DatePicker()
        self._dp_from.setDate(QDate.currentDate().addDays(-30))
        cond_row.addWidget(self._dp_from)

        cond_row.addWidget(BodyLabel("~"))
        self._dp_to = DatePicker()
        self._dp_to.setDate(QDate.currentDate())
        cond_row.addWidget(self._dp_to)

        cond_row.addSpacing(10)
        self._btn_no_date = PushButton(FIF.CANCEL, "不限日期")
        self._btn_no_date.setCheckable(True)
        self._btn_no_date.setChecked(False)
        cond_row.addWidget(self._btn_no_date)

        cond_row.addStretch()

        self._btn_query = PrimaryPushButton(FIF.SEARCH, "查  询")
        self._btn_query.setMinimumWidth(110)
        self._btn_query.clicked.connect(self._do_query)
        cond_row.addWidget(self._btn_query)

        btn_refresh = PushButton(FIF.SYNC, "刷  新")
        btn_refresh.setMinimumWidth(90)
        btn_refresh.clicked.connect(self._do_query)
        cond_row.addWidget(btn_refresh)

        fl.addLayout(cond_row)
        root.addWidget(fc)

        # 汇总统计卡片
        stat_card = _card()
        stat_lay = QHBoxLayout(stat_card)
        stat_lay.setContentsMargins(20, 10, 20, 10)
        stat_lay.setSpacing(30)
        self._lbl_stat_total   = self._make_stat(stat_lay, "总次数", "0")
        self._lbl_stat_done    = self._make_stat(stat_lay, "完成",   "0", "#22c55e")
        self._lbl_stat_aborted = self._make_stat(stat_lay, "中止",   "0", "#ef4444")
        self._lbl_stat_avg     = self._make_stat(stat_lay, "平均时长", "—")
        stat_lay.addStretch()
        root.addWidget(stat_card)

        # 数据表格
        self._table = TableWidget(self)
        self._table.setColumnCount(len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setBorderVisible(True)
        self._table.setBorderRadius(8)
        for i, w in enumerate([50, 180, 160, 160, 80, 80, 80]):
            self._table.setColumnWidth(i, w)
        root.addWidget(self._table, 1)

        # 底部操作栏
        bot_row = QHBoxLayout()
        bot_row.addStretch()
        self._btn_export = PushButton(FIF.SAVE, "导出 CSV")
        self._btn_export.setMinimumWidth(110)
        self._btn_export.clicked.connect(self._export_csv)
        bot_row.addWidget(self._btn_export)
        btn_del = PushButton(FIF.DELETE, "删除选中")
        btn_del.clicked.connect(self._delete_selected)
        bot_row.addWidget(btn_del)
        root.addLayout(bot_row)

    def _make_stat(self, parent_layout, label, default, color=""):
        col = QVBoxLayout()
        col.setSpacing(2)
        lb = CaptionLabel(label)
        lb.setAlignment(Qt.AlignCenter)
        val = SubtitleLabel(default)
        val.setAlignment(Qt.AlignCenter)
        if color:
            val.setStyleSheet(f"color: {color}; font-weight: bold;")
        col.addWidget(lb)
        col.addWidget(val)
        parent_layout.addLayout(col)
        return val

    def _do_query(self):
        qr_kw   = self._le_qr.text().strip()
        no_date = self._btn_no_date.isChecked()
        date_from = "" if no_date else self._dp_from.getDate().toString("yyyy-MM-dd")
        date_to   = "" if no_date else self._dp_to.getDate().toString("yyyy-MM-dd")

        try:
            rows = TestDB.query(qr_code=qr_kw, date_from=date_from, date_to=date_to)
        except Exception as e:
            InfoBar.error(
                title="查询失败", content=str(e),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self,
            )
            return

        self._last_rows = rows
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                if c == 6:
                    if str(val) == "完成":
                        item.setForeground(QColor("#22c55e"))
                    elif str(val) == "中止":
                        item.setForeground(QColor("#ef4444"))
                self._table.setItem(r, c, item)

        total   = len(rows)
        done    = sum(1 for r in rows if r[6] == "完成")
        aborted = sum(1 for r in rows if r[6] == "中止")
        durs    = [r[4] for r in rows if r[4] is not None]
        avg_dur = f"{sum(durs)/len(durs):.1f}s" if durs else "—"

        self._lbl_count.setText(f"共 {total} 条记录")
        self._lbl_stat_total.setText(str(total))
        self._lbl_stat_done.setText(str(done))
        self._lbl_stat_aborted.setText(str(aborted))
        self._lbl_stat_avg.setText(avg_dur)

    def _delete_selected(self):
        selected_rows = list({idx.row() for idx in self._table.selectedIndexes()})
        if not selected_rows:
            InfoBar.warning(
                title="未选中", content="请先选中要删除的记录行。",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2000, parent=self,
            )
            return
        ids = []
        for r in selected_rows:
            item = self._table.item(r, 0)
            if item:
                try:
                    ids.append(int(item.text()))
                except ValueError:
                    pass
        if ids:
            TestDB.delete_by_ids(ids)
            self._do_query()
            InfoBar.success(
                title="已删除", content=f"成功删除 {len(ids)} 条记录。",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2000, parent=self,
            )

    def _export_csv(self):
        if not self._last_rows:
            InfoBar.warning(
                title="无数据", content="请先执行查询，再导出 CSV。",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2500, parent=self,
            )
            return
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        default_name = f"test_records_{ts}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", default_name,
            "CSV 文件 (*.csv);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(self._COLS)
                for row in self._last_rows:
                    writer.writerow([str(v) for v in row])
            InfoBar.success(
                title="导出成功",
                content=f"已导出 {len(self._last_rows)} 条记录到:\n{path}",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self,
            )
        except Exception as e:
            InfoBar.error(
                title="导出失败", content=str(e),
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self,
            )

    def refresh(self):
        self._do_query()


# ═════════════════════════════════════════════
#  页面 5：参数配置
# ═════════════════════════════════════════════
class ParamSettingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ParamSettingPage")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        scroll.setWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(20)
        root.addWidget(TitleLabel("参数配置"))
        root.addWidget(CaptionLabel("所有设置自动保存，下次启动时自动恢复。"))
        root.addWidget(_sep())

        # 版本期望卡片
        vc = _card()
        vl = QVBoxLayout(vc)
        vl.setContentsMargins(24, 18, 24, 18)
        vl.setSpacing(14)
        vh = QHBoxLayout()
        vh.addWidget(ToolButton(FIF.INFO))
        vh.addWidget(StrongBodyLabel("期望版本号"))
        vh.addStretch()
        vh.addWidget(CaptionLabel("查询到版本后与此对比，显示 ? 或 ?"))
        vl.addLayout(vh)
        vl.addWidget(_sep())

        vr1 = QHBoxLayout()
        vr1.addWidget(BodyLabel("期望外部版本"))
        vr1.addStretch()
        self._le_outer_ver = QLineEdit()
        self._le_outer_ver.setPlaceholderText("如 V1.0.0（留空不比对）")
        self._le_outer_ver.setFixedWidth(220)
        self._le_outer_ver.setText(_APP_CFG.get("exp_outer_ver"))
        self._le_outer_ver.editingFinished.connect(
            lambda: _APP_CFG.set("exp_outer_ver", self._le_outer_ver.text().strip())
        )
        vr1.addWidget(self._le_outer_ver)
        vl.addLayout(vr1)

        vr2 = QHBoxLayout()
        vr2.addWidget(BodyLabel("期望内部版本"))
        vr2.addStretch()
        self._le_inner_ver = QLineEdit()
        self._le_inner_ver.setPlaceholderText("如 V1.0.0（留空不比对）")
        self._le_inner_ver.setFixedWidth(220)
        self._le_inner_ver.setText(_APP_CFG.get("exp_inner_ver"))
        self._le_inner_ver.editingFinished.connect(
            lambda: _APP_CFG.set("exp_inner_ver", self._le_inner_ver.text().strip())
        )
        vr2.addWidget(self._le_inner_ver)
        vl.addLayout(vr2)

        root.addWidget(vc)

        # 运行参数卡片
        rc = _card()
        rl = QVBoxLayout(rc)
        rl.setContentsMargins(24, 18, 24, 18)
        rl.setSpacing(14)
        rh = QHBoxLayout()
        rh.addWidget(ToolButton(FIF.ROTATE))
        rh.addWidget(StrongBodyLabel("运行参数"))
        rl.addLayout(rh)
        rl.addWidget(_sep())

        rr1 = QHBoxLayout()
        rr1.addWidget(BodyLabel("默认循环次数"))
        rr1.addStretch()
        self._sp_loop = SpinBox()
        self._sp_loop.setRange(1, 255)
        self._sp_loop.setValue(_APP_CFG.get("loop_count"))
        self._sp_loop.setSuffix("  次")
        self._sp_loop.setFixedWidth(130)
        self._sp_loop.valueChanged.connect(lambda v: _APP_CFG.set("loop_count", v))
        rr1.addWidget(self._sp_loop)
        rl.addLayout(rr1)

        rr2 = QHBoxLayout()
        rr2.addWidget(BodyLabel("下料等待时间"))
        rr2.addStretch()
        self._sp_delay = SpinBox()
        self._sp_delay.setRange(50, 9999)
        self._sp_delay.setValue(_APP_CFG.get("unload_delay_ms"))
        self._sp_delay.setSuffix("  ms")
        self._sp_delay.setFixedWidth(150)
        self._sp_delay.valueChanged.connect(lambda v: _APP_CFG.set("unload_delay_ms", v))
        rr2.addWidget(self._sp_delay)
        rl.addLayout(rr2)

        root.addWidget(rc)

        # 串口默认卡片
        sc = _card()
        sl = QVBoxLayout(sc)
        sl.setContentsMargins(24, 18, 24, 18)
        sl.setSpacing(14)
        sh = QHBoxLayout()
        sh.addWidget(ToolButton(FIF.CONNECT))
        sh.addWidget(StrongBodyLabel("串口默认"))
        sh.addStretch()
        sh.addWidget(CaptionLabel("下次启动时自动预选"))
        sl.addLayout(sh)
        sl.addWidget(_sep())

        sr1 = QHBoxLayout()
        sr1.addWidget(BodyLabel("默认串口"))
        sr1.addStretch()
        self._le_port = QLineEdit()
        self._le_port.setPlaceholderText("如 COM3（留空不预选）")
        self._le_port.setFixedWidth(220)
        self._le_port.setText(_APP_CFG.get("serial_port"))
        self._le_port.editingFinished.connect(
            lambda: _APP_CFG.set("serial_port", self._le_port.text().strip())
        )
        sr1.addWidget(self._le_port)
        sl.addLayout(sr1)

        sr2 = QHBoxLayout()
        sr2.addWidget(BodyLabel("默认波特率"))
        sr2.addStretch()
        self._cb_baud2 = ComboBox()
        for b in ("9600", "19200", "38400", "57600", "115200", "230400"):
            self._cb_baud2.addItem(b)
        saved_baud = _APP_CFG.get("serial_baud")
        self._cb_baud2.setCurrentText(saved_baud if saved_baud else "115200")
        self._cb_baud2.setFixedWidth(130)
        self._cb_baud2.currentTextChanged.connect(lambda v: _APP_CFG.set("serial_baud", v))
        sr2.addWidget(self._cb_baud2)
        sl.addLayout(sr2)

        root.addWidget(sc)

        # 主题卡片
        tc = _card()
        tl = QVBoxLayout(tc)
        tl.setContentsMargins(24, 18, 24, 18)
        tl.setSpacing(14)
        th = QHBoxLayout()
        th.addWidget(ToolButton(FIF.BRUSH))
        th.addWidget(StrongBodyLabel("界面主题"))
        th.addStretch()
        th.addWidget(CaptionLabel("立即生效并持久保存"))
        tl.addLayout(th)
        tl.addWidget(_sep())

        tr1 = QHBoxLayout()
        tr1.addWidget(BodyLabel("主题模式"))
        tr1.addStretch()
        self._seg = SegmentedWidget()
        self._seg.addItem("auto",  "跟随系统")
        self._seg.addItem("light", "浅色")
        self._seg.addItem("dark",  "深色")
        saved_theme = _APP_CFG.get("theme") or "auto"
        self._seg.setCurrentItem(saved_theme)
        self._seg.currentItemChanged.connect(self._on_theme_changed)
        tr1.addWidget(self._seg)
        tl.addLayout(tr1)

        tl.addWidget(BodyLabel("主题色"))
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        for name, hc in _THEME_COLORS:
            btn = PushButton(name)
            btn.setFixedHeight(30)
            btn.clicked.connect((lambda h: lambda: self._on_color_picked(h))(hc))
            color_row.addWidget(btn)
        color_row.addStretch()
        tl.addLayout(color_row)

        root.addWidget(tc)
        root.addStretch()

    def _on_theme_changed(self, key: str):
        mapping = {"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}
        setTheme(mapping[key])
        _APP_CFG.set("theme", key)

    def _on_color_picked(self, hc: str):
        setThemeColor(QColor(hc))
        _APP_CFG.set("theme_color", hc)
        InfoBar.success(
            title="主题色已更新", content=f"已切换为 {hc}",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=1800, parent=self,
        )


# ═════════════════════════════════════════════
#  页面 6：关于
# ═════════════════════════════════════════════
class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AboutPage")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(scroll)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(36, 28, 36, 36)
        root.setSpacing(20)
        root.addWidget(TitleLabel("关于"))
        root.addWidget(_sep())

        about_card = _card()
        a_lay = QVBoxLayout(about_card)
        a_lay.setContentsMargins(24, 18, 24, 22)
        a_lay.setSpacing(12)
        ico_row = QHBoxLayout()
        ico_btn = ToolButton(FIF.APPLICATION)
        ico_btn.setEnabled(False)
        ico_btn.setFixedSize(48, 48)
        ico_row.addWidget(ico_btn)
        app_name_col = QVBoxLayout()
        app_name_col.setSpacing(2)
        app_name_col.addWidget(SubtitleLabel(APP_NAME))
        app_name_col.addWidget(CaptionLabel(f"{APP_VERSION}  ?  {APP_AUTHOR}"))
        ico_row.addLayout(app_name_col)
        ico_row.addStretch()
        a_lay.addLayout(ico_row)
        a_lay.addWidget(_sep())
        for label, value in [
            ("用途",   "LIN 总线设备调试与控制上位机"),
            ("协议",   "固定 13 字节帧，首尾 0x02"),
            ("框架",   "PyQt5 + PyQt-Fluent-Widgets"),
            ("数据库", "SQLite（test_records.db）"),
            ("Python", sys.version.split()[0]),
        ]:
            row = QHBoxLayout()
            lb = BodyLabel(label)
            lb.setFixedWidth(60)
            row.addWidget(lb)
            vl = BodyLabel(value)
            vl.setStyleSheet("color: #718096;")
            row.addWidget(vl)
            row.addStretch()
            a_lay.addLayout(row)
        root.addWidget(about_card)
        root.addStretch()


# ═════════════════════════════════════════════
#  主窗口
# ═════════════════════════════════════════════
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  {APP_VERSION}")
        self.resize(1150, 860)
        self.setMinimumSize(960, 720)
        self.navigationInterface.setExpandWidth(220)

        self._control_page = ControlPage(self)
        self._serial_page  = SerialSettingPage(self)
        self._log_page     = LogPage(self)
        self._query_page   = QueryPage(self)
        self._param_page   = ParamSettingPage(self)
        self._about_page   = AboutPage(self)

        self.addSubInterface(self._control_page, FIF.HOME,            "控制面板", NavigationItemPosition.TOP)
        self.addSubInterface(self._serial_page,  FIF.CONNECT,         "串口设置", NavigationItemPosition.TOP)
        self.addSubInterface(self._log_page,     FIF.DOCUMENT,        "通信日志", NavigationItemPosition.TOP)
        self.addSubInterface(self._query_page,   FIF.HISTORY,         "测试记录", NavigationItemPosition.TOP)
        self.addSubInterface(self._param_page,   FIF.DEVELOPER_TOOLS, "参数配置", NavigationItemPosition.TOP)
        self.navigationInterface.addSeparator()
        self.addSubInterface(self._about_page,   FIF.INFO,            "关    于", NavigationItemPosition.BOTTOM)

        self._serial_page.connect_requested.connect(self._do_connect)
        self._serial_page.disconnect_requested.connect(self._do_disconnect)
        self._worker = None

        self._serial_page.apply_defaults(
            _APP_CFG.get("serial_port"),
            _APP_CFG.get("serial_baud"),
        )

        QTimer.singleShot(80, self._expand_nav)

    def _expand_nav(self):
        try:
            self.navigationInterface.panel.expand()
        except Exception:
            pass

    def _do_connect(self, port: str, baud: int):
        if self._worker:
            self._worker.stop()
        self._worker = SerialWorker(port, baud, self)
        self._worker.port_opened.connect(lambda: self._on_port_opened(port, baud))
        self._worker.error_occurred.connect(self._control_page._on_serial_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._control_page.attach_worker(self._worker)
        self._worker.start()

    def _do_disconnect(self):
        if self._worker:
            self._worker.stop()

    def _on_port_opened(self, port: str, baud: int):
        self._serial_page.set_connected(True, port, baud)

    def _on_worker_finished(self):
        self._control_page.on_disconnected()
        self._serial_page.set_connected(False)
        self._control_page.detach_worker()
        self._worker = None

    def closeEvent(self, event):
        if self._worker:
            self._worker.stop()
        super().closeEvent(event)


# ─────────────────────────────────────────────
#  程序入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    # 初始化数据库
    TestDB.init()

    # 恢复上次保存的主题设置
    _theme_map = {"auto": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}
    setTheme(_theme_map.get(_APP_CFG.get("theme"), Theme.AUTO))
    saved_color = _APP_CFG.get("theme_color")
    if saved_color:
        setThemeColor(QColor(saved_color))

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec_())
