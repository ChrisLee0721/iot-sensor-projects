#!/usr/bin/env python3
"""
ESP32 DHT11 传感器持久化监控器 - 使用 OpenSynaptic 库

默认模式（直接运行 python EA.py）:
  双通道持久运行——UDP 监听（OSynaptic-FX 二进制推送）+ HTTP 轮询两路并行

其他用法:
  python EA.py --demo        # 模拟数据演示（无需设备）
  python EA.py --host IP     # 自定义 ESP32 地址
  python EA.py --poll 5      # HTTP 轮询间隔 5 秒（默认 10）
  python EA.py --port 9000   # UDP 端口（默认 9000）
  python EA.py --no-udp      # 仅 HTTP 轮询
  python EA.py --no-http     # 仅接收 UDP 推送
  python EA.py --install     # 安装 OpenSynaptic
"""

import argparse
import ctypes as _ctypes
import importlib
import json
import os
import socket
import sys
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
try:
    from opensynaptic.core import OpenSynaptic as _OpenSynaptic
    HAS_OPENSYNAPTIC = True
except ImportError:
    _OpenSynaptic = None
    HAS_OPENSYNAPTIC = False

DEFAULT_HOST = "192.168.4.1"
DEMO_DATA: Dict = {
    "online": True,
    "alarm": False,
    "temp_c": 23.45,
    "humi_pct": 55.30,
    "last_ok_ms": 1234567890,
    "uptime_ms": 9876543210,
    "cpu_mhz": 240,
    "cpu_load_pct": 15,
    "heap_free": 102400,
    "heap_used_pct": 45,
}


