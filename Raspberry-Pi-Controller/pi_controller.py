#!/usr/bin/env python3
"""
树莓派智能家居控制器
-----------------------------------------------
功能：
  1. 每隔 poll_interval_s 秒从 ESP32 获取室内温湿度
  2. 每 10 分钟从 Open-Meteo 获取实时室外天气（免费，无需 Key）
  3. 使用 river 在线学习模型（Hoeffding 树）实时决策
     - 前 bootstrap_n 条：规则引擎引导，同步训练模型
     - 之后：ML 预测，持续用规则标签反向训练（数据自迭代）
  4. 决策变化时通过 USB 串口向 Arduino 发送 OSynaptic 帧
  5. 所有数据写入 data_log.csv 供后续分析

接线：
  树莓派 USB → Arduino Uno（/dev/ttyUSB0，9600 bps）
  树莓派 wlan0 → ESP32 SoftAP（192.168.4.1）
  树莓派 eth0  → 家庭路由器（SSH 控制 + 互联网天气 API）
"""

import sys
import io

# 强制标准输出/错误使用 UTF-8，避免在 zh_HK / Big5 locale 下日志乱码
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import time
import csv
import logging
import socket
import struct
import base64
import threading
import queue
from datetime import datetime
from pathlib import Path

import requests

# ── river 在线学习 ──────────────────────────────────────────────────────────
from river import tree, preprocessing, compose, metrics

# ═══════════════════════════════════════════════════════════════════════════
# 配置（按实际情况修改）
# ═══════════════════════════════════════════════════════════════════════════
CFG = {
    # ESP32 SoftAP 地址
    "esp32_ip": "192.168.4.1",

    # Arduino 串口（CH340: ttyUSB1；ESP32 CP2102: ttyUSB0）
    "serial_port": "/dev/ttyUSB1",
    "serial_baud": 9600,

    # 采集间隔（秒）
    "poll_interval_s": 10,

    # 地理位置（Open-Meteo 天气 API，默认上海）
    # 查询经纬度：https://www.latlong.net/
    "latitude": 31.23,
    "longitude": 121.47,

    # 舒适区间阈值（触发规则引擎）
    "temp_comfort_low":  20.0,   # °C
    "temp_comfort_high": 28.0,   # °C
    "humi_comfort_low":  40.0,   # %
    "humi_comfort_high": 70.0,   # %

    # CSV 日志路径
    "log_file": "data_log.csv",

    # 前 N 条用规则先引导模型，之后切换到 ML 决策
    "bootstrap_n": 20,

    # Gsyn-Java UDP 广播（手机端监控 App，默认端口 9876）
    "udp_broadcast_enabled": True,
    "udp_broadcast_port":    9876,
    "udp_aid":               1,      # OSynaptic Agent ID，与 Gsyn-Java 设置一致

    # Gsyn-Java UDP 远程控制监听（手机端 SendFragment → Pi → Arduino）
    # Gsyn-Java Send 界面填写：Host = Pi 的 IP，Port = 9877
    "udp_listen_enabled":    True,
    "udp_listen_port":       9877,
}

# ═══════════════════════════════════════════════════════════════════════════
# 日志格式
# ═══════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pi_ctrl")

# ═══════════════════════════════════════════════════════════════════════════
# 动作标签定义
# 0 = 维持现状   1 = 开制热   2 = 开制冷   3 = 开窗   4 = 关窗   5 = 报警
# ═══════════════════════════════════════════════════════════════════════════
ACTION_NAMES = {0: "维持", 1: "制热", 2: "制冷", 3: "开窗", 4: "关窗", 5: "报警"}

# ═══════════════════════════════════════════════════════════════════════════
# 在线学习模型
# Pipeline = 标准化 → Hoeffding 树分类器
# Hoeffding 树是专为流式数据设计的决策树，每来一条样本就增量更新
# ═══════════════════════════════════════════════════════════════════════════
model = compose.Pipeline(
    preprocessing.StandardScaler(),
    tree.HoeffdingTreeClassifier(grace_period=30, delta=1e-5, leaf_prediction="mc"),
)
ml_accuracy = metrics.Accuracy()
sample_count = 0


