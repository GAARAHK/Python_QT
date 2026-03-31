# -*- coding: gbk -*-
"""
串口调度器 —— 负责对 COM_A（电机控制）/ COM_B（电流采集）
的串口指令进行有序排队发送，避免 485 总线冲突。
"""
import queue
import threading
import time
import serial
from PyQt5.QtCore import QObject, pyqtSignal


class SerialScheduler(QObject):
    """
    独立线程的串口调度队列。
    - 所有指令放入 put() 即可，内部按 FIFO 有序发送。
    - 超时重发：发送后等待 ACK 超时则重试一次。
    """
    error_occurred = pyqtSignal(str, str)          # (port_name, error_msg)
    data_received  = pyqtSignal(str, int, bytes)   # (port_name, motor_id, raw_bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ports: dict[str, serial.Serial] = {}
        self._queues: dict[str, queue.Queue]  = {}
        self._threads: dict[str, threading.Thread] = {}
        self._running = False

    # ────────────────────────────────────────────────────────────────────
    def open_port(self, name: str, port: str, baudrate: int = 9600,
                  parity: str = 'N', stopbits: int = 1) -> bool:
        try:
            ser = serial.Serial(
                port=port, baudrate=baudrate,
                bytesize=8, parity=parity,
                stopbits=stopbits, timeout=0.5
            )
            self._ports[name]   = ser
            self._queues[name]  = queue.Queue()
            self._running       = True
            t = threading.Thread(
                target=self._worker, args=(name,), daemon=True
            )
            self._threads[name] = t
            t.start()
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(name, str(e))
            return False

    def close_port(self, name: str):
        self._running = False
        if name in self._queues:
            self._queues[name].put(None)   # 哨兵，通知线程退出
        if name in self._threads:
            self._threads[name].join(timeout=2)
        if name in self._ports and self._ports[name].is_open:
            self._ports[name].close()

    def close_all(self):
        for name in list(self._ports.keys()):
            self.close_port(name)

    def put(self, port_name: str, motor_id: int, cmd: bytes,
            expect_bytes: int = 0, retries: int = 1):
        """
        向指定端口队列投递指令。
        motor_id   : 仅用于回调标识
        expect_bytes: 期望返回字节数，0 表示无需等响应
        retries    : 超时重试次数
        """
        if port_name not in self._queues:
            return
        self._queues[port_name].put({
            "motor_id":     motor_id,
            "cmd":          cmd,
            "expect_bytes": expect_bytes,
            "retries":      retries,
        })

    # ────────────────────────────────────────────────────────────────────
    def _worker(self, name: str):
        q   = self._queues[name]
        ser = self._ports[name]

        while True:
            item = q.get()
            if item is None:   # 退出哨兵
                break
            if not ser.is_open:
                continue

            cmd          = item["cmd"]
            motor_id     = item["motor_id"]
            expect_bytes = item["expect_bytes"]
            retries      = item["retries"]

            for attempt in range(retries + 1):
                try:
                    ser.reset_input_buffer()
                    ser.write(cmd)

                    if expect_bytes > 0:
                        resp = ser.read(expect_bytes)
                        if resp:
                            self.data_received.emit(name, motor_id, bytes(resp))
                            break
                        else:
                            if attempt < retries:
                                time.sleep(0.05)
                    else:
                        # 控制指令：发完即可，间隔 20ms 防总线冲突
                        time.sleep(0.02)
                        break
                except serial.SerialException as e:
                    self.error_occurred.emit(name, str(e))
                    break
