# -*- coding: gbk -*-
"""
主窗口 v2 —— 竖边栏 + 淡入动画切换 + 新版监控大屏
"""
import sys
import traceback

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame, QMessageBox,
    QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer, pyqtSlot
from PyQt5.QtGui import QFont

import styles
from database import init_db, start_run_batch, end_run_batch
from serial_scheduler import SerialScheduler
from current_collector import CurrentCollector
from motor_controller import MotorController

from ui_overview import OverviewPanel
from ui_control_panel import ControlPanel
from ui_template_editor import TemplateEditor
from ui_query_panel import QueryPanel

TOTAL_MOTORS = 20


# ── 淡入动画堆栈 ──────────────────────────────────────────────────────────
class FadeStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None

    def switch_to(self, idx: int):
        if idx == self.currentIndex():
            return
        widget = self.widget(idx)
        if widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        super().setCurrentIndex(idx)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._anim = anim


# ── 竖边栏导航 ────────────────────────────────────────────────────────────
class NavSidebar(QWidget):
    def __init__(self, stack: FadeStackedWidget, page_names: list, parent=None):
        super().__init__(parent)
        self._stack   = stack
        self._btns: list[QPushButton] = []
        self._current = 0
        self.setFixedWidth(165)
        self.setStyleSheet("background:#060A14;")
        self._build(page_names)

        # 滑块指示器（动画）
        self._slider = QFrame(self)
        self._slider.setFixedSize(3, 48)
        self._slider.setStyleSheet("background:#00AADD; border-radius:1px;")
        self._slider_anim = QPropertyAnimation(self._slider, b"pos")
        self._slider_anim.setDuration(220)
        self._slider_anim.setEasingCurve(QEasingCurve.OutCubic)
        QTimer.singleShot(60, self._init_slider)

    def _build(self, page_names: list):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Logo 区
        logo = QFrame()
        logo.setFixedHeight(64)
        logo.setStyleSheet("background:#040810; border-bottom:1px solid #1A2A44;")
        lb = QVBoxLayout(logo)
        lb.setContentsMargins(14, 8, 0, 8)
        lb.setSpacing(3)
        t1 = QLabel("电机群控系统")
        t1.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        t1.setStyleSheet("color:#00AADD; background:transparent;")
        t2 = QLabel("Motor Control v2.0")
        t2.setFont(QFont("Consolas", 9))
        t2.setStyleSheet("color:#2A4060; background:transparent;")
        lb.addWidget(t1)
        lb.addWidget(t2)
        vbox.addWidget(logo)

        # 导航按钮
        nav = QWidget()
        nav.setStyleSheet("background:transparent;")
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(0, 14, 0, 0)
        nv.setSpacing(0)
        for i, name in enumerate(page_names):
            btn = QPushButton(name)
            btn.setFixedHeight(48)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setStyleSheet(styles.NAV_BTN_QSS)
            btn.clicked.connect(lambda checked, idx=i: self._switch(idx))
            self._btns.append(btn)
            nv.addWidget(btn)
        nv.addStretch()
        vbox.addWidget(nav)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#1A2A44;")
        vbox.addWidget(sep)

        self._status_lbl = QLabel("  串口未连接")
        self._status_lbl.setFixedHeight(32)
        self._status_lbl.setFont(QFont("Microsoft YaHei UI", 9))
        self._status_lbl.setStyleSheet("color:#2A4060; background:transparent; padding-left:12px;")
        vbox.addWidget(self._status_lbl)

    def _init_slider(self):
        if self._btns:
            btn = self._btns[0]
            y = btn.mapTo(self, QPoint(0, 0)).y() + (btn.height() - self._slider.height()) // 2
            self._slider.move(0, y)

    def _switch(self, idx: int):
        if idx == self._current:
            self._btns[idx].setChecked(True)
            return
        self._btns[self._current].setChecked(False)
        self._btns[idx].setChecked(True)
        btn = self._btns[idx]
        y = btn.mapTo(self, QPoint(0, 0)).y() + (btn.height() - self._slider.height()) // 2
        self._slider_anim.setStartValue(self._slider.pos())
        self._slider_anim.setEndValue(QPoint(0, y))
        self._slider_anim.start()
        self._current = idx
        self._stack.switch_to(idx)

    def update_status(self, text: str, connected: bool = False):
        color = "#00AADD" if connected else "#2A4060"
        self._status_lbl.setText(f"  {text}")
        self._status_lbl.setStyleSheet(
            f"color:{color}; background:transparent; padding-left:12px;"
        )


