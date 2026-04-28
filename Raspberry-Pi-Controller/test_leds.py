#!/usr/bin/env python3
"""
LED 硬件诊断脚本
依次点亮每个 LED 3 秒，确认 Pi→Arduino 串口通信正常。
运行：python3 test_leds.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import time, serial
from osrx_tx import OSTXSensor, serial_emit

PORT = "/dev/ttyUSB1"
BAUD = 9600
GAP  = 0.10   # 100ms 帧间隙，保证 Arduino 15ms 空闲检测有足够余量

print(f"打开串口 {PORT} @ {BAUD} bps ...")
port = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)   # 等待 Arduino 复位完成
print("串口已就绪，开始测试\n")

ac  = OSTXSensor(agent_id=0x00000001, sensor_id="AC",  unit="md")
win = OSTXSensor(agent_id=0x00000001, sensor_id="WIN", unit="st")
alm = OSTXSensor(agent_id=0x00000001, sensor_id="ALM", unit="st")
emit = serial_emit(port)


def reset_all():
    ac.send(scaled=0, emit=emit);  time.sleep(GAP)
    win.send(scaled=0, emit=emit); time.sleep(GAP)
    alm.send(scaled=0, emit=emit); time.sleep(GAP)


# ── 全灭 ────────────────────────────────────────────────────────
print("全灭 ...")
reset_all()
time.sleep(1)

# ── 制热：红灯 D5 ───────────────────────────────────────────────
print("▶ AC=heat  → D5 红灯 亮 3s")
ac.send(scaled=10000, emit=emit)
time.sleep(3)
reset_all()

# ── 制冷：蓝灯 D4 ───────────────────────────────────────────────
print("▶ AC=cool  → D4 蓝灯 亮 3s")
ac.send(scaled=20000, emit=emit)
time.sleep(3)
reset_all()

# ── 开窗：黄灯 D3 ───────────────────────────────────────────────
print("▶ WIN=open → D3 黄灯 亮 3s  (D2 绿灯 灭)")
win.send(scaled=10000, emit=emit)
time.sleep(3)
reset_all()

# ── 报警：白灯 D6 ───────────────────────────────────────────────
print("▶ ALM=on   → D6 白灯 亮 3s")
alm.send(scaled=10000, emit=emit)
time.sleep(3)
reset_all()

print("\n全部测试完成，全灭。")
port.close()
