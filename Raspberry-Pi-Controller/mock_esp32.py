#!/usr/bin/env python3
"""
模拟 ESP32 REST API，用于不接硬件时测试 pi_controller.py 的全部逻辑。

用法：
  1. 在终端 A 运行：python3 mock_esp32.py
  2. 修改 pi_controller.py 的 CFG["esp32_ip"] = "127.0.0.1:8080"
  3. 在终端 B 运行：python3 pi_controller.py

温度每分钟缓慢变化，模拟真实传感器波动。
"""

import json
import math
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# 仿真参数（可随意调整）
BASE_TEMP = 24.0   # 基础温度 °C
BASE_HUMI = 58.0   # 基础湿度 %
AMPLITUDE = 4.0    # 波动幅度 °C
PERIOD_S  = 120    # 波动周期秒数（2 分钟/周期）


def _current_reading():
    t = time.time()
    temp = BASE_TEMP + AMPLITUDE * math.sin(2 * math.pi * t / PERIOD_S)
    humi = BASE_HUMI + 8.0   * math.cos(2 * math.pi * t / PERIOD_S)
    return round(temp, 1), round(humi, 1)


class ESP32Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/sensor", "/sensor/"):
            temp, humi = _current_reading()
            payload = json.dumps({"temp_c": temp, "humi_pct": humi, "online": True})
            body = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # 只打印温湿度，减少噪音
        if "/sensor" in (args[0] if args else ""):
            temp, humi = _current_reading()
            print(f"  [mock] GET /sensor  →  {temp}°C / {humi}%")


if __name__ == "__main__":
    HOST, PORT = "127.0.0.1", 8080
    server = HTTPServer((HOST, PORT), ESP32Handler)
    print(f"Mock ESP32 API 运行中: http://{HOST}:{PORT}/sensor")
    print("温度波动范围:", BASE_TEMP - AMPLITUDE, "~", BASE_TEMP + AMPLITUDE, "°C")
    print("按 Ctrl+C 停止\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
