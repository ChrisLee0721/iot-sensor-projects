#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# 智能家居控制器 启动脚本
# 请在运行前手动连接好 ESP32 SoftAP（ESP32-DHT11-API）
# ─────────────────────────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  树莓派智能家居控制器"
echo "============================================"

# 显示当前 IP，便于 App 填写目标地址
PI_IP=$(ip addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)
echo "当前 wlan0 IP: ${PI_IP:-未连接}"
echo "Gsyn-Java Send 目标: ${PI_IP:-?}:9877"
echo "============================================"
echo ""

cd "$PROJECT_DIR"
PYTHONIOENCODING=utf-8 python3 pi_controller.py 2>&1 | tee run.log

echo ""
echo "控制器已停止"
read -r -p "按 Enter 关闭窗口..."
