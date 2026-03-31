# -*- coding: gbk -*-
"""
电机状态机 + 控制线程
每路电机对应一个 MotorController 实例，运行在独立 QThread 中。
"""
import time
from enum import Enum, auto
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


class MotorState(Enum):
    IDLE = auto()
    FORWARD = auto()
    REVERSE = auto()
    STOPPED_BETWEEN = auto()
    ALARM = auto()
    COMPLETED = auto()


class MotorController(QThread):
    """
    单路电机状态机线程。
    通过信号向主线程汇报状态，禁止直接操作 UI。
    """
    # 信号定义 ──────────────────────────────────────────────────────────────
    state_changed    = pyqtSignal(int, str)          # (motor_id, state_name)
    loop_updated     = pyqtSignal(int, int)           # (motor_id, current_loop)
    request_current  = pyqtSignal(int, int, int)      # (motor_id, channel, loop_count) → 请求采集线程读电流
    alarm_triggered  = pyqtSignal(int, str, int, float)  # (motor_id, qr_code, loop, value)
    run_finished     = pyqtSignal(int, str)           # (motor_id, status)
    send_cmd         = pyqtSignal(int, bytes)         # (motor_id, cmd_bytes) → 发给串口调度器

    def __init__(self, motor_id: int, channel: int, parent=None):
        super().__init__(parent)
        self.motor_id = motor_id        # 1~20，也是 Modbus 设备 ID
        self.channel  = channel         # 电流采集通道，1~20
        self._mutex   = QMutex()

        # 运行参数（由外部 assign_task 注入）
        self.qr_code          = ""
        self.batch_uuid       = ""
        self.steps            = []      # [{"action": "forward"|"reverse"|"stop", "duration_s": N}]
        self.target_loops     = 0
        self.collect_interval = 10
        self.alarm_min        = 0.0
        self.alarm_max        = 99.0

        self._stop_flag   = False
        self._current_loop = 0
        self._state       = MotorState.IDLE

        # 外部注入电流结果（线程安全）
        self._pending_current: float | None = None

    # ────────────────────────────────────────────────────────────────────
    def assign_task(self, qr_code: str, batch_uuid: str, template: dict):
        """绑定任务参数，必须在 start() 前调用"""
        with QMutexLocker(self._mutex):
            self.qr_code          = qr_code
            self.batch_uuid       = batch_uuid
            self.steps            = template["steps"]
            self.target_loops     = template["target_loops"]
            self.collect_interval = template["collect_interval"]
            self.alarm_min        = template["alarm_min"]
            self.alarm_max        = template["alarm_max"]
            self._stop_flag       = False
            self._current_loop    = 0

    def stop_motor(self):
        """外部请求停止"""
        with QMutexLocker(self._mutex):
            self._stop_flag = True

    def inject_current(self, value: float):
        """由采集线程回调，注入电流读数"""
        with QMutexLocker(self._mutex):
            self._pending_current = value

    # ────────────────────────────────────────────────────────────────────
    def run(self):
        """状态机主循环"""
        from modbus_utils import cmd_motor_forward, cmd_motor_reverse, cmd_motor_stop

        while not self._should_stop():
            if self._current_loop >= self.target_loops:
                self._set_state(MotorState.COMPLETED)
                self.run_finished.emit(self.motor_id, "completed")
                return

            self._current_loop += 1
            self.loop_updated.emit(self.motor_id, self._current_loop)

            need_collect = (self._current_loop % self.collect_interval == 0)

            for step in self.steps:
                if self._should_stop():
                    break

                action     = step.get("action", "stop")
                duration_s = float(step.get("duration_s", 1))

                # 发送控制指令
                if action == "forward":
                    self._set_state(MotorState.FORWARD)
                    self.send_cmd.emit(self.motor_id, cmd_motor_forward(self.motor_id))
                elif action == "reverse":
                    self._set_state(MotorState.REVERSE)
                    self.send_cmd.emit(self.motor_id, cmd_motor_reverse(self.motor_id))
                else:
                    self._set_state(MotorState.STOPPED_BETWEEN)
                    self.send_cmd.emit(self.motor_id, cmd_motor_stop(self.motor_id))

                # 正转阶段且需要采集：等待 2.5 秒后触发采集（避开浪涌）
                collect_done = False
                SURGE_DELAY  = 2.5  # 秒

                elapsed = 0.0
                while elapsed < duration_s:
                    if self._should_stop():
                        break
                    time.sleep(0.1)
                    elapsed += 0.1

                    if (action == "forward" and need_collect
                            and not collect_done
                            and elapsed >= SURGE_DELAY):
                        collect_done = True
                        self._pending_current = None
                        self.request_current.emit(
                            self.motor_id, self.channel, self._current_loop
                        )
                        # 等待采集线程回填（最多等3秒）
                        wait = 0.0
                        while self._pending_current is None and wait < 3.0:
                            time.sleep(0.05)
                            wait += 0.05

                        cur = self._pending_current
                        if cur is not None:
                            self._handle_current_result(cur)
                            if self._state == MotorState.ALARM:
                                return

            # 单次循环结束 → 发送停止
            self.send_cmd.emit(self.motor_id, cmd_motor_stop(self.motor_id))

        # 人工中止
        self.send_cmd.emit(self.motor_id, cmd_motor_stop(self.motor_id))
        self._set_state(MotorState.IDLE)
        self.run_finished.emit(self.motor_id, "manual_stop")

    # ────────────────────────────────────────────────────────────────────
    def _handle_current_result(self, value: float):
        from database import log_current, log_alarm, end_run_batch

        log_current(self.batch_uuid, self.motor_id, self.qr_code,
                    self._current_loop, value)

        if value < self.alarm_min or value > self.alarm_max:
            from modbus_utils import cmd_motor_stop
            self.send_cmd.emit(self.motor_id, cmd_motor_stop(self.motor_id))
            log_alarm(self.batch_uuid, self.motor_id, self.qr_code,
                      self._current_loop, value, self.alarm_min, self.alarm_max)
            end_run_batch(self.batch_uuid, "alarm")
            self._set_state(MotorState.ALARM)
            self.alarm_triggered.emit(
                self.motor_id, self.qr_code, self._current_loop, value
            )

    def _set_state(self, state: MotorState):
        self._state = state
        self.state_changed.emit(self.motor_id, state.name)

    def _should_stop(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._stop_flag
