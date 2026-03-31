# -*- coding: gbk -*-
"""
Modbus RTU CRC16 工具 & 通用串口指令构建
"""
import struct


def crc16(data: bytes) -> bytes:
    """计算 Modbus RTU CRC16，返回低字节在前的 2 字节"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc)


def build_write_single(device_id: int, reg_addr: int, value: int) -> bytes:
    """构建 Modbus FC06 写单个寄存器报文"""
    payload = struct.pack('>BBHH', device_id, 0x06, reg_addr, value)
    return payload + crc16(payload)


def build_read_holding(device_id: int, start_reg: int, count: int) -> bytes:
    """构建 Modbus FC03 读保持寄存器报文"""
    payload = struct.pack('>BBHH', device_id, 0x03, start_reg, count)
    return payload + crc16(payload)


def verify_crc(data: bytes) -> bool:
    """验证接收报文 CRC 是否正确"""
    if len(data) < 3:
        return False
    received_crc = data[-2:]
    calculated_crc = crc16(data[:-2])
    return received_crc == calculated_crc


# ── 电机控制指令 ──────────────────────────────────────────────────────────
def cmd_motor_forward(device_id: int) -> bytes:
    """电机正转"""
    return build_write_single(device_id, 0x0000, 0x0001)


def cmd_motor_reverse(device_id: int) -> bytes:
    """电机反转"""
    return build_write_single(device_id, 0x0000, 0x0002)


def cmd_motor_stop(device_id: int) -> bytes:
    """电机停止"""
    return build_write_single(device_id, 0x0000, 0x0000)


def cmd_set_comm_mode(device_id: int) -> bytes:
    """设置为通讯控制模式 M34"""
    return build_write_single(device_id, 0x0097, 0x0022)


# ── 电流采集指令 ──────────────────────────────────────────────────────────
CURRENT_COLLECTOR_ID = 0x01  # 电流采集模块固定地址


def cmd_read_one_channel(channel: int) -> bytes:
    """读取指定通道电流（channel: 1~24，对应寄存器 0x0000~0x0017）"""
    reg = channel - 1
    return build_read_holding(CURRENT_COLLECTOR_ID, reg, 1)


def parse_current_response(data: bytes, scale: float = 1.0) -> float | None:
    """
    解析电流采集模块单路返回报文，返回实际电流值（A 或 mA，取决于硬件量程）
    期望格式: [ID, 0x03, 0x02, HH, LL, CRC_L, CRC_H]
    """
    if len(data) < 7:
        return None
    if not verify_crc(data):
        return None
    raw = struct.unpack('>H', data[3:5])[0]
    return raw * scale


# ── 通用别名（供 ui_control_panel 直接调用）─────────────────────────────
def cmd_write_register(device_id: int, reg_addr: int, value: int) -> bytes:
    """FC06 写单个寄存器（build_write_single 的别名）"""
    return build_write_single(device_id, reg_addr, value)


def cmd_read_registers(device_id: int, start_reg: int, count: int) -> bytes:
    """FC03 读保持寄存器（build_read_holding 的别名）"""
    return build_read_holding(device_id, start_reg, count)
