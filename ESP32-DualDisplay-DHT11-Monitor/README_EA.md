# ESP32 DHT11 + OpenSynaptic 传感器数据处理器

## 📋 功能介绍

EA.py 是一个智能传感器数据处理脚本，集成了 OpenSynaptic 库来处理从 ESP32 DH11 传感器收集的温度和湿度数据。

**主要功能：**
- 🔗 从 ESP32 WiFi API 获取实时传感器数据
- 🌡️ 提取温度（°C）和湿度（%）数据配对
- 🔧 使用 OpenSynaptic 进行数据标准化（UCUM 单位规范）
- 📦 数据压缩（Base62 编码，减少 60-80% 的数据量）
- 📊 支持多种输出格式和显示模式

---

## 🚀 快速开始

### 1️⃣ 演示模式（无需 ESP32）

最简单的方式 - 使用模拟数据查看脚本功能：

```bash
python EA.py --demo
```

**输出示例：**
```
======================================================================
🚀 ESP32 DHT11 + OpenSynaptic 智能传感器数据处理器
======================================================================
📍 设备地址: 192.168.4.1
📦 OpenSynaptic: ❌ 未安装
🎯 运行模式: 演示模式（模拟数据）
======================================================================

📊 使用模拟数据演示...

📊 原始 API 数据:
{
  "online": true,
  "alarm": false,
  "temp_c": 23.45,
  "humi_pct": 55.3,
  ...
}

🌡️  传感器数据 [2026-04-22 09:48:34]
  状态: ✅ 在线
  温度: 23.45°C
  湿度: 55.30%

======================================================================
✅ 数据处理完成
======================================================================
```

### 2️⃣ 实时模式（需要 ESP32）

连接到实际的 ESP32 设备：

```bash
# 默认连接到 192.168.4.1（ESP32 默认 AP 地址）
python EA.py

# 或连接到自定义 IP
python EA.py --host 192.168.1.100
```

**需要条件：**
- ESP32 开启 WiFi AP（热点名：`ESP32-DHT11-API`，密码：`12345678`）
- 主机已连接到该 WiFi 热点
- 默认 IP 地址为 `192.168.4.1`

---

## 📦 安装 OpenSynaptic（可选但推荐）

安装后可以使用数据压缩功能。

### ✅ 方式 1：手动安装（推荐）

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装库
pip install opensynaptic requests --upgrade
```

### ❌ 如果遇到权限错误

```bash
pip install opensynaptic requests --upgrade --break-system-packages
```

### 🔍 验证安装

```bash
python -c "import opensynaptic; print('✅ OpenSynaptic 已安装')"
```

### 📧 再次运行脚本

安装后，运行脚本会激活数据压缩功能：

```bash
python EA.py --demo

# 或实时模式
python EA.py
```

此时输出中会显示：
- ✅ OpenSynaptic: 已安装
- 🔧 压缩数据包的详细信息
- 📊 数据包优化情况

---

## 📖 完整用法

```bash
python EA.py [OPTIONS]
```

### 可用选项：

| 选项 | 说明 | 示例 |
|------|------|------|
| `--demo` | 使用模拟数据演示（不需要 ESP32） | `python EA.py --demo` |
| `--install` | 尝试自动安装 OpenSynaptic | `python EA.py --install` |
| `--host` | 指定 ESP32 主机地址 | `python EA.py --host 192.168.1.100` |
| `--help` | 显示帮助信息 | `python EA.py --help` |

### 常见命令：

```bash
# 1. 演示模式
python EA.py --demo

# 2. 连接默认 ESP32
python EA.py

# 3. 连接自定义 IP 的 ESP32
python EA.py --host 192.168.1.50