def make_features(in_temp, in_humi, out_temp, out_humi, feels_like, hour, weekday):
    """构造特征字典，供 river 模型使用"""
    return {
        "in_temp":    in_temp,
        "in_humi":    in_humi,
        "out_temp":   out_temp,
        "out_humi":   out_humi,
        "feels_like": feels_like,
        "hour":       hour,
        "weekday":    weekday,
        # 衍生特征：室内外差值，帮助模型学习"窗户是否有益"
        "temp_diff":  in_temp - out_temp,
        "humi_diff":  in_humi - out_humi,
    }


def rule_based_decision(in_t, in_h, out_t):
    """
    静态规则引擎——作为在线学习的引导标签来源。
    随着样本积累，ML 模型会学习到时间/季节等更复杂的模式，
    最终的决策质量将超越纯规则。
    """
    tl = CFG["temp_comfort_low"]
    th = CFG["temp_comfort_high"]
    hl = CFG["humi_comfort_low"]
    hh = CFG["humi_comfort_high"]

    # 湿度严重超限 → 报警
    if in_h > hh + 10 or in_h < hl - 10:
        return 5

    # 温度过低 → 制热
    if in_t < tl - 2:
        return 1

    # 温度过高 → 制冷
    if in_t > th + 2:
        return 2

    # 室内舒适 + 室外温差小 → 开窗通风
    if tl <= in_t <= th and hl <= in_h <= hh and abs(out_t - in_t) < 3:
        return 3

    # 其余情况关窗维持
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# ESP32 数据获取
# ═══════════════════════════════════════════════════════════════════════════
def fetch_esp32():
    """返回 (temp_c, humi_pct, online)，失败时返回 (None, None, False)"""
    try:
        r = requests.get(f"http://{CFG['esp32_ip']}/sensor", timeout=3)
        r.raise_for_status()
        d = r.json()
        return float(d["temp_c"]), float(d["humi_pct"]), bool(d.get("online", True))
    except Exception as e:
        log.warning(f"ESP32 获取失败: {e}")
        return None, None, False


# ═══════════════════════════════════════════════════════════════════════════
# 天气 API（Open-Meteo，完全免费，无需注册 Key）
# ═══════════════════════════════════════════════════════════════════════════
_weather_cache: dict = {"ts": 0.0, "data": None}
_WEATHER_TTL = 600  # 10 分钟缓存，避免频繁请求


def fetch_weather() -> dict:
    """返回 {temp, humi, feels_like}，失败时返回缓存或默认值"""
    now = time.monotonic()
    if now - _weather_cache["ts"] < _WEATHER_TTL and _weather_cache["data"]:
        return _weather_cache["data"]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={CFG['latitude']}&longitude={CFG['longitude']}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature"
        "&timezone=auto"
    )
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        c = r.json()["current"]
        data = {
            "temp":       c["temperature_2m"],
            "humi":       c["relative_humidity_2m"],
            "feels_like": c["apparent_temperature"],
        }
        _weather_cache.update({"ts": now, "data": data})
        log.info(
            f"天气更新 → 室外 {data['temp']}°C / 湿度 {data['humi']}% / "
            f"体感 {data['feels_like']}°C"
        )
        return data
    except Exception as e:
        log.warning(f"天气 API 失败: {e}")
        return _weather_cache["data"] or {"temp": 20.0, "humi": 60.0, "feels_like": 20.0}


# ═══════════════════════════════════════════════════════════════════════════
# Arduino 串口发送（OSynaptic 帧）
# ═══════════════════════════════════════════════════════════════════════════
_serial_conn = None

