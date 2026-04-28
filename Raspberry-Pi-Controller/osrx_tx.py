"""
osrx_tx.py — 纯 Python 实现的 OSynaptic-TX 帧构建器
──────────────────────────────────────────────────────
根据 OpenSynaptic/OSynaptic-RX v1.0.0 C 源码（src/osrx_sensor.c）实现。
兼容 Arduino Uno 上运行的 OSynaptic-RX v1.0.0 解析器。

帧格式（FULL 模式，OSRX_CMD_DATA_FULL = 63）：
  [0]        cmd         = 63
  [1]        route_count = 1
  [2..5]     aid         (big-endian u32)
  [6]        tid         (u8，每发一帧 +1，滚动 0-255)
  [7..12]    timestamp   (big-endian 48-bit，低 32 位为 Unix 秒)
  [13..N-4]  body        = "{aid}.U.{ts_b64}|{sid}>U.{unit}:{b62}|"
  [N-3]      CRC-8/SMBUS  of body  (poly=0x07, init=0x00)
  [N-2..N-1] CRC-16/CCITT-FALSE of packet[0..N-3]  (poly=0x1021, init=0xFFFF)

body 格式（osrx_sensor.c 解析流程）：
  1. 找第一个 '|'，跳过前缀 "{aid}.U.{ts_b64}"
  2. 找 '>'，读取 sensor_id
  3. 找 '.'，跳过 state token (U)
  4. 找 ':'，读取 unit
  5. 找 '|'（或帧尾），读取 b62(scaled)

Base62 字母表（与 OSynaptic-RX 解码器完全一致）：
  0-9  → '0'..'9'
  10-35→ 'a'..'z'
  36-61→ 'A'..'Z'
  负数 → '-' 前缀
"""

import time
import struct
import base64


# ── CRC 算法 ──────────────────────────────────────────────────────────────────

