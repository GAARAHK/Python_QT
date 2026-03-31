# -*- coding: gbk -*-
"""
20路电机监控大屏 v2
每张卡片内置：二维码输入、工况选择、启停按钮
每行（5路）有独立的批量工况设定与启停
"""
from PyQt5.QtWidgets import (
    QWidget, QLabel, QFrame, QPushButton, QLineEdit, QComboBox,
    QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
import datetime

from database import load_templates

TOTAL_MOTORS = 20
MOTORS_PER_ROW = 5

# 状态配色: (LED颜色, 边框/条颜色, 卡片背景, 状态文字颜色)
STATE_STYLE = {
    "IDLE":            ("#3A4A60", "#1E2D44", "#0C1420", "#4A6080"),
    "FORWARD":         ("#0088FF", "#0066CC", "#060E20", "#44AAFF"),
    "REVERSE":         ("#FF8800", "#CC6600", "#100800", "#FFAA44"),
    "STOPPED_BETWEEN": ("#00AA44", "#008833", "#04100A", "#44CC88"),
    "ALARM":           ("#FF2222", "#CC0000", "#100404", "#FF6666"),
    "COMPLETED":       ("#00DDAA", "#009977", "#040E0C", "#44EEBB"),
}
STATE_LABELS = {
    "IDLE":            "空  闲",
    "FORWARD":         "正  转",
    "REVERSE":         "反  转",
    "STOPPED_BETWEEN": "暂  停",
    "ALARM":           "报  警",
    "COMPLETED":       "完  成",
}

_BTN_START_QSS = """
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1A4A28, stop:1 #0E2A18);
    color: #44EE66; border: 1px solid #1E5530;
    border-radius: 3px; font-size: 11px; font-weight: bold;
    padding: 2px 6px;
}
QPushButton:hover { background: #1E5A30; }
QPushButton:pressed { background: #0A1E10; }
QPushButton:disabled { color: #2A4A30; border-color: #162A1E; }
"""

_BTN_STOP_QSS = """
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #4A1A1A, stop:1 #2A0E0E);
    color: #EE4444; border: 1px solid #5A1E1E;
    border-radius: 3px; font-size: 11px; font-weight: bold;
    padding: 2px 6px;
}
QPushButton:hover { background: #5A2020; }
QPushButton:pressed { background: #1E0A0A; }
QPushButton:disabled { color: #4A2A2A; border-color: #2A1414; }
"""


# ─────────────────────────────────────────────────────────────────────────────
class MotorCard(QFrame):
    """单路电机卡片，内置二维码输入 + 工况选择 + 启停按钮"""

    # 信号：请求启动/停止某路电机
    start_requested = pyqtSignal(int, str, dict)   # motor_id, qr_code, template
    stop_requested  = pyqtSignal(int)              # motor_id

    def __init__(self, motor_id: int, parent=None):
        super().__init__(parent)
        self.motor_id  = motor_id
        self._state    = "IDLE"
        self._running  = False
        self._templates: list[dict] = []

        self.setFixedSize(236, 188)
        self._build()
        self._apply_state("IDLE")

        # 报警 LED 闪烁
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._blink_led)
        self._blink_on = True

    # ── 构建 ─────────────────────────────────────────────────────────
    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 左侧彩色状态竖条
        self._accent_bar = QFrame()
        self._accent_bar.setFixedWidth(4)
        outer.addWidget(self._accent_bar)

        # 右侧内容区
        content = QWidget()
        content.setObjectName("cardContent")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(7, 5, 7, 5)
        vbox.setSpacing(3)

        # ---- 行1：LED + 编号 + 状态 ----
        r1 = QHBoxLayout()
        r1.setSpacing(5)
        self._led = QLabel()
        self._led.setFixedSize(10, 10)
        r1.addWidget(self._led)
        lbl_id = QLabel(f"#{self.motor_id:02d}")
        lbl_id.setFont(QFont("Consolas", 11, QFont.Bold))
        lbl_id.setStyleSheet("color:#8ABCDE; background:transparent;")
        r1.addWidget(lbl_id)
        r1.addStretch()
        self._state_lbl = QLabel("空  闲")
        self._state_lbl.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        self._state_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        r1.addWidget(self._state_lbl)
        vbox.addLayout(r1)

        # ---- 分割线 ----
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#1A2A44;")
        vbox.addWidget(line)

        # ---- 行2：二维码输入 ----
        self._qr_edit = QLineEdit()
        self._qr_edit.setPlaceholderText("输入工件二维码...")
        self._qr_edit.setFixedHeight(22)
        self._qr_edit.setFont(QFont("Consolas", 9))
        self._qr_edit.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        vbox.addWidget(self._qr_edit)

        # ---- 行3：工况选择 ----
        self._tmpl_combo = QComboBox()
        self._tmpl_combo.setFixedHeight(22)
        self._tmpl_combo.setFont(QFont("Microsoft YaHei UI", 9))
        self._tmpl_combo.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 2px;"
            " QComboBox::drop-down{border:none;}"
            " QComboBox::down-arrow{image:none;}"
        )
        vbox.addWidget(self._tmpl_combo)

        # ---- 行4：启动 / 停止 ----
        r4 = QHBoxLayout()
        r4.setSpacing(4)
        self._btn_start = QPushButton("启 动")
        self._btn_start.setFixedHeight(24)
        self._btn_start.setStyleSheet(_BTN_START_QSS)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop = QPushButton("停 止")
        self._btn_stop.setFixedHeight(24)
        self._btn_stop.setStyleSheet(_BTN_STOP_QSS)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)
        r4.addWidget(self._btn_start)
        r4.addWidget(self._btn_stop)
        vbox.addLayout(r4)

        # ---- 行5：循环 + 电流 ----
        r5 = QHBoxLayout()
        r5.setSpacing(0)

        loop_w = QWidget()
        loop_w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(loop_w)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lt = QLabel("循环")
        lt.setFont(QFont("Microsoft YaHei UI", 8))
        lt.setStyleSheet("color:#2A4060; background:transparent;")
        self._loop_val = QLabel("----")
        self._loop_val.setFont(QFont("Consolas", 13, QFont.Bold))
        self._loop_val.setStyleSheet("color:#4A7A9A; background:transparent;")
        lv.addWidget(lt)
        lv.addWidget(self._loop_val)
        r5.addWidget(loop_w)
        r5.addStretch()

        cur_w = QWidget()
        cur_w.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(cur_w)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        ct = QLabel("电流 A")
        ct.setFont(QFont("Microsoft YaHei UI", 8))
        ct.setStyleSheet("color:#2A4060; background:transparent;")
        ct.setAlignment(Qt.AlignRight)
        self._cur_val = QLabel("--.-")
        self._cur_val.setFont(QFont("Consolas", 13, QFont.Bold))
        self._cur_val.setStyleSheet("color:#4A7A9A; background:transparent;")
        self._cur_val.setAlignment(Qt.AlignRight)
        cv.addWidget(ct)
        cv.addWidget(self._cur_val)
        r5.addWidget(cur_w)

        vbox.addLayout(r5)
        outer.addWidget(content)

    # ── 内部动作 ─────────────────────────────────────────────────────
    def _on_start(self):
        tmpl = self._current_template()
        if tmpl is None:
            return
        qr = self._qr_edit.text().strip()
        self.start_requested.emit(self.motor_id, qr, tmpl)

    def _on_stop(self):
        self.stop_requested.emit(self.motor_id)

    def _current_template(self) -> dict | None:
        idx = self._tmpl_combo.currentIndex()
        if idx < 0 or idx >= len(self._templates):
            return None
        return self._templates[idx]

    def _blink_led(self):
        led_c = STATE_STYLE["ALARM"][0]
        if self._blink_on:
            self._led.setStyleSheet(
                f"background-color:{led_c}; border-radius:5px; border:1px solid #CC0000;"
            )
        else:
            self._led.setStyleSheet(
                "background-color:#200808; border-radius:5px; border:1px solid #400808;"
            )
        self._blink_on = not self._blink_on

    # ── 公开更新接口 ─────────────────────────────────────────────────
    def refresh_templates(self, templates: list[dict]):
        self._templates = templates
        current_text = self._tmpl_combo.currentText()
        self._tmpl_combo.blockSignals(True)
        self._tmpl_combo.clear()
        for t in templates:
            self._tmpl_combo.addItem(t["name"])
        idx = self._tmpl_combo.findText(current_text)
        if idx >= 0:
            self._tmpl_combo.setCurrentIndex(idx)
        self._tmpl_combo.blockSignals(False)

    def update_state(self, state_name: str):
        self._state = state_name
        self._apply_state(state_name)
        if state_name == "ALARM":
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._blink_on = True

    def update_running(self, running: bool):
        self._running = running
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self._qr_edit.setReadOnly(running)
        self._tmpl_combo.setEnabled(not running)

    def update_loop(self, count: int):
        self._loop_val.setText(f"{count:04d}")

    def update_current(self, value: float, alarmed: bool = False):
        self._cur_val.setText(f"{value:5.2f}")
        color = "#FF4444" if alarmed else STATE_STYLE.get(self._state, STATE_STYLE["IDLE"])[0]
        self._cur_val.setStyleSheet(
            f"color:{color}; background:transparent;"
            " font-family:Consolas; font-size:13pt; font-weight:bold;"
        )

    def _apply_state(self, state_name: str):
        led_c, bar_c, bg_c, txt_c = STATE_STYLE.get(state_name, STATE_STYLE["IDLE"])
        self._accent_bar.setStyleSheet(f"background-color:{bar_c};")
        self._led.setStyleSheet(
            f"background-color:{led_c}; border-radius:5px; border:1px solid {bar_c};"
        )
        self._state_lbl.setText(STATE_LABELS.get(state_name, state_name))
        self._state_lbl.setStyleSheet(
            f"color:{txt_c}; font-weight:bold; background:transparent;"
        )
        self.setStyleSheet(f"""
            MotorCard {{
                background-color:{bg_c};
                border:1px solid {bar_c};
                border-left:none;
                border-radius:4px;
            }}
            #cardContent {{ background-color:{bg_c}; }}
        """)