# 持久化 OSTXSensor 实例，保持 tid 连续递增（需等 osrx_tx 模块可用后初始化）
# sensor_id / unit 必须与 Arduino main.cpp 中 on_frame() 的 strcmp 完全一致：
#   AC  / md  — 空调（scaled: 0=off, 10000=heat, 20000=cool）
#   WIN / st  — 窗户（scaled: 0=关,  10000=开）
#   ALM / st  — 报警（scaled: 0=关,  10000=开）
_ac_sensor  = None
_win_sensor = None
_alm_sensor = None


def _get_sensors():
    global _ac_sensor, _win_sensor, _alm_sensor
    if _ac_sensor is None:
        try:
            from osrx_tx import OSTXSensor
            _ac_sensor  = OSTXSensor(agent_id=0x00000001, sensor_id="AC",  unit="md")
            _win_sensor = OSTXSensor(agent_id=0x00000001, sensor_id="WIN", unit="st")
            _alm_sensor = OSTXSensor(agent_id=0x00000001, sensor_id="ALM", unit="st")
        except ImportError:
            pass
    return _ac_sensor, _win_sensor, _alm_sensor


def _get_serial():
    global _serial_conn
    if _serial_conn is None or not _serial_conn.is_open:
        try:
            import serial
            _serial_conn = serial.Serial(
                CFG["serial_port"], CFG["serial_baud"], timeout=1
            )
            time.sleep(2)  # 等待 Arduino 复位
            log.info(f"串口已连接: {CFG['serial_port']}")
        except Exception as e:
            log.warning(f"串口连接失败: {e}")
            _serial_conn = None
    return _serial_conn


