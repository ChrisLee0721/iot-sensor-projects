#!/usr/bin/env python3
"""
ESP32 DHT11 持久化监控脚本

同时运行两个并行通道：
  • UDP 监听  — 接收 ESP32 主动推送的 OSynaptic-FX 二进制包 (端口 9000)
  • HTTP 轮询 — 定期从 /sensor 获取 JSON 作为备用/校验 (默认每 10s)

日志写入 monitor.log，Ctrl+C 退出。

用法:
  python monitor.py                    # 默认连接 192.168.4.1
  python monitor.py --host 192.168.4.1 --poll 10 --port 9000
  python monitor.py --no-http          # 仅 UDP，不轮询 HTTP
  python monitor.py --no-udp           # 仅 HTTP 轮询
  python monitor.py --log monitor.log  # 指定日志文件
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Optional

# ── 可选依赖 ────────────────────────────────────────────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── 常量 ────────────────────────────────────────────────────────────────────
DEFAULT_HOST = "192.168.4.1"
DEFAULT_PORT = 9000
DEFAULT_POLL = 10.0   # 秒

# ── 日志配置 ────────────────────────────────────────────────────────────────
_log_lock = threading.Lock()

def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("monitor")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


# ── os-node 解码器路径 ───────────────────────────────────────────────────────
def _find_os_node() -> Optional[str]:
    venv_bin = os.path.dirname(sys.executable)
    candidate = os.path.join(venv_bin, "os-node")
    return candidate if os.path.isfile(candidate) else None


OS_NODE = _find_os_node()


def decode_osfx(raw: bytes) -> str:
    """用 os-node decode 解码二进制包，返回解码结果字符串；失败返回 hex 预览。"""
    if OS_NODE:
        try:
            r = subprocess.run(
                [OS_NODE, "decode", raw.hex()],
                capture_output=True, text=True, timeout=5,
            )
            out = r.stdout.strip()
            if r.returncode == 0 and out:
                return out
            err = r.stderr.strip()
            if err:
                return f"[decode err] {err[:100]}"
        except Exception as e:
            return f"[decode exc] {e}"
    preview = raw[:20].hex() + ("..." if len(raw) > 20 else "")
    return f"[hex] {preview}"


# ── UDP 监听线程 ─────────────────────────────────────────────────────────────
def udp_listener(port: int, stop: threading.Event, logger: logging.Logger) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(1.0)

    while not stop.is_set():
        try:
            sock.bind(("", port))
            break
        except OSError as e:
            logger.warning(f"UDP 绑定失败 :{port}: {e}，5s 后重试…")
            time.sleep(5)

    logger.info(f"UDP 监听已启动 → :{port}  "
                f"({'os-node 解码' if OS_NODE else '仅 hex，未找到 os-node'})")

    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(512)
        except socket.timeout:
            continue
        except OSError as e:
            logger.error(f"UDP 接收错误: {e}")
            time.sleep(1)
            continue

        decoded = decode_osfx(data)
        logger.info(f"[UDP] {addr[0]}  {len(data)}B  {decoded}")

    sock.close()
    logger.info("UDP 监听已停止")


# ── HTTP 轮询线程 ────────────────────────────────────────────────────────────
def http_poller(host: str, interval: float,
                stop: threading.Event, logger: logging.Logger) -> None:
    if not HAS_REQUESTS:
        logger.error("HTTP 轮询需要 requests 库: pip install requests")
        return

    url = f"http://{host}/sensor"
    logger.info(f"HTTP 轮询已启动 → {url}  间隔 {interval}s")
    consecutive_fail = 0

    while not stop.is_set():
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            consecutive_fail = 0

            online  = data.get("online", False)
            temp    = data.get("temp_c", -999)
            humi    = data.get("humi_pct", -999)
            alarm   = data.get("alarm", False)
            heap    = data.get("heap_free", 0)
            cpu     = data.get("cpu_load_pct", 0)

            status  = "ALARM" if alarm else ("OK" if online else "OFFLINE")
            if online:
                logger.info(
                    f"[HTTP] {status}  "
                    f"temp={temp:.1f}°C  humi={humi:.1f}%  "
                    f"cpu={cpu}%  heap={heap//1024}KB"
                )
            else:
                logger.warning(f"[HTTP] {status}  传感器离线")

        except requests.exceptions.ConnectionError:
            consecutive_fail += 1
            logger.warning(
                f"[HTTP] 无法连接 {host}（失败 {consecutive_fail} 次），"
                f"请确认已连接 ESP32 WiFi AP"
            )
        except requests.exceptions.Timeout:
            consecutive_fail += 1
            logger.warning(f"[HTTP] 请求超时（失败 {consecutive_fail} 次）")
        except Exception as e:
            consecutive_fail += 1
            logger.error(f"[HTTP] 异常: {e}")

        # 等待下一次轮询，但每秒检查一次 stop 标志
        deadline = time.monotonic() + interval
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(1.0)

    logger.info("HTTP 轮询已停止")


# ── 主入口 ───────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32 DHT11 持久化监控（UDP + HTTP 双通道）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host",   default=DEFAULT_HOST, metavar="IP",
                        help=f"ESP32 地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port",   default=DEFAULT_PORT, type=int, metavar="PORT",
                        help=f"OSynaptic-FX UDP 端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--poll",   default=DEFAULT_POLL, type=float, metavar="秒",
                        help=f"HTTP 轮询间隔秒数（默认 {DEFAULT_POLL}）")
    parser.add_argument("--log",    default="monitor.log", metavar="文件",
                        help="日志文件路径（默认 monitor.log，传空串禁用）")
    parser.add_argument("--no-udp",  dest="no_udp",  action="store_true",
                        help="禁用 UDP 监听")
    parser.add_argument("--no-http", dest="no_http", action="store_true",
                        help="禁用 HTTP 轮询")
    args = parser.parse_args()

    logger = setup_logging(args.log if args.log else "")

    logger.info("=" * 60)
    logger.info("ESP32 DHT11 持久化监控启动")
    logger.info(f"  ESP32 地址   : {args.host}")
    logger.info(f"  UDP 端口     : {args.port}  {'(已禁用)' if args.no_udp else ''}")
    logger.info(f"  HTTP 间隔    : {args.poll}s  {'(已禁用)' if args.no_http else ''}")
    logger.info(f"  日志文件     : {args.log or '(仅终端)'}")
    logger.info(f"  os-node      : {OS_NODE or '未找到（仅 hex 输出）'}")
    logger.info(f"  requests     : {'✅' if HAS_REQUESTS else '❌ 需安装'}")
    logger.info("=" * 60)

    if args.no_udp and args.no_http:
        logger.error("--no-udp 和 --no-http 不能同时使用")
        sys.exit(1)

    stop = threading.Event()
    threads = []

    if not args.no_udp:
        t = threading.Thread(
            target=udp_listener,
            args=(args.port, stop, logger),
            name="udp",
            daemon=True,
        )
        t.start()
        threads.append(t)

    if not args.no_http:
        t = threading.Thread(
            target=http_poller,
            args=(args.host, args.poll, stop, logger),
            name="http",
            daemon=True,
        )
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在停止…")
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=5)
        logger.info("监控已退出")


if __name__ == "__main__":
    main()