# ─────────────────────────────────────────────────────────────────────────────
class RowHeader(QFrame):
    """一行（5路电机）的批量控制头部"""

    start_row_sig = pyqtSignal(list, dict)    # [motor_id, ...], template
    stop_row_sig  = pyqtSignal(list)           # [motor_id, ...]

    def __init__(self, row_idx: int, motor_ids: list[int], parent=None):
        super().__init__(parent)
        self._motor_ids = motor_ids
        self._templates: list[dict] = []

        self.setFixedHeight(40)
        self.setStyleSheet(
            "background:#0A1528; border:1px solid #1E3050; border-radius:3px;"
        )
        self._build(row_idx)

    def _build(self, row_idx: int):
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(10, 4, 10, 4)
        hbox.setSpacing(8)

        # 组名
        ids_str = f"{self._motor_ids[0]:02d}-{self._motor_ids[-1]:02d}"
        lbl = QLabel(f"第 {row_idx + 1} 组  #{ids_str}")
        lbl.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        lbl.setStyleSheet("color:#4A7A9A; background:transparent;")
        lbl.setFixedWidth(130)
        hbox.addWidget(lbl)

        # 批量工况下拉
        lbl2 = QLabel("批量工况:")
        lbl2.setFont(QFont("Microsoft YaHei UI", 9))
        lbl2.setStyleSheet("color:#3A5070; background:transparent;")
        hbox.addWidget(lbl2)

        self._row_combo = QComboBox()
        self._row_combo.setFixedSize(160, 26)
        self._row_combo.setFont(QFont("Microsoft YaHei UI", 9))
        self._row_combo.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        hbox.addWidget(self._row_combo)

        hbox.addStretch()

        # 本组启动
        btn_start = QPushButton("本组启动")
        btn_start.setFixedSize(80, 26)
        btn_start.setStyleSheet(_BTN_START_QSS)
        btn_start.clicked.connect(self._on_row_start)
        hbox.addWidget(btn_start)

        # 本组停止
        btn_stop = QPushButton("本组停止")
        btn_stop.setFixedSize(80, 26)
        btn_stop.setStyleSheet(_BTN_STOP_QSS)
        btn_stop.clicked.connect(self._on_row_stop)
        hbox.addWidget(btn_stop)

    def refresh_templates(self, templates: list[dict]):
        self._templates = templates
        cur = self._row_combo.currentText()
        self._row_combo.blockSignals(True)
        self._row_combo.clear()
        for t in templates:
            self._row_combo.addItem(t["name"])
        idx = self._row_combo.findText(cur)
        if idx >= 0:
            self._row_combo.setCurrentIndex(idx)
        self._row_combo.blockSignals(False)

    def _on_row_start(self):
        idx = self._row_combo.currentIndex()
        if idx < 0 or idx >= len(self._templates):
            return
        self.start_row_sig.emit(self._motor_ids, self._templates[idx])

    def _on_row_stop(self):
        self.stop_row_sig.emit(self._motor_ids)