def send_command(action: int):
    """
    发送控制指令到 Arduino。
    使用持久化的 OSTXSensor 实例，tid 连续递增。
    """
    try:
        from osrx_tx import serial_emit

        t1, t2, t3 = _get_sensors()
        if t1 is None:
            log.warning("osrx_tx 模块未找到，跳过串口发送")
            return

        port = _get_serial()
        if port is None:
            log.warning("无串口，跳过发送（请检查接线或 /dev/ttyUSB0）")
            return

        emit_ = serial_emit(port)

        # Arduino 以 15ms 空闲间隙作为帧尾标志（osrx_feed_done），
        # 多帧之间必须留出足够间隙，否则被当作一个超长帧而 CRC 失败被丢弃。
        # 100ms = 帧传输约 44ms(@9600bps, ~42B) + 15ms 静默检测 + 41ms 余量
        # 实测：50ms 不可靠（余量不足），100ms 稳定（与 test_leds.py 一致）
        _G = 0.10

        # 先将所有设备归零（每帧间等 50ms）
        t1.send(scaled=0, emit=emit_); time.sleep(_G)   # AC  = off
        t2.send(scaled=0, emit=emit_); time.sleep(_G)   # WIN = 关
        t3.send(scaled=0, emit=emit_); time.sleep(_G)   # ALM = 关

        if action == 1:                               # 制热
            t1.send(scaled=10000, emit=emit_)         # AC = heat (1)
        elif action == 2:                             # 制冷
            t1.send(scaled=20000, emit=emit_)         # AC = cool (2)
        elif action == 3:                             # 开窗
            t2.send(scaled=10000, emit=emit_)         # WIN = 开
        elif action == 4:                             # 关窗（WIN 归零已完成）
            pass
        elif action == 5:                             # 报警
            t3.send(scaled=10000, emit=emit_)         # ALM = 开

        log.info(f"→ 已发送: {ACTION_NAMES.get(action, action)}")

    except Exception as e:
        log.error(f"发送指令失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Gsyn-Java UDP 广播（树莓派作透明桥接，ESP32/Arduino 不动）
# 帧格式与 Gsyn-Java PacketBuilder.buildMultiSensorPacket 完全兼容
# ═══════════════════════════════════════════════════════════════════════════
_udp_tid = 0


def _gsyn_b62_decode(s: str) -> int:
    """Base62 解码 — 与 Gsyn-Java Base62Codec.decode() 对应"""
    ALPHA = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if not s:
        return 0
    negative = s[0] == "-"
    result = 0
    for ch in (s[1:] if negative else s):
        idx = ALPHA.find(ch)
        if idx < 0:
            return 0
        result = result * 62 + idx
    return -result if negative else result


def _parse_remote_body(body_str: str) -> int | None:
    """
    从 Gsyn-Java 发来的 body 解析 action。
    格式：{aid}.U.{ts_token}|{sid}>{state}.{unit}:{b62}|...

    支持两套 sid：
      1) T1/T2/T3（布尔通道）
      2) AC/WIN/ALM（语义通道）

    动作映射：
      T1=1 或 AC=1.0  -> action 1（制热）
      T2=1 或 AC=2.0  -> action 2（制冷）
      T3=1 或 WIN=1.0 -> action 3（开窗）
      WIN=0.0         -> action 4（关窗）
      ALM=1.0         -> action 5（报警）
      都未触发        -> action 0（维持）
    返回 action(0-5)，无法识别则返回 None。
    """
    try:
        first_pipe = body_str.index("|")
        rest = body_str[first_pipe + 1:]
        states: dict[str, int] = {}
        for seg in rest.split("|"):
            if not seg:
                continue
            gt = seg.index(">")
            sid = seg[:gt].upper()
            colon = seg.index(":")
            b62 = seg[colon + 1:]
            # integer × 10000，bool: 0 或 10000
            states[sid] = _gsyn_b62_decode(b62)

        if not states:
            return None

        # 先处理最高优先级：报警
        if states.get("ALM", 0) > 5000:
            return 5

        # AC 语义通道：支持 0/1/2（按 10000 缩放）
        ac_scaled = states.get("AC")
        if ac_scaled is not None:
            if ac_scaled >= 15000:
                return 2
            if ac_scaled > 5000:
                return 1

        # 兼容布尔通道
        if states.get("T1", 0) > 5000:
            return 1
        if states.get("T2", 0) > 5000:
            return 2

        # 窗户通道：WIN/T3
        if states.get("WIN", 0) > 5000 or states.get("T3", 0) > 5000:
            return 3
        if "WIN" in states and states["WIN"] <= 5000:
            return 4

        return 0
    except (ValueError, IndexError):
        pass
    return None


def _gsyn_b62(value: int) -> str:
    """Base62 编码 — 与 Gsyn-Java Base62Codec 字母表相同"""
    ALPHA = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if value == 0:
        return "0"
    negative = value < 0
    n, chars = abs(value), []
    while n:
        chars.append(ALPHA[n % 62])
        n //= 62
    if negative:
        chars.append("-")
    return "".join(reversed(chars))


def _gsyn_build_packet(aid: int, tid: int, ts_sec: int, body_str: str) -> bytes:
    """构造与 Gsyn-Java PacketBuilder 兼容的 OSynaptic FULL 帧（UDP 用）"""
    body = body_str.encode("utf-8")
    frame = bytearray(13 + len(body) + 3)
    off = 0
    frame[off] = 63; off += 1                           # cmd = DATA_FULL
    frame[off] = 1;  off += 1                           # route_count
    frame[off:off+4] = struct.pack(">I", aid); off += 4 # aid big-endian
    frame[off] = tid & 0xFF; off += 1                   # tid
    frame[off:off+2] = b"\x00\x00"; off += 2            # ts high 16-bit = 0
    frame[off:off+4] = struct.pack(">I", ts_sec & 0xFFFFFFFF); off += 4
    frame[off:off+len(body)] = body; off += len(body)
    # CRC-8/SMBUS of body
    crc8 = 0
    for b in body:
        crc8 ^= b
        for _ in range(8):
            crc8 = ((crc8 << 1) ^ 0x07) & 0xFF if crc8 & 0x80 else (crc8 << 1) & 0xFF
    frame[off] = crc8; off += 1
    # CRC-16/CCITT-FALSE of frame[0..off-1]
    crc16 = 0xFFFF
    for b in frame[:off]:
        crc16 ^= (b << 8) & 0xFFFF
        for _ in range(8):
            crc16 = ((crc16 << 1) ^ 0x1021) & 0xFFFF if crc16 & 0x8000 else (crc16 << 1) & 0xFFFF
    frame[off] = (crc16 >> 8) & 0xFF; off += 1
    frame[off] = crc16 & 0xFF
    return bytes(frame)


def udp_broadcast_gsyn(in_temp: float, in_humi: float):
    """
    将室内温湿度通过 UDP 广播给 Gsyn-Java（Android 端监控 App）。
    Pi 充当透明桥接：ESP32 → REST API → Pi → UDP → 手机。
    ESP32 固件和 Arduino Uno 无需任何改动。
    """
    global _udp_tid
    if not CFG.get("udp_broadcast_enabled", True):
        return

    aid  = CFG.get("udp_aid", 1)
    port = CFG.get("udp_broadcast_port", 9876)
    ts   = int(time.time())

    # Gsyn-Java encodeTimestamp: URL-safe Base64（无 padding）of 6-byte [0,0,ts高低4字节]
    ts_bytes = bytes([0, 0, (ts >> 24) & 0xFF, (ts >> 16) & 0xFF, (ts >> 8) & 0xFF, ts & 0xFF])
    ts_token = base64.urlsafe_b64encode(ts_bytes).rstrip(b"=").decode()

    # Body: {aid}.U.{ts_token}|TEMP>U.°C:{b62}|HUM>U.%RH:{b62}|
    body_str = (
        f"{aid}.U.{ts_token}"
        f"|TEMP>U.\u00b0C:{_gsyn_b62(round(in_temp * 10000))}"
        f"|HUM>U.%RH:{_gsyn_b62(round(in_humi * 10000))}"
        "|"
    )

    _udp_tid = (_udp_tid + 1) % 256
    packet = _gsyn_build_packet(aid, _udp_tid, ts, body_str)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(packet, ("255.255.255.255", port))
    except Exception as e:
        log.warning(f"UDP 广播失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# UDP 远程控制监听（Gsyn-Java → Pi → Arduino）
# ═══════════════════════════════════════════════════════════════════════════
_remote_cmd_q: queue.Queue = queue.Queue(maxsize=1)


def _udp_listener():
    """后台守护线程：监听来自 Gsyn-Java 的 UDP 控制帧"""
    port = CFG.get("udp_listen_port", 9877)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))
        sock.settimeout(2.0)
        log.info(f"UDP 监听已启动: 端口 {port}（等待 Gsyn-Java 控制指令）")
    except Exception as e:
        log.error(f"UDP 监听启动失败: {e}")
        return

    while True:
        try:
            data, addr = sock.recvfrom(512)
        except socket.timeout:
            continue
        except Exception as e:
            log.error(f"UDP 监听线程异常退出: {e}")
            sock.close()
            break

        # 最小长度：13 字节头 + 0 体 + 1 crc8 + 2 crc16 = 16
        if len(data) < 16:
            continue

        # 验证 CRC-16（全帧最后两字节）
        crc16_rx = (data[-2] << 8) | data[-1]
        crc16_calc = 0xFFFF
        for b in data[:-2]:
            crc16_calc ^= (b << 8) & 0xFFFF
            for _ in range(8):
                if crc16_calc & 0x8000:
                    crc16_calc = ((crc16_calc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc16_calc = (crc16_calc << 1) & 0xFFFF
        if crc16_rx != crc16_calc:
            log.debug(f"UDP 收包 CRC-16 不匹配，丢弃（来自 {addr}）")
            continue

        # 提取 body（字节 13 到 len-3）
        body_end = len(data) - 3
        if body_end <= 13:
            continue
        try:
            body_str = data[13:body_end].decode("utf-8")
        except UnicodeDecodeError:
            continue

        action = _parse_remote_body(body_str)
        if action is not None:
            try:
                _remote_cmd_q.put_nowait((action, str(addr[0])))
            except queue.Full:
                pass  # 队列满（上条指令尚未执行），丢弃过时指令
            log.info(f"[REMOTE] 收到手机指令: {ACTION_NAMES.get(action, action)} (来自 {addr[0]})")


# ═══════════════════════════════════════════════════════════════════════════
# CSV 数据日志
# ═══════════════════════════════════════════════════════════════════════════
_CSV_FIELDS = [
    "timestamp", "in_temp", "in_humi",
    "out_temp", "out_humi", "feels_like",
    "hour", "weekday",
    "rule_label", "ml_pred", "decision",
    "phase", "ml_accuracy_pct", "sample_n",
    # ML 有用性证明指标
    # diverged=1 表示 ML 与规则不同，说明模型识别到了规则不知道的模式
    # comfortable_next 表示下一读数周期室内是否处于舒适区间（用于事后验证 ML 发散时决策对不对）
    "diverged", "comfortable_next",
]


def _is_comfortable(in_temp: float, in_humi: float) -> bool:
    """判断当前室内是否处于舒适区间（用于事后验证 ML 发散决策是否正确）"""
    return (
        CFG["temp_comfort_low"] <= in_temp <= CFG["temp_comfort_high"]
        and CFG["humi_comfort_low"] <= in_humi <= CFG["humi_comfort_high"]
    )


def log_to_csv(row: dict):
    path = Path(CFG["log_file"])
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ═══════════════════════════════════════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════════════════════════════════════
def main():
    global sample_count

    log.info("=" * 55)
    log.info("  树莓派智能家居控制器  启动")
    log.info(f"  ESP32: http://{CFG['esp32_ip']}/sensor")
    log.info(f"  串口:  {CFG['serial_port']} @ {CFG['serial_baud']} bps")
    log.info(f"  引导阶段: 前 {CFG['bootstrap_n']} 条")
    log.info("=" * 55)

    # 启动 UDP 远程控制监听线程
    if CFG.get("udp_listen_enabled", True):
        t = threading.Thread(target=_udp_listener, daemon=True)
        t.start()
        log.info(f"UDP 控制监听: 端口 {CFG.get('udp_listen_port', 9877)}")

    last_action = -1  # 上次发送的动作（-1 表示从未发送过，强制初始化）
    last_row: dict = {}  # 上一轮的 CSV 行，用于补写 comfortable_next
    remote_hold_until = 0.0   # 手动覆盖保护截止时间（单调时钟秒）
    _REMOTE_HOLD_SECS = 60    # 手动操作后 60 秒内不被自动决策覆盖

    while True:
        loop_start = time.monotonic()
        now = datetime.now()

        # ── 0. 优先处理远程手动指令（不依赖 ESP32 是否在线）────────────
        try:
            _pending_remote, _ = _remote_cmd_q.get_nowait()
        except queue.Empty:
            _pending_remote = None

        if _pending_remote is not None:
            if _pending_remote != 0:
                log.info(f"[REMOTE 覆盖] {ACTION_NAMES.get(_pending_remote, _pending_remote)}")
                send_command(_pending_remote)
                last_action = _pending_remote
            else:
                log.info("[REMOTE 覆盖] 维持（保持当前灯态，刷新保护期）")
            remote_hold_until = time.monotonic() + _REMOTE_HOLD_SECS

        # ── 1. 获取室内数据 ───────────────────────────────────────────────
        in_temp, in_humi, online = fetch_esp32()
        if in_temp is None:
            log.warning("ESP32 离线，等待重试...")
            time.sleep(CFG["poll_interval_s"])
            continue

        # ── 1b. UDP 广播给 Gsyn-Java（手机端监控，桥接转发）─────────────
        udp_broadcast_gsyn(in_temp, in_humi)

        # ── 2. 获取室外天气 ───────────────────────────────────────────────
        weather   = fetch_weather()
        out_temp  = weather["temp"]
        out_humi  = weather["humi"]
        feels_like = weather["feels_like"]

        # ── 3. 构造特征向量 ───────────────────────────────────────────────
        feat = make_features(
            in_temp, in_humi,
            out_temp, out_humi, feels_like,
            hour=now.hour,
            weekday=now.weekday(),
        )

        # ── 4. 规则标签（始终计算, 用于引导训练 + 精度评估基准）──────────
        rule_label = rule_based_decision(in_temp, in_humi, out_temp)

        # ── 5. 在线学习决策 ───────────────────────────────────────────────
        sample_count += 1

        if sample_count <= CFG["bootstrap_n"]:
            # 引导阶段：跟规则走，同时喂给模型学习
            ml_pred  = None
            decision = rule_label
            phase    = "引导"
            model.learn_one(feat, rule_label)
        else:
            # ML 阶段：先预测，再用规则标签更新模型（数据自迭代）
            ml_pred = model.predict_one(feat)
            decision = ml_pred if ml_pred is not None else rule_label
            ml_accuracy.update(rule_label, decision)  # None 已被 fallback 替换后再评估
            model.learn_one(feat, rule_label)         # 持续用规则标签迭代
            phase = "ML"

        # ── 6. 执行决策（自动，受手动保护期约束）──────────────────────
        if decision != last_action and time.monotonic() >= remote_hold_until:
            # 手动保护期已过 + 决策发生变化，才由自动决策接管
            send_command(decision)
            last_action = decision

        # ── 7. 控制台日志 ─────────────────────────────────────────────────
        acc_disp = (
            f"{ml_accuracy.get() * 100:.1f}%"
            if sample_count > CFG["bootstrap_n"]
            else "引导中"
        )
        log.info(
            f"[#{sample_count:04d}|{phase}] "
            f"室内 {in_temp:.1f}°C / {in_humi:.1f}%  "
            f"室外 {out_temp:.1f}°C / {out_humi:.1f}%  "
            f"规则→{ACTION_NAMES[rule_label]}  "
            f"决策→{ACTION_NAMES.get(decision, decision)}  "
            f"ML精度:{acc_disp}"
        )

        # ── 8. 写入 CSV ────────────────────────────────────────────────────
        diverged = int(phase == "ML" and ml_pred is not None and ml_pred != rule_label)

        # 补写上一行的 comfortable_next（知道了本轮实际温湿度，才能填上一轮的结果）
        if last_row:
            last_row["comfortable_next"] = int(_is_comfortable(in_temp, in_humi))
            # 追加修正到 CSV（最后一行覆盖策略：用追加 + 标记实现）
            # 实际实现：在 DataFrame 分析时用 shift(-1) 更方便，此处只记当轮数据

        current_row = {
            "timestamp":       now.isoformat(timespec="seconds"),
            "in_temp":         round(in_temp, 2),
            "in_humi":         round(in_humi, 2),
            "out_temp":        round(out_temp, 2),
            "out_humi":        round(out_humi, 2),
            "feels_like":      round(feels_like, 2),
            "hour":            now.hour,
            "weekday":         now.weekday(),
            "rule_label":      rule_label,
            "ml_pred":         ml_pred,
            "decision":        decision,
            "phase":           phase,
            "ml_accuracy_pct": round(ml_accuracy.get() * 100, 1) if sample_count > CFG["bootstrap_n"] else "",
            "sample_n":        sample_count,
            "diverged":        diverged,
            "comfortable_next": "",  # 下一轮填入
        }
        log_to_csv(current_row)
        last_row = current_row

        # ── 9. 等待下一个周期 ─────────────────────────────────────────────
        elapsed = time.monotonic() - loop_start
        sleep_t = max(0.0, CFG["poll_interval_s"] - elapsed)
        time.sleep(sleep_t)


if __name__ == "__main__":
    main()