# 4. 显示帮助
python EA.py --help
```

---

## 📊 输出数据说明

### 原始 API 数据
脚本从 ESP32 的 `/sensor` 端点获取以下信息：

```json
{
  "online": true,              // 传感器是否在线
  "alarm": false,              // 告警状态
  "temp_c": 23.45,            // 温度（摄氏度）
  "humi_pct": 55.30,          // 湿度（百分比）
  "last_ok_ms": 1234567890,   // 上次成功读取时间
  "uptime_ms": 9876543210,    // 系统运行时间
  "cpu_mhz": 240,             // CPU 频率
  "cpu_load_pct": 15,         // CPU 负载
  "heap_free": 102400,        // 可用堆内存
  "heap_used_pct": 45         // 堆内存使用百分比
}
```

### 提取的传感器数据
```
🌡️  传感器数据 [2026-04-22 09:48:34]
  状态: ✅ 在线
  温度: 23.45°C
  湿度: 55.30%
```

### OpenSynaptic 处理结果（安装后）
```
🔧 OpenSynaptic 处理结果:
  压缩数据包（Hex）: a1b2c3d4e5f6...
  数据包大小: 16 字节
  分配 ID: 12345
  压缩策略: DIFF
```

---

## 🔧 故障排除

### ❌ "无法连接到 ESP32"

**原因：**
- ESP32 未启动或不在线
- WiFi 连接不正确
- IP 地址不匹配

**解决方案：**
```bash
# 1. 检查 ESP32 是否在线
ping 192.168.4.1

# 2. 使用演示模式测试脚本功能
python EA.py --demo

# 3. 尝试自定义 IP
python EA.py --host <你的_ESP32_IP>
```

### ❌ "OpenSynaptic 未安装"

**解决方案：**
```bash
# 方式 1：手动安装
pip install opensynaptic

# 方式 2：使用脚本自动安装
python EA.py --install

# 方式 3：如果遇到权限错误
pip install opensynaptic --break-system-packages
```

### ❌ 其他导入错误

**验证环境：**
```bash
python -m venv --help  # 检查虚拟环境支持
source .venv/bin/activate  # 激活虚拟环境
pip list  # 查看已安装的包
```

---

## 📚 OpenSynaptic 库介绍

OpenSynaptic 是一个高性能 IoT 协议栈，具有以下特点：

| 特性 | 说明 |
|------|------|
| **UCUM 标准化** | 自动标准化传感器单位 |
| **Base62 压缩** | 减少 60-80% 的数据量 |
| **多传输支持** | TCP、UDP、MQTT、LoRa、CAN |
| **零复制管道** | 高效的二进制编码 |

### 性能指标
- 处理延迟：~10-20 μs（单传感器）
- 吞吐量：~1.2M ops/s（单核）
- 压缩率：60-80% vs JSON

### 官方资源
- 📖 GitHub: https://github.com/OpenSynaptic/OpenSynaptic
- 📦 PyPI: https://pypi.org/project/opensynaptic/
- 📚 文档: https://opensynaptic.github.io/docs/

---

## 💡 使用提示

### 持续监测模式

如果想要持续监测温度和湿度，可以编辑 EA.py，取消注释最后的循环代码：

```python
# 启用持续监测（每 2 秒获取一次数据）
while True:
    data = fetch_sensor_data()
    if data:
        temp, humi, online = extract_temperature_humidity(data)
        display_sensor_data(temp, humi, online)
    time.sleep(2)
```

### 自定义输出

可以将脚本的输出重定向到文件：

```bash
python EA.py > sensor_log.txt 2>&1
```

### 远程监测

如果需要远程监测，可以定期运行脚本并同步到远程服务器：

```bash
# 使用 cron 定时任务（每 5 分钟运行一次）
*/5 * * * * cd ~/Projects/ESP32 && python EA.py >> sensor.log 2>&1
```

---

## 📝 版本信息

- **脚本版本：** 2.0 (2026-04-22)
- **OpenSynaptic 版本：** 1.4.0+
- **Python 版本：** 3.11+
- **依赖：** requests, opensynaptic (可选)

---

## 📞 获取帮助

```bash
python EA.py --help
```

或查看脚本头部的详细说明。

---

**祝你使用愉快！如有问题，请检查 ESP32 连接和依赖安装。** 🎉
