#!/bin/bash
# EA.py 快速启动脚本
# 用法：./run-ea.sh [选项]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv/bin/python"

# 检查虚拟环境
if [ ! -f "$VENV_PATH" ]; then
    echo "❌ 虚拟环境不存在，请先创建："
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install requests"
    exit 1
fi

echo "📊 ESP32 DHT11 + OpenSynaptic 传感器数据处理器"
echo "=============================================="
echo ""

# 显示可用命令
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]] || [[ -z "$1" ]]; then
    echo "用法: ./run-ea.sh [命令] [选项]"
    echo ""
    echo "命令："
    echo "  demo          演示模式（使用模拟数据，无需 ESP32）"
    echo "  run           实时模式（连接到 ESP32）"
    echo "  install       尝试自动安装 OpenSynaptic"
    echo "  help          显示此帮助信息"
    echo ""
    echo "高级用法:"
    echo "  ./run-ea.sh run --host 192.168.1.100   连接到自定义 IP"
    echo "  ./run-ea.sh demo                        使用模拟数据演示"
    echo ""
    exit 0
fi

# 执行命令
case "$1" in
    demo)
        echo "🎯 运行模式: 演示模式（模拟数据）"
        echo ""
        $VENV_PATH "$SCRIPT_DIR/EA.py" --demo
        ;;
    run)
        shift
        echo "🎯 运行模式: 实时模式"
        echo ""
        $VENV_PATH "$SCRIPT_DIR/EA.py" "$@"
        ;;
    install)
        echo "⚙️  尝试安装 OpenSynaptic..."
        echo ""
        $VENV_PATH "$SCRIPT_DIR/EA.py" --install
        ;;
    help)
        $VENV_PATH "$SCRIPT_DIR/EA.py" --help
        ;;
    *)
        # 默认实时模式
        $VENV_PATH "$SCRIPT_DIR/EA.py" "$@"
        ;;
esac