def _crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    """CRC-8/SMBUS，无反射，无最终异或。"""
    crc = init & 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _crc16(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE，无反射，无最终异或。"""
    crc = init & 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ── Base62 编码 ────────────────────────────────────────────────────────────────

_B62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _b62_encode(value: int) -> str:
    """将有符号 32-bit 整数编码为 Base62 字符串（与 OSynaptic-RX 解码器兼容）。"""
    neg = value < 0
    n = abs(value)
    if n == 0:
        return "0"
    digits = []
    while n:
        digits.append(_B62_CHARS[n % 62])
        n //= 62
    if neg:
        digits.append("-")
    return "".join(reversed(digits))


# ── 帧构建 ────────────────────────────────────────────────────────────────────

OSRX_CMD_DATA_FULL = 63
OSRX_VALUE_SCALE   = 10000


def build_frame(
    aid:       int,
    tid:       int,
    sensor_id: str,
    unit:      str,
    scaled:    int,
    ts_sec:    int | None = None,
) -> bytes:
    """
    构建一帧完整的 OSynaptic 二进制帧。

    body 格式（与 osrx_sensor.c / test_parse.c 完全一致）：
      "{aid}.U.{ts_b64}|{sensor_id}>U.{unit}:{b62(scaled)}|"

    参数：
      aid        : agent ID（例如 0x00000001）
      tid        : transaction ID（0-255，调用方负责递增）
      sensor_id  : 传感器名称（"AC" / "WIN" / "ALM"，最长 8 字节）
      unit       : 单位字符串（"md" / "st"，最长 8 字节）
      scaled     : 整数值 × OSRX_VALUE_SCALE（例如 10000 = 1.0）
      ts_sec     : Unix 时间戳秒数（None 时自动取 time.time()）

    返回完整帧字节串。
    """
    if ts_sec is None:
        ts_sec = int(time.time())

    # ts_b64：URL-safe Base64（无 padding）of 6-byte big-endian timestamp
    ts_bytes = bytes([
        0, 0,
        (ts_sec >> 24) & 0xFF,
        (ts_sec >> 16) & 0xFF,
        (ts_sec >>  8) & 0xFF,
         ts_sec        & 0xFF,
    ])
    ts_b64 = base64.urlsafe_b64encode(ts_bytes).rstrip(b"=").decode("ascii")

    # body = "{aid}.U.{ts_b64}|{sensor_id}>U.{unit}:{b62}|"
    body_str = f"{aid}.U.{ts_b64}|{sensor_id}>U.{unit}:{_b62_encode(scaled)}|"
    body = body_str.encode("ascii")

    # 头部（13 字节）
    header = bytes([
        OSRX_CMD_DATA_FULL,          # [0] cmd
        1,                           # [1] route_count
        (aid >> 24) & 0xFF,          # [2] aid MSB
        (aid >> 16) & 0xFF,          # [3]
        (aid >>  8) & 0xFF,          # [4]
         aid        & 0xFF,          # [5] aid LSB
        tid & 0xFF,                  # [6] tid
        # [7..12] timestamp 48-bit big-endian（高 16 位 = 0，低 32 位 = ts_sec）
        0, 0,
        (ts_sec >> 24) & 0xFF,
        (ts_sec >> 16) & 0xFF,
        (ts_sec >>  8) & 0xFF,
         ts_sec        & 0xFF,
    ])

    # CRC-8 of body（1 字节）
    crc8_val  = _crc8(body) if body else 0
    crc8_byte = bytes([crc8_val])

    # 组装完整帧（不含 CRC-16 的部分）
    pre_crc16 = header + body + crc8_byte

    # CRC-16 of pre_crc16（2 字节 big-endian）
    crc16_val = _crc16(pre_crc16)
    crc16_bytes = struct.pack(">H", crc16_val)

    return pre_crc16 + crc16_bytes


# ── 高层 API（模仿 opensynaptic.OSTXSensor）────────────────────────────────────

class OSTXSensor:
    """
    轻量替代 opensynaptic.OSTXSensor。
    用法与原库保持一致：

        ac = OSTXSensor(agent_id=0x00000001, sensor_id="AC", unit="md")
        ac.send(scaled=10000, emit=serial_emit(port))
    """

    def __init__(self, agent_id: int, sensor_id: str, unit: str):
        self.agent_id  = agent_id
        self.sensor_id = sensor_id
        self.unit      = unit
        self._tid      = 0

    def send(self, scaled: int, emit) -> None:
        """构建帧并通过 emit 函数逐字节发送。"""
        frame = build_frame(
            aid=self.agent_id,
            tid=self._tid,
            sensor_id=self.sensor_id,
            unit=self.unit,
            scaled=scaled,
        )
        self._tid = (self._tid + 1) & 0xFF
        emit(frame)


def serial_emit(port) -> "callable":
    """
    返回一个 emit 函数，将帧字节写入 serial.Serial 对象。
    兼容 opensynaptic.serial_emit 的调用签名。
    write 之后立即 flush，确保字节已进入 UART 硬件发送寄存器，
    调用方的 time.sleep() gap 才能被 Arduino 端 osrx_feed_done 正确识别。
    """
    def _emit(data: bytes) -> None:
        port.write(data)
        port.flush()
    return _emit


# ── 自测 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 验证帧结构：构建一帧后自行解码检查 CRC
    frame = build_frame(
        aid=0x00000001, tid=0,
        sensor_id="AC", unit="md", scaled=10000,
        ts_sec=0
    )
    print(f"帧长度: {len(frame)} 字节")
    print(f"帧 HEX: {frame.hex()}")

    # 手动验证 CRC
    body_start = 13
    body_end   = len(frame) - 3
    body       = frame[body_start:body_end]
    print(f"body  : {body.decode()}")

    got_crc8  = frame[-3]
    exp_crc8  = _crc8(body)
    got_crc16 = struct.unpack(">H", frame[-2:])[0]
    exp_crc16 = _crc16(frame[:-2])

    print(f"CRC-8  期望={exp_crc8:02X}  帧内={got_crc8:02X}  {'✓' if exp_crc8 == got_crc8 else '✗'}")
    print(f"CRC-16 期望={exp_crc16:04X}  帧内={got_crc16:04X}  {'✓' if exp_crc16 == got_crc16 else '✗'}")
