# 🚀 EA.py 快速开始指南

## 你数据处理脚本已准备就绪！

### 📁 新增文件

创建了以下文件：

1. **EA.py** - 主要脚本
   - 从 ESP32 获取温度和湿度数据
   - 集成 OpenSynaptic 库进行数据处理
   - 支持演示模式、实时模式和自动安装

2. **README_EA.md** - 完整使用文档
   - 详细的功能介绍
   - 完整的安装指南
   - 故障排除方案

3. **run-ea.sh** - 快速启动脚本
   - 便捷的 shell 包装
   - 快捷命令支持

4. **QUICKSTART_EA.md**（本文件）- 快速开始指南

---

## ⚡ 最快 30 秒开始

### 1️⃣ 演示模式（立即可用）

```bash
python EA.py --demo
```

输出示例：
```
🌡️  传感器数据 [2026-04-22 09:49:28]
  状态: ✅ 在线
  温度: 23.45°C
  湿度: 55.30%
```

### 2️⃣ 实时模式（需要 ESP32）

当 ESP32 连接时：

```bash
python EA.py
```

### 3️⃣ 安装 OpenSynaptic（可选）

增强功能 - 数据压缩：

```bash
pip install opensynaptic
python EA.py --demo
```

---

## 📊 脚本功能矩阵

| 功能 | 演示模式 | 实时模式 | 需要 OpenSynaptic |
|------|--------|---------|------------------|
| 显示 API 数据 | ✅ | ✅ | ❌ |
| 提取温度/湿度 | ✅ | ✅ | ❌ |
| 数据标准化 | ✅ | ✅ | ✅ |
| 数据压缩 | ✅ | ✅ | ✅ |
| 连接 ESP32 | ❌ | ✅ | ❌ |

---

## 🎯 主要命令一览

```bash
# 演示模式（最简单，推荐首先尝试）
python EA.py --demo

# 实时模式（连接 ESP32）
python EA.py

# 连接自定义 IP
python EA.py --host 192.168.1.100

# 显示帮助
python EA.py --help

# 尝试自动安装 OpenSynaptic
python EA.py --install
```

---

## 📦 依赖项

### 已安装
- ✅ **requests** - HTTP 请求库（已安装）

### 可选
- ⚠️ **opensynaptic** - IoT 协议栈（可选但推荐）

### 安装可选依赖

```bash
# 方式 1: 常规方法
pip install opensynaptic

# 方式 2: 如果遇到权限错误
pip install opensynaptic --break-system-packages
```

---

## 🔍 验证安装

```bash
# 检查脚本是否可运行
python EA.py --help

# 运行演示
python EA.py --demo

# 检查 OpenSynaptic（可选）
python -c "import opensynaptic; print('✅ OpenSynaptic 已安装')"
```

---

## 📈 数据输出示例

### 原始 JSON 数据
```json
{
  "online": true,
  "alarm": false,
  "temp_c": 23.45,
  "humi_pct": 55.30,
  ...
}
```

### 格式化输出
```
🌡️  传感器数据 [2026-04-22 09:49:28]
  状态: ✅ 在线
  温度: 23.45°C
  湿度: 55.30%
```

### OpenSynaptic 处理（安装后）
```
🔧 OpenSynaptic 处理结果:
  压缩数据包（Hex）: a1b2c3d4...
  数据包大小: 16 字节
  分配 ID: 12345
  压缩策略: DIFF
```

---

## 🐛 常见问题

### Q: 无法连接到 ESP32？
**A:** 这是正常的 - 设备不在线。使用演示模式：
```bash
python EA.py --demo
```

### Q: 如何连接真实 ESP32？
**A:** 
1. 确保 ESP32 开启 WiFi AP
2. 连接到 `ESP32-DHT11-API` 热点
3. 运行 `python EA.py`

### Q: OpenSynaptic 无法自动安装？
**A:** 手动安装：
```bash
pip install opensynaptic --break-system-packages
```

### Q: 如何持续监测数据？
**A:** 编辑 EA.py，取消注释最后的循环代码，或使用 cron 定时任务。

---

## 📚 详细文档

更多信息请查看：

- 📖 [README_EA.md](README_EA.md) - 完整使用指南
- 🔧 脚本本身有详细注释 - `python EA.py --help`

---

## 🎓 OpenSynaptic 简介

OpenSynaptic 是高性能 IoT 协议栈，提供：

- **UCUM 标准化** - 自动规范化传感器单位
- **Base62 压缩** - 减少 60-80% 的数据量
- **多传输支持** - TCP、UDP、MQTT、LoRa、CAN
- **高性能** - 1.2M ops/s 吞吐量

官方网站：https://github.com/OpenSynaptic/OpenSynaptic

---

## ✅ 下一步

### 立即体验

```bash
python EA.py --demo
```

### 然后尝试

```bash
# 安装增强功能
pip install opensynaptic

# 再次运行演示看完整功能
python EA.py --demo
```

### 最后连接 ESP32

```bash
python EA.py
```

---

**祝你使用愉快！🎉**

有问题？运行 `python EA.py --help` 查看完整帮助。