# ── 主窗口 ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("20路电机串口群控与数据采集系统")
        self.setGeometry(60, 40, 1480, 920)

        self._scheduler  = SerialScheduler(self)
        self._collector  = CurrentCollector(self._scheduler, "COM_B", parent=self)
        self._controllers: dict[int, MotorController] = {}
        self._batch_uuids: dict[int, str] = {}

        init_db()
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_h = QHBoxLayout(root)
        root_h.setContentsMargins(0, 0, 0, 0)
        root_h.setSpacing(0)

        self._stack       = FadeStackedWidget()
        self._overview    = OverviewPanel()
        self._ctrl_panel  = ControlPanel()
        self._tmpl_editor = TemplateEditor()
        self._query_panel = QueryPanel()
        for w in (self._overview, self._ctrl_panel,
                  self._tmpl_editor, self._query_panel):
            self._stack.addWidget(w)

        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet("color:#1A2A44; max-width:1px;")

        pages = ["    监控大屏", "    控制面板", "    工况配置", "    数据查询"]
        self._sidebar = NavSidebar(self._stack, pages)

        root_h.addWidget(self._sidebar)
        root_h.addWidget(div)
        root_h.addWidget(self._stack)

        self._status_label = QLabel("系统就绪 | 串口未打开")
        self.statusBar().addPermanentWidget(self._status_label)

    def _connect_signals(self):
        # 监控大屏卡片启停
        self._overview.start_motor_sig.connect(self._start_motor)
        self._overview.stop_motor_sig.connect(self._stop_motor)

        # 串口打开/关闭
        self._ctrl_panel.open_ports_requested.connect(self._open_ports)
        self._ctrl_panel.close_ports_requested.connect(self._close_ports)

        # 单机参数指令路由
        self._ctrl_panel.send_cmd_a.connect(
            lambda mid, cmd: self._scheduler.put("COM_A", mid, cmd, expect_bytes=8, retries=1)
        )
        self._ctrl_panel.send_cmd_b.connect(
            lambda cmd: self._scheduler.put("COM_B", 0, cmd, expect_bytes=8, retries=1)
        )
        self._scheduler.data_received.connect(self._ctrl_panel.show_response)

        # 模板变化 → 更新大屏卡片工况下拉
        self._tmpl_editor.templates_changed.connect(self._overview.refresh_templates)

        # 串口错误
        self._scheduler.error_occurred.connect(self._on_serial_error)

        # 采集结果
        self._collector.current_result.connect(self._on_current_result)

    # ── 串口管理 ──────────────────────────────────────────────────────
    @pyqtSlot(str, int, str, int, float)
    def _open_ports(self, com_a: str, baud_a: int,
                    com_b: str, baud_b: int, scale: float):
        ok_a = self._scheduler.open_port("COM_A", com_a, baud_a)
        ok_b = self._scheduler.open_port("COM_B", com_b, baud_b)
        self._collector._scale = scale
        if ok_a and ok_b:
            status = f"COM_A={com_a}  COM_B={com_b}"
            self._status_label.setText(f"已连接 | {status}")
            self._sidebar.update_status(status, connected=True)
        else:
            failed = []
            if not ok_a:
                failed.append(f"COM_A({com_a})")
            if not ok_b:
                failed.append(f"COM_B({com_b})")
            QMessageBox.critical(self, "串口错误", f"以下串口打开失败：\n{', '.join(failed)}")

    @pyqtSlot()
    def _close_ports(self):
        self._scheduler.close_all()
        self._status_label.setText("串口已关闭")
        self._sidebar.update_status("串口已关闭", connected=False)

    # ── 电机控制 ──────────────────────────────────────────────────────
    @pyqtSlot(int, str, dict)
    def _start_motor(self, motor_id: int, qr_code: str, template: dict):
        # 如果已在运行，先停止
        if motor_id in self._controllers:
            self._controllers[motor_id].stop_motor()
            self._controllers[motor_id].wait(200)

        batch_uuid = start_run_batch(motor_id, qr_code, template["id"])
        self._batch_uuids[motor_id] = batch_uuid

        ctrl = MotorController(motor_id, motor_id, self)
        ctrl.assign_task(qr_code, batch_uuid, template)
        ctrl.state_changed.connect(self._on_state_changed)
        ctrl.loop_updated.connect(self._on_loop_updated)
        ctrl.request_current.connect(self._collector.request)
        ctrl.alarm_triggered.connect(self._on_alarm)
        ctrl.run_finished.connect(self._on_run_finished)
        ctrl.send_cmd.connect(
            lambda mid, cmd: self._scheduler.put("COM_A", mid, cmd)
        )
        self._controllers[motor_id] = ctrl
        ctrl.start()
        self._overview.set_running(motor_id, True)
        self._overview.set_state(motor_id, "FORWARD")

    @pyqtSlot(int)
    def _stop_motor(self, motor_id: int):
        ctrl = self._controllers.get(motor_id)
        if ctrl and ctrl.isRunning():
            ctrl.stop_motor()
        self._overview.set_running(motor_id, False)

    # ── 回调 ──────────────────────────────────────────────────────────
    @pyqtSlot(int, str)
    def _on_state_changed(self, motor_id: int, state: str):
        self._overview.set_state(motor_id, state)

    @pyqtSlot(int, int)
    def _on_loop_updated(self, motor_id: int, count: int):
        self._overview.set_loop(motor_id, count)

    @pyqtSlot(int, int, float)
    def _on_current_result(self, motor_id: int, loop_count: int, value: float):
        ctrl = self._controllers.get(motor_id)
        if ctrl:
            ctrl.inject_current(value)
        self._overview.set_current(motor_id, value)

    @pyqtSlot(int, str, int, float)
    def _on_alarm(self, motor_id: int, qr_code: str, loop_count: int, value: float):
        self._overview.set_state(motor_id, "ALARM")
        self._overview.set_current(motor_id, value, alarmed=True)
        self._overview.set_running(motor_id, False)
        self.statusBar().showMessage(
            f"报警！电机 #{motor_id:02d} [{qr_code}] "
            f"第{loop_count}次循环电流 {value:.2f}A 超限，已自动停机",
            10000
        )

    @pyqtSlot(int, str)
    def _on_run_finished(self, motor_id: int, status: str):
        batch_uuid = self._batch_uuids.get(motor_id, "")
        if batch_uuid:
            end_run_batch(batch_uuid, status)
        self._overview.set_running(motor_id, False)
        if status == "completed":
            self._overview.set_state(motor_id, "COMPLETED")

    @pyqtSlot(str, str)
    def _on_serial_error(self, port_name: str, msg: str):
        self.statusBar().showMessage(f"串口错误 [{port_name}]: {msg}", 8000)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "退出确认", "确定退出？运行中的电机将被停止。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for ctrl in self._controllers.values():
                ctrl.stop_motor()
                ctrl.wait(300)
            self._scheduler.close_all()
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    def _exception_hook(t, v, tb):
        traceback.print_exception(t, v, tb)
        sys.exit(1)
    sys.excepthook = _exception_hook

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(styles.DARK_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
