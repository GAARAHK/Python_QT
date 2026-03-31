# -*- coding: gbk -*-
"""
控制面板 v2
- 串口配置（COM_A + COM_B，波特率，比例系数）
- 电机控制器（COM_A）Modbus 参数配置
- 电流采集模块（COM_B）Modbus 参数配置
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QGroupBox,
    QScrollArea, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont
import serial.tools.list_ports

from database import load_all_settings, save_all_settings
import styles
import modbus_utils


def _make_group(title: str) -> QGroupBox:
    gb = QGroupBox(title)
    gb.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
    gb.setStyleSheet(
        "QGroupBox { color:#00AADD; border:1px solid #1E3A60;"
        "  border-radius:4px; margin-top:12px; padding-top:8px; }"
        "QGroupBox::title { subcontrol-origin:margin; left:10px;"
        "  padding:0 4px; background:#0C1020; }"
    )
    return gb


def _row_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Microsoft YaHei UI", 9))
    lbl.setStyleSheet("color:#6A8A9A; background:transparent;")
    lbl.setFixedWidth(110)
    return lbl


def _resp_edit() -> QLineEdit:
    """只读回显框"""
    e = QLineEdit()
    e.setReadOnly(True)
    e.setFont(QFont("Consolas", 9))
    e.setStyleSheet(
        "background:#050810; color:#44AA88; border:1px solid #1A2A44;"
        " border-radius:2px; padding:0 4px;"
    )
    e.setFixedHeight(22)
    e.setPlaceholderText("等待响应...")
    return e


# ─────────────────────────────────────────────────────────────────────────────
class ControlPanel(QWidget):
    """控制面板：串口配置 + 电机参数下发 + 采集模块参数"""

    # 串口开关
    open_ports_requested  = pyqtSignal(str, int, str, int, float)
    close_ports_requested = pyqtSignal()

    # 单条 Modbus 指令
    send_cmd_a = pyqtSignal(int, bytes)   # motor_id, cmd_bytes
    send_cmd_b = pyqtSignal(bytes)        # cmd_bytes（motor_id 固定为 0）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = load_all_settings()
        self._build()

    # ── 构建 ──────────────────────────────────────────────────────────
    def _build(self):
        root_scroll = QScrollArea(self)
        root_scroll.setWidgetResizable(True)
        root_scroll.setFrameShape(QFrame.NoFrame)
        root_scroll.setStyleSheet("background:#0C1020;")

        inner = QWidget()
        inner.setStyleSheet("background:#0C1020;")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(18, 14, 18, 18)
        vbox.setSpacing(12)

        vbox.addWidget(self._build_serial_group())
        vbox.addWidget(self._build_motor_param_group())
        vbox.addWidget(self._build_current_module_group())
        vbox.addStretch()

        root_scroll.setWidget(inner)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(root_scroll)

    # ── 分区：串口配置 ────────────────────────────────────────────────
    def _build_serial_group(self) -> QGroupBox:
        gb = _make_group("串口配置")
        grid = QGridLayout(gb)
        grid.setSpacing(8)
        grid.setContentsMargins(12, 8, 12, 8)

        def port_combo():
            cb = QComboBox()
            cb.setFixedWidth(120)
            cb.setStyleSheet(
                "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
                " border-radius:2px; padding:0 4px;"
            )
            return cb

        def baud_combo():
            cb = QComboBox()
            cb.addItems(["9600", "19200", "38400", "57600", "115200"])
            cb.setFixedWidth(100)
            cb.setStyleSheet(
                "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
                " border-radius:2px; padding:0 4px;"
            )
            return cb

        # COM_A
        grid.addWidget(_row_label("电机总线 COM_A:"), 0, 0)
        self._combo_a = port_combo()
        grid.addWidget(self._combo_a, 0, 1)
        grid.addWidget(_row_label("波特率:"), 0, 2)
        self._baud_a = baud_combo()
        grid.addWidget(self._baud_a, 0, 3)

        # COM_B
        grid.addWidget(_row_label("采集模块 COM_B:"), 1, 0)
        self._combo_b = port_combo()
        grid.addWidget(self._combo_b, 1, 1)
        grid.addWidget(_row_label("波特率:"), 1, 2)
        self._baud_b = baud_combo()
        grid.addWidget(self._baud_b, 1, 3)

        # 比例系数
        grid.addWidget(_row_label("电流比例系数:"), 2, 0)
        self._scale_edit = QLineEdit(str(self._cfg.get("current_scale", 1.0)))
        self._scale_edit.setFixedWidth(80)
        self._scale_edit.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        grid.addWidget(self._scale_edit, 2, 1)

        # 刷新 / 打开 / 关闭
        btn_row = QHBoxLayout()
        self._btn_refresh = QPushButton("刷新端口")
        self._btn_refresh.setStyleSheet(styles.BTN_PRIMARY)
        self._btn_refresh.setFixedSize(90, 28)
        self._btn_refresh.clicked.connect(self._refresh_ports)
        self._btn_open = QPushButton("打开串口")
        self._btn_open.setStyleSheet(styles.BTN_SERIAL_OPEN)
        self._btn_open.setFixedSize(90, 28)
        self._btn_open.clicked.connect(self._open_ports)
        self._btn_close = QPushButton("关闭串口")
        self._btn_close.setStyleSheet(styles.BTN_SERIAL_CLOSE)
        self._btn_close.setFixedSize(90, 28)
        self._btn_close.clicked.connect(self.close_ports_requested)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addWidget(self._btn_open)
        btn_row.addWidget(self._btn_close)
        btn_row.addStretch()
        grid.addLayout(btn_row, 3, 0, 1, 4)

        self._refresh_ports()
        return gb

    # ── 分区：电机控制器参数 (COM_A) ─────────────────────────────────
    def _build_motor_param_group(self) -> QGroupBox:
        gb = _make_group("电机控制器 (COM_A) 参数设置")
        vbox = QVBoxLayout(gb)
        vbox.setSpacing(8)
        vbox.setContentsMargins(12, 8, 12, 8)

        # 目标电机 ID
        r0 = QHBoxLayout()
        r0.addWidget(_row_label("目标电机 ID:"))
        self._motor_id_spin = QSpinBox()
        self._motor_id_spin.setRange(1, 20)
        self._motor_id_spin.setFixedWidth(70)
        self._motor_id_spin.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        r0.addWidget(self._motor_id_spin)
        r0.addStretch()
        vbox.addLayout(r0)

        # 设置通讯控制模式 M34
        r1 = QHBoxLayout()
        r1.addWidget(_row_label("通讯控制模式:"))
        btn_mode = QPushButton("设置通讯模式 M34")
        btn_mode.setStyleSheet(styles.BTN_PRIMARY)
        btn_mode.setFixedHeight(26)
        btn_mode.clicked.connect(self._cmd_set_comm_mode)
        r1.addWidget(btn_mode)
        r1.addStretch()
        vbox.addLayout(r1)

        # 自定义寄存器写入
        r2 = QHBoxLayout()
        r2.addWidget(_row_label("寄存器地址(hex):"))
        self._reg_addr_edit = QLineEdit("0000")
        self._reg_addr_edit.setFixedWidth(70)
        self._reg_addr_edit.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        r2.addWidget(self._reg_addr_edit)
        lbl_val = QLabel("写入值(hex):")
        lbl_val.setFont(QFont("Microsoft YaHei UI", 9))
        lbl_val.setStyleSheet("color:#6A8A9A; background:transparent;")
        r2.addWidget(lbl_val)
        self._reg_val_edit = QLineEdit("0000")
        self._reg_val_edit.setFixedWidth(70)
        self._reg_val_edit.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        r2.addWidget(self._reg_val_edit)
        btn_write = QPushButton("写入 FC06")
        btn_write.setStyleSheet(styles.BTN_PRIMARY)
        btn_write.setFixedHeight(26)
        btn_write.clicked.connect(self._cmd_write_reg_a)
        r2.addWidget(btn_write)
        r2.addStretch()
        vbox.addLayout(r2)

        # 回显
        r3 = QHBoxLayout()
        r3.addWidget(_row_label("响应 (COM_A):"))
        self._resp_a = _resp_edit()
        r3.addWidget(self._resp_a)
        vbox.addLayout(r3)

        return gb

    # ── 分区：电流采集模块参数 (COM_B) ───────────────────────────────
    def _build_current_module_group(self) -> QGroupBox:
        gb = _make_group("电流采集模块 (COM_B) 参数设置")
        vbox = QVBoxLayout(gb)
        vbox.setSpacing(8)
        vbox.setContentsMargins(12, 8, 12, 8)

        # 修改设备地址
        row_addr = QHBoxLayout()
        row_addr.addWidget(_row_label("新设备地址:"))
        self._new_addr_spin = QSpinBox()
        self._new_addr_spin.setRange(1, 247)
        self._new_addr_spin.setValue(1)
        self._new_addr_spin.setFixedWidth(70)
        self._new_addr_spin.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        row_addr.addWidget(self._new_addr_spin)
        btn_set_addr = QPushButton("修改地址")
        btn_set_addr.setStyleSheet(styles.BTN_PRIMARY)
        btn_set_addr.setFixedHeight(26)
        btn_set_addr.clicked.connect(self._cmd_set_addr)
        row_addr.addWidget(btn_set_addr)
        row_addr.addStretch()
        vbox.addLayout(row_addr)

        # 修改波特率
        row_baud = QHBoxLayout()
        row_baud.addWidget(_row_label("通信波特率:"))
        self._baud_mod_combo = QComboBox()
        self._baud_mod_combo.addItems(["4800", "9600", "19200", "38400"])
        self._baud_mod_combo.setCurrentIndex(1)
        self._baud_mod_combo.setFixedWidth(100)
        self._baud_mod_combo.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        row_baud.addWidget(self._baud_mod_combo)
        btn_set_baud = QPushButton("修改波特率")
        btn_set_baud.setStyleSheet(styles.BTN_PRIMARY)
        btn_set_baud.setFixedHeight(26)
        btn_set_baud.clicked.connect(self._cmd_set_baud)
        row_baud.addWidget(btn_set_baud)
        row_baud.addStretch()
        vbox.addLayout(row_baud)

        # 更新速度
        row_speed = QHBoxLayout()
        row_speed.addWidget(_row_label("数据更新速度:"))
        self._update_speed_combo = QComboBox()
        self._update_speed_combo.addItems(["400ms", "300ms", "240ms", "160ms", "100ms"])
        self._update_speed_combo.setCurrentIndex(0)
        self._update_speed_combo.setFixedWidth(100)
        self._update_speed_combo.setStyleSheet(
            "background:#050810; color:#7AAAC0; border:1px solid #1A2A44;"
            " border-radius:2px; padding:0 4px;"
        )
        row_speed.addWidget(self._update_speed_combo)
        btn_set_speed = QPushButton("设置更新速度")
        btn_set_speed.setStyleSheet(styles.BTN_PRIMARY)
        btn_set_speed.setFixedHeight(26)
        btn_set_speed.clicked.connect(self._cmd_set_update_speed)
        row_speed.addWidget(btn_set_speed)
        row_speed.addStretch()
        vbox.addLayout(row_speed)

        # 读取全部通道
        row_read = QHBoxLayout()
        btn_read_all = QPushButton("读取全部 24 路电流数据 (FC03)")
        btn_read_all.setStyleSheet(styles.BTN_PRIMARY)
        btn_read_all.setFixedHeight(28)
        btn_read_all.clicked.connect(self._cmd_read_all_channels)
        row_read.addWidget(btn_read_all)
        row_read.addStretch()
        vbox.addLayout(row_read)

        # 回显
        row_resp = QHBoxLayout()
        row_resp.addWidget(_row_label("响应 (COM_B):"))
        self._resp_b = _resp_edit()
        row_resp.addWidget(self._resp_b)
        vbox.addLayout(row_resp)

        return gb

    # ── 串口动作 ──────────────────────────────────────────────────────
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        for cb in (self._combo_a, self._combo_b):
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(ports)
            idx = cb.findText(cur)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            cb.blockSignals(False)

    def _open_ports(self):
        try:
            scale = float(self._scale_edit.text())
        except ValueError:
            scale = 1.0
        baud_map = {"9600": 9600, "19200": 19200, "38400": 38400,
                    "57600": 57600, "115200": 115200}
        self.open_ports_requested.emit(
            self._combo_a.currentText(),
            baud_map.get(self._baud_a.currentText(), 9600),
            self._combo_b.currentText(),
            baud_map.get(self._baud_b.currentText(), 9600),
            scale
        )
        cfg = {
            "com_a": self._combo_a.currentText(),
            "baud_a": self._baud_a.currentText(),
            "com_b": self._combo_b.currentText(),
            "baud_b": self._baud_b.currentText(),
            "current_scale": scale,
        }
        save_all_settings(cfg)

    # ── 电机 Modbus 指令 ──────────────────────────────────────────────
    def _cmd_set_comm_mode(self):
        mid = self._motor_id_spin.value()
        # FC06 写寄存器 0x0097 = 0x0022
        cmd = modbus_utils.cmd_write_register(mid, 0x0097, 0x0022)
        self.send_cmd_a.emit(mid, cmd)

    def _cmd_write_reg_a(self):
        mid = self._motor_id_spin.value()
        try:
            addr = int(self._reg_addr_edit.text().strip(), 16)
            val  = int(self._reg_val_edit.text().strip(), 16)
        except ValueError:
            return
        cmd = modbus_utils.cmd_write_register(mid, addr, val)
        self.send_cmd_a.emit(mid, cmd)

    # ── 采集模块 Modbus 指令 ──────────────────────────────────────────
    def _cmd_set_addr(self):
        new_addr = self._new_addr_spin.value()
        # 寄存器 0x0050 = 设备地址（对当前地址 0x01 下发）
        cmd = modbus_utils.cmd_write_register(0x01, 0x0050, new_addr)
        self.send_cmd_b.emit(cmd)

    def _cmd_set_baud(self):
        baud_code = self._baud_mod_combo.currentIndex()  # 0=4800,1=9600,2=19200,3=38400
        cmd = modbus_utils.cmd_write_register(0x01, 0x0051, baud_code)
        self.send_cmd_b.emit(cmd)

    def _cmd_set_update_speed(self):
        speed_code = self._update_speed_combo.currentIndex()  # 0-4
        cmd = modbus_utils.cmd_write_register(0x01, 0x004F, speed_code)
        self.send_cmd_b.emit(cmd)

    def _cmd_read_all_channels(self):
        # FC03 从寄存器 0x0000 读 24 个寄存器
        cmd = modbus_utils.cmd_read_registers(0x01, 0x0000, 24)
        self.send_cmd_b.emit(cmd)

    # ── 响应回显 slot ─────────────────────────────────────────────────
    @pyqtSlot(str, int, bytes)
    def show_response(self, port_name: str, motor_id: int, data: bytes):
        hex_str = " ".join(f"{b:02X}" for b in data)
        if port_name == "COM_A":
            self._resp_a.setText(f"#{motor_id:02d}  {hex_str}")
        else:
            self._resp_b.setText(hex_str)