# ---------- 安装辅助 ----------
def try_install_opensynaptic() -> bool:
    """尝试自动安装 OpenSynaptic，成功返回 True。"""
    global HAS_OPENSYNAPTIC, _OpenSynaptic

    print("\n💡 正在尝试安装 OpenSynaptic...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "opensynaptic", "--upgrade",
         "--break-system-packages"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        print("⚠️  自动安装失败，请手动运行: pip install opensynaptic")
        if result.stderr:
            print(f"   错误详情: {result.stderr.strip().splitlines()[-1]}")
        return False

    # 刷新模块缓存后重新导入，使全局符号生效
    try:
        mod = importlib.import_module("opensynaptic.core")
        importlib.invalidate_caches()
        _OpenSynaptic = getattr(mod, "OpenSynaptic")
        HAS_OPENSYNAPTIC = True
        print("✅ OpenSynaptic 安装成功！")
        return True
    except Exception as e:
        print(f"⚠️  安装后导入失败: {e}")
        return False


# ---------- 数据获取 ----------
def fetch_sensor_data(host: str) -> Optional[Dict]:
    """从 ESP32 的 /sensor 端点获取传感器数据。"""
    if not HAS_REQUESTS:
        print("❌ requests 库未安装，运行: pip install requests")
        return None

    url = f"http://{host}/sensor"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectTimeout:
        print(f"❌ 连接超时：ESP32 ({host}) 未响应")
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到 ESP32 ({host})，请检查 WiFi 连接")
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
    return None


# ---------- 数据处理 ----------
def extract_temperature_humidity(data: Dict) -> Tuple[float, float, bool]:
    """从原始数据中提取温度、湿度和在线状态。"""
    return (
        data.get("temp_c", -999.0),
        data.get("humi_pct", -999.0),
        data.get("online", False),
    )


def process_with_opensynaptic(temp: float, humi: float) -> Optional[Dict]:
    """使用 OpenSynaptic 对温度和湿度进行标准化和压缩。"""
    if not HAS_OPENSYNAPTIC or _OpenSynaptic is None:
        return None

    try:
        node = _OpenSynaptic()
        sensors = [
            ["DHT11_TEMP", "OK", temp, "cel"],
            ["DHT11_HUMI", "OK", humi, "%"],
        ]
        packet, aid, strategy = node.transmit(sensors=sensors)
        return {
            "packet_hex": packet.hex() if packet else None,
            "packet_bytes": len(packet) if packet else 0,
            "allocation_id": aid,
            "compression_strategy": strategy,
        }
    except Exception as e:
        print(f"⚠️  OpenSynaptic 处理错误: {e}")
        return None


# ---------- 显示 ----------
def display_raw_data(data: Dict) -> None:
    print("\n📊 原始 API 数据:")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def display_sensor_data(temp: float, humi: float, online: bool) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🌡️  传感器数据 [{ts}]")
    print(f"  状态: {'✅ 在线' if online else '❌ 离线'}")
    if online:
        print(f"  温度: {temp:.2f}°C")
        print(f"  湿度: {humi:.2f}%")
    else:
        print("  传感器离线，无有效数据")


def display_opensynaptic_result(result: Optional[Dict]) -> None:
    if result is None:
        return
    hex_preview = (result["packet_hex"][:32] + "...") if result["packet_hex"] else "无"
    print(f"\n🔧 OpenSynaptic 处理结果:")
    print(f"  压缩数据包（Hex）: {hex_preview}")
    print(f"  数据包大小: {result['packet_bytes']} 字节")
    print(f"  分配 ID:    {result['allocation_id']}")
    print(f"  压缩策略:   {result['compression_strategy']}")


# ---------- OSynaptic-FX Native Decoder (libosfx_decode.so via ctypes) ----------
_OSFX_SO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libosfx_decode.so")
_FUSION_STATE_BYTES = 7680  # sizeof(osfx_fusion_state) on aarch64, compiled with same macros
_MAX_DECODE_SENSORS = 8


class _OsfxSensorOut(_ctypes.Structure):
    _fields_ = [
        ("sensor_id",    _ctypes.c_char * 32),
        ("sensor_state", _ctypes.c_char * 16),
        ("value",        _ctypes.c_double),
        ("unit",         _ctypes.c_char * 24),
        ("geohash_id",   _ctypes.c_char * 32),
        ("supp_msg",     _ctypes.c_char * 128),
        ("url",          _ctypes.c_char * 128),
    ]


_osfx_lib   = None
_osfx_state = None
HAS_OSFX_NATIVE = False


def _init_osfx_native() -> None:
    global _osfx_lib, _osfx_state, HAS_OSFX_NATIVE
    if not os.path.exists(_OSFX_SO):
        return
    try:
        lib = _ctypes.CDLL(_OSFX_SO)
        lib.osfx_fusion_state_init.argtypes = [_ctypes.c_void_p]
        lib.osfx_fusion_state_init.restype = None
        lib.osfx_core_decode_multi_sensor_packet_auto.argtypes = [
            _ctypes.c_void_p,                        # st
            _ctypes.c_char_p, _ctypes.c_size_t,      # packet, packet_len
            _ctypes.c_char_p, _ctypes.c_size_t,      # out_node_id, cap
            _ctypes.c_char_p, _ctypes.c_size_t,      # out_node_state, cap
            _ctypes.c_void_p, _ctypes.c_size_t,      # out_sensors, sensors_cap
            _ctypes.POINTER(_ctypes.c_size_t),        # out_sensor_count
            _ctypes.c_void_p,                         # out_meta (nullable)
        ]
        lib.osfx_core_decode_multi_sensor_packet_auto.restype = _ctypes.c_int
        state = (_ctypes.c_uint8 * _FUSION_STATE_BYTES)()
        lib.osfx_fusion_state_init(state)
        _osfx_lib = lib
        _osfx_state = state
        HAS_OSFX_NATIVE = True
    except Exception:
        pass  # silently fail; will show [raw hex] for OSFX packets


_init_osfx_native()


def _decode_osfx_packet(raw: bytes) -> Optional[Dict]:
    """用 libosfx_decode.so 持久化 fusion_state 解码 OSynaptic-FX 二进制包。
    返回 {s1_id, s1_v, s1_u, ..., sN_id, sN_v, sN_u} 扁平 dict，或 None。
    """
    if not (HAS_OSFX_NATIVE and _osfx_lib is not None and _osfx_state is not None):
        return None
    try:
        nid  = _ctypes.create_string_buffer(64)
        nst  = _ctypes.create_string_buffer(32)
        arr  = (_OsfxSensorOut * _MAX_DECODE_SENSORS)()
        cnt  = _ctypes.c_size_t(0)
        ret  = _osfx_lib.osfx_core_decode_multi_sensor_packet_auto(
            _osfx_state,
            raw, len(raw),
            nid, 64,
            nst, 32,
            arr, _MAX_DECODE_SENSORS,
            _ctypes.byref(cnt),
            None,
        )
        if ret and cnt.value > 0:
            out: Dict = {}
            for i in range(cnt.value):
                s = arr[i]
                out[f"s{i+1}_id"]    = s.sensor_id.decode("utf-8", errors="replace").rstrip("\x00")
                out[f"s{i+1}_v"]     = s.value
                out[f"s{i+1}_u"]     = s.unit.decode("utf-8", errors="replace").rstrip("\x00")
                out[f"s{i+1}_state"] = s.sensor_state.decode("utf-8", errors="replace").rstrip("\x00")
            return out
    except Exception:
        pass
    return None


def _parse_osfx_flat(d: dict) -> Dict[str, Optional[float]]:
    """从 C 解码器返回的 s1_id/s1_v 扁平 dict 提取结构化字段。
    C 编码器做了单位标准化：Cel→K(+273.15)、MHz→Hz(*1e6)，此处还原。"""
    fields: Dict[str, Optional[float]] = {
        "temp": None, "humi": None,
        "cpu_load": None, "cpu_mhz": None,
        "heap_free": None, "heap_used": None,
        "uptime": None, "alarm": None,
    }
    i = 1
    while True:
        if f"s{i}_id" not in d:
            break
        sid = str(d.get(f"s{i}_id", "")).upper()
        val = d.get(f"s{i}_v")
        if val is not None:
            val = float(val)
        if   "DHT11_TEMP"  in sid:
            fields["temp"]      = (val - 273.15) if val is not None else None  # K→°C
        elif "DHT11_HUMI"  in sid: fields["humi"]      = val
        elif "CPU_LOAD"    in sid: fields["cpu_load"]   = val
        elif "CPU_MHZ"     in sid:
            fields["cpu_mhz"]   = (val / 1_000_000.0) if val is not None else None  # Hz→MHz
        elif "HEAP_FREE"   in sid: fields["heap_free"]  = val
        elif "HEAP_USED"   in sid: fields["heap_used"]  = val
        elif "UPTIME"      in sid: fields["uptime"]     = val
        elif "ALARM"       in sid: fields["alarm"]      = val
        i += 1
    return fields


def listen_udp(port: int = 9000) -> None:
    """监听 ESP32 广播的 OSynaptic-FX 二进制数据包，并还原为原始传感器数据。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind(("", port))
    except OSError as e:
        print(f"\n❌ 无法绑定 UDP 端口 {port}: {e}")
        return

    sock.settimeout(1.0)
    print(f"\n📡 监听 UDP :{port} — 等待 ESP32 OSynaptic-FX 广播包 (Ctrl+C 退出)")
    print(f"   解码: {'✅ OpenSynaptic Python 库' if HAS_OPENSYNAPTIC else '❌ 未安装，仅显示 hex（运行 --install）'}\n")

    try:
        while True:
            try:
                data, addr = sock.recvfrom(512)
            except socket.timeout:
                continue

            ts = datetime.now().strftime("%H:%M:%S")
            decoded = _decode_osfx_packet(data)

            if decoded:
                fields = _parse_osfx_flat(decoded)
                temp = fields.get("temp")
                humi = fields.get("humi")

                parts = []
                if temp is not None:
                    parts.append(f"🌡️  {temp:.2f}°C")
                if humi is not None:
                    parts.append(f"💧 {humi:.2f}%")

                if parts:
                    print(f"[{ts}] {addr[0]}  {len(data)}B  →  {' │ '.join(parts)}")
                else:
                    # 无法提取标准字段，显示完整解码结果
                    print(f"[{ts}] {addr[0]}  {len(data)}B  →  {json.dumps(decoded, ensure_ascii=False)}")
            else:
                hex_preview = data[:20].hex() + ("..." if len(data) > 20 else "")
                print(f"[{ts}] {addr[0]}  {len(data)}B  [hex] {hex_preview}")

    except KeyboardInterrupt:
        print("\n\n⛔ 已停止监听")
    finally:
        sock.close()


# ---------- UDP 监听线程 ----------
def _udp_thread(port: int, stop: threading.Event) -> None:
    """同时监听 port(OSFX) 和 port+1(心跳) 两个 socket，任何包都打印原始内容。"""
    ping_port = port + 1  # 9001 — 纯文本心跳

    def _make_sock(p: int) -> Optional[socket.socket]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0)  # 非阻塞，使用 select
        try:
            s.bind(("", p))
            print(f"  ✅ UDP 已绑定 :{p}")
            return s
        except OSError as e:
            print(f"  ❌ UDP bind :{p} 失败: {e}")
            s.close()
            return None

    sock_osfx = sock_ping = None
    while not stop.is_set() and (sock_osfx is None or sock_ping is None):
        if sock_osfx is None:
            sock_osfx = _make_sock(port)
        if sock_ping is None:
            sock_ping = _make_sock(ping_port)
        if sock_osfx is None or sock_ping is None:
            time.sleep(3)

    if sock_osfx is None and sock_ping is None:
        return

    print(f"  ℹ️  监听 :{port}(OSFX) 和 :{ping_port}(心跳)，确保已连接 ESP32 WiFi")

    all_socks = [s for s in (sock_osfx, sock_ping) if s]
    last_seen = time.monotonic()
    HEARTBEAT_INTERVAL = 30

    while not stop.is_set():
        # select 最多等 1 秒
        import select as _sel
        readable, _, _ = _sel.select(all_socks, [], [], 1.0)

        now = time.monotonic()
        if not readable and now - last_seen >= HEARTBEAT_INTERVAL:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] UDP ⏳ 等待中... (30s无包，检查 ESP32 是否在线及 WiFi 连接)")
            last_seen = now

        for s in readable:
            try:
                data, addr = s.recvfrom(2048)
            except OSError:
                continue

            last_seen = time.monotonic()
            ts = datetime.now().strftime("%H:%M:%S")
            src_port = ping_port if s is sock_ping else port

            # 纯文本心跳包（来自 9001）
            if s is sock_ping:
                text = data.decode("utf-8", errors="replace").strip()
                print(f"[{ts}] PING :{src_port} {addr[0]}  {len(data)}B  →  {text}")
                continue

            # OSFX 二进制包（来自 9000）
            hex20 = data[:20].hex()
            decoded = _decode_osfx_packet(data)
            if decoded:
                fields = _parse_osfx_flat(decoded)

                parts = []
                if fields["temp"]      is not None: parts.append(f"🌡️  {fields['temp']:.1f}°C")
                if fields["humi"]      is not None: parts.append(f"💧 {fields['humi']:.1f}%")
                if fields["cpu_load"]  is not None: parts.append(f"⚙️  CPU {fields['cpu_load']:.0f}%")
                if fields["cpu_mhz"]   is not None: parts.append(f"🔢 {fields['cpu_mhz']:.0f}MHz")
                if fields["heap_free"] is not None: parts.append(f"🧠 堆{fields['heap_free']/1024:.0f}KB")
                if fields["heap_used"] is not None: parts.append(f"({fields['heap_used']:.0f}%用)")
                if fields["uptime"]    is not None:
                    up = int(fields["uptime"])
                    parts.append(f"⏱️  {up//3600}h{(up%3600)//60}m{up%60}s")
                if fields["alarm"]     is not None: parts.append(f"🚨 ALARM={'ON' if fields['alarm'] else 'OFF'}")

                if parts:
                    print(f"[{ts}] OSFX {addr[0]}  {len(data)}B  →  {' │ '.join(parts)}")
                else:
                    print(f"[{ts}] OSFX {addr[0]}  {len(data)}B  hex={hex20}  raw={json.dumps(decoded, ensure_ascii=False)}")
            else:
                print(f"[{ts}] OSFX {addr[0]}  {len(data)}B  [raw hex] {hex20}{'...' if len(data)>20 else ''}")

    for s in all_socks:
        s.close()


# ---------- HTTP 轮询线程 ----------
def _http_thread(host: str, interval: float, stop: threading.Event) -> None:
    if not HAS_REQUESTS:
        print("⚠️  HTTP 轮询需要 requests： pip install requests")
        return
    url = f"http://{host}/sensor"
    fail = 0
    while not stop.is_set():
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            fail = 0
            temp, humi, online = extract_temperature_humidity(data)
            ts = datetime.now().strftime("%H:%M:%S")
            status = "✅ ALARM" if data.get("alarm") else ("✅ OK" if online else "❌ OFFLINE")
            if online:
                print(f"[{ts}] HTTP {status}  temp={temp:.1f}°C  humi={humi:.1f}%"
                      f"  cpu={data.get('cpu_load_pct',0)}%  heap={data.get('heap_free',0)//1024}KB")
            else:
                print(f"[{ts}] HTTP {status}  传感器离线")
        except Exception as e:
            fail += 1
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] HTTP ▲失败({fail}) {e}")
        deadline = time.monotonic() + interval
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.5)


# ---------- 单次采集流程 ----------
def run_once(host: str, demo: bool) -> None:
    if demo:
        print("\n📊 使用模拟数据演示...")
        raw_data: Optional[Dict] = DEMO_DATA
    else:
        print("\n⏳ 正在从 ESP32 获取数据...")
        raw_data = fetch_sensor_data(host)

    if raw_data is None:
        print("❌ 无法获取数据")
        if not demo:
            print("💡 提示: 使用 --demo 进行离线演示，或检查 ESP32 连接")
        return

    display_raw_data(raw_data)

    temp, humi, online = extract_temperature_humidity(raw_data)
    display_sensor_data(temp, humi, online)

    if online:
        if HAS_OPENSYNAPTIC:
            print("\n⚙️  使用 OpenSynaptic 进行数据标准化和压缩...")
            display_opensynaptic_result(process_with_opensynaptic(temp, humi))
        else:
            print("\n💡 安装 OpenSynaptic 以启用压缩功能: python EA.py --install")


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32 DHT11 + OpenSynaptic 传感器持久化监控器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--demo",     action="store_true", help="模拟数据演示（无需 ESP32）")
    parser.add_argument("--install",  action="store_true", help="尝试自动安装 OpenSynaptic")
    parser.add_argument("--host",     default=DEFAULT_HOST, metavar="IP",
                        help="ESP32 地址（默认 %(default)s）")
    parser.add_argument("--port",     default=9000, type=int, metavar="PORT",
                        help="UDP 端口（默认 9000）")
    parser.add_argument("--poll",     default=10.0, type=float, metavar="秒",
                        help="HTTP 轮询间隔（默认 10s）")
    parser.add_argument("--no-udp",   dest="no_udp",  action="store_true", help="禁用 UDP 监听")
    parser.add_argument("--no-http",  dest="no_http", action="store_true", help="禁用 HTTP 轮询")
    args = parser.parse_args()

    if args.install:
        try_install_opensynaptic()
        return

    if args.demo:
        run_once(args.host, demo=True)
        return

    # -------- 交互式配置（启动后输入，回车保留默认值） --------
    # 只有在没有通过命令行显式指定参数时才进入引导
    cli_specified = any([
        args.host != DEFAULT_HOST,
        args.port != 9000,
        args.poll != 10.0,
        args.no_udp,
        args.no_http,
    ])

    if not cli_specified:
        print("\n" + "=" * 70)
        print("🚀 ESP32 DHT11 + OpenSynaptic 持久化监控器  —  交互式配置")
        print("=" * 70)
        print("  直接回车使用括号内的默认值\n")

        def _ask(prompt: str, default: str) -> str:
            try:
                val = input(f"  {prompt} [{default}]: ").strip()
                return val if val else default
            except (EOFError, KeyboardInterrupt):
                return default

        host_in = _ask(f"ESP32 地址", args.host)
        args.host = host_in if host_in else args.host

        port_in = _ask("UDP 端口", str(args.port))
        try:
            args.port = int(port_in)
        except ValueError:
            pass

        poll_in = _ask("HTTP 轮询间隔(秒)", str(args.poll))
        try:
            args.poll = float(poll_in)
        except ValueError:
            pass

        udp_in = _ask("启用 UDP 监听? (y/n)", "y" if not args.no_udp else "n")
        args.no_udp = udp_in.lower().startswith("n")

        http_in = _ask("启用 HTTP 轮询? (y/n)", "y" if not args.no_http else "n")
        args.no_http = http_in.lower().startswith("n")

        print()

    print("\n" + "=" * 70)
    print("🚀 ESP32 DHT11 + OpenSynaptic 持久化监控器")
    print("=" * 70)
    print(f"📍 ESP32 地址:   {args.host}")
    print(f"📡 UDP 端口:   {args.port}  {'(已禁用)' if args.no_udp else ''}")
    print(f"🔄 HTTP 间隔:   {args.poll}s  {'(已禁用)' if args.no_http else ''}")
    print(f"📦 OSFX 解码器: {'✅ libosfx_decode.so' if HAS_OSFX_NATIVE else '❌ 未找到'}")
    print(f"🌐 requests:     {'✅ 已安装' if HAS_REQUESTS else '❌ 未安装'}")
    print("=" * 70)
    print("Ctrl+C 退出\n")

    stop = threading.Event()
    threads = []

    if not args.no_udp:
        t = threading.Thread(target=_udp_thread,
                             args=(args.port, stop), daemon=True)
        t.start()
        threads.append(t)
        print(f"📡 UDP 监听已启动 → :{args.port}")

    if not args.no_http:
        t = threading.Thread(target=_http_thread,
                             args=(args.host, args.poll, stop), daemon=True)
        t.start()
        threads.append(t)
        print(f"🔄 HTTP 轮询已启动 → http://{args.host}/sensor")

    print()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n⛔ 正在停止...")
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=3)
        print("已退出")


if __name__ == "__main__":
    main()
