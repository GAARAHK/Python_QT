# -*- coding: gbk -*-
"""
电流采集管理器 —— 接收 MotorController 的 request_current 信号，
向 COM_B 发送 Modbus FC03 指令，并将结果回注给对应的 MotorController。
"""
from PyQt5.QtCore import QObject, pyqtSignal
from modbus_utils import cmd_read_one_channel, parse_current_response

EXPECT_BYTES = 7   # 单路返回报文长度


class CurrentCollector(QObject):
    """
    采集请求分发器。
    - 连接 SerialScheduler 的 data_received 信号接收原始字节。
    - 将结果通过 current_result 信号发回。
    """
    current_result = pyqtSignal(int, int, float)   # (motor_id, loop_count, value)

    def __init__(self, scheduler, port_name: str = "COM_B",
                 scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scheduler  = scheduler
        self._port_name  = port_name
        self._scale      = scale
        # 记录 motor_id → loop_count 的待回填映射
        self._pending: dict[int, int] = {}

        scheduler.data_received.connect(self._on_data_received)

    def request(self, motor_id: int, channel: int, loop_count: int):
        """由 MotorController.request_current 信号触发"""
        self._pending[motor_id] = loop_count
        cmd = cmd_read_one_channel(channel)
        # motor_id 作为标识，expect_bytes=EXPECT_BYTES 触发等待
        self._scheduler.put(self._port_name, motor_id, cmd,
                            expect_bytes=EXPECT_BYTES, retries=1)

    def _on_data_received(self, port_name: str, motor_id: int, raw: bytes):
        if port_name != self._port_name:
            return
        value = parse_current_response(raw, self._scale)
        if value is None:
            return
        loop_count = self._pending.pop(motor_id, 0)
        self.current_result.emit(motor_id, loop_count, value)