# ─────────────────────────────────────────────────────────────────────────────
class OverviewPanel(QWidget):
    """20路电机监控大屏"""

    start_motor_sig = pyqtSignal(int, str, dict)   # motor_id, qr_code, template
    stop_motor_sig  = pyqtSignal(int)              # motor_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[int, MotorCard] = {}
        self._row_headers: list[RowHeader] = []
        self._build()
        self.refresh_templates()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部标题栏 ────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(38)
        header.setStyleSheet("background:#060A14; border-bottom:1px solid #1A2A44;")
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(16, 0, 16, 0)
        title = QLabel("20路电机串口群控系统  /  实时监控大屏")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        title.setStyleSheet("color:#00AADD; background:transparent;")
        h_row.addWidget(title)
        h_row.addStretch()
        self._clock_lbl = QLabel()
        self._clock_lbl.setFont(QFont("Consolas", 11))
        self._clock_lbl.setStyleSheet("color:#3A5A70; background:transparent;")
        h_row.addWidget(self._clock_lbl)
        root.addWidget(header)

        # ── 图例栏 ────────────────────────────────────────────────
        legend = QFrame()
        legend.setFixedHeight(27)
        legend.setStyleSheet("background:#080D1A;")
        l_row = QHBoxLayout(legend)
        l_row.setContentsMargins(16, 0, 16, 0)
        l_row.setSpacing(18)
        for state, (led_c, _, _, txt_c) in STATE_STYLE.items():
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background-color:{led_c}; border-radius:4px;")
            lbl = QLabel(STATE_LABELS[state].replace("  ", " "))
            lbl.setFont(QFont("Microsoft YaHei UI", 9))
            lbl.setStyleSheet(f"color:{txt_c}; background:transparent;")
            item_w = QWidget()
            item_w.setStyleSheet("background:transparent;")
            il = QHBoxLayout(item_w)
            il.setContentsMargins(0, 0, 0, 0)
            il.setSpacing(4)
            il.addWidget(dot)
            il.addWidget(lbl)
            l_row.addWidget(item_w)
        l_row.addStretch()
        self._running_lbl = QLabel("运行中: 0 路")
        self._running_lbl.setFont(QFont("Consolas", 9))
        self._running_lbl.setStyleSheet("color:#3A5070; background:transparent;")
        l_row.addWidget(self._running_lbl)
        root.addWidget(legend)

        # ── 可滚动卡片区 ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:#0C1020;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background:#0C1020;")
        inner_vbox = QVBoxLayout(inner)
        inner_vbox.setContentsMargins(12, 12, 12, 12)
        inner_vbox.setSpacing(8)

        # 构建 4 组，每组：RowHeader + 一行 5 张卡片
        for row_idx in range(TOTAL_MOTORS // MOTORS_PER_ROW):
            motor_ids = list(range(
                row_idx * MOTORS_PER_ROW + 1,
                row_idx * MOTORS_PER_ROW + MOTORS_PER_ROW + 1
            ))
            rh = RowHeader(row_idx, motor_ids)
            rh.start_row_sig.connect(self._on_row_start)
            rh.stop_row_sig.connect(self._on_row_stop)
            self._row_headers.append(rh)
            inner_vbox.addWidget(rh)

            cards_row = QHBoxLayout()
            cards_row.setSpacing(6)
            for mid in motor_ids:
                card = MotorCard(mid)
                card.start_requested.connect(self.start_motor_sig)
                card.stop_requested.connect(self.stop_motor_sig)
                self._cards[mid] = card
                cards_row.addWidget(card)
            cards_row.addStretch()
            inner_vbox.addLayout(cards_row)

        inner_vbox.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # 时钟定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _tick(self):
        self._clock_lbl.setText(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    def _update_running_count(self):
        n = sum(
            1 for c in self._cards.values()
            if c._state in ("FORWARD", "REVERSE", "STOPPED_BETWEEN")
        )
        self._running_lbl.setText(f"运行中: {n} 路")

    def _on_row_start(self, motor_ids: list, template: dict):
        """批量启动某行所有电机（逐个发信号）"""
        for mid in motor_ids:
            card = self._cards.get(mid)
            if card:
                qr = card._qr_edit.text().strip()
                self.start_motor_sig.emit(mid, qr, template)

    def _on_row_stop(self, motor_ids: list):
        for mid in motor_ids:
            self.stop_motor_sig.emit(mid)

    # ── 公开刷新接口 ─────────────────────────────────────────────────
    def refresh_templates(self):
        templates = load_templates()
        for card in self._cards.values():
            card.refresh_templates(templates)
        for rh in self._row_headers:
            rh.refresh_templates(templates)

    def set_state(self, motor_id: int, state: str):
        if motor_id in self._cards:
            self._cards[motor_id].update_state(state)
            self._update_running_count()

    def set_running(self, motor_id: int, running: bool):
        if motor_id in self._cards:
            self._cards[motor_id].update_running(running)

    def set_loop(self, motor_id: int, count: int):
        if motor_id in self._cards:
            self._cards[motor_id].update_loop(count)

    def set_current(self, motor_id: int, value: float, alarmed: bool = False):
        if motor_id in self._cards:
            self._cards[motor_id].update_current(value, alarmed)

    # 兼容旧接口（main.py 中遗留的调用，保留为空操作）
    def set_qr(self, motor_id: int, qr: str):
        pass

    def set_template(self, motor_id: int, name: str):
        pass
