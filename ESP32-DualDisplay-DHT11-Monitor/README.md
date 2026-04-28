# ESP32 双屏 DHT11 监控系统

基于 ESP32 的温湿度监控项目，配备两块 ST7735 TFT 显示屏、DHT11 传感器、内置 Web 服务器、REST API 以及 OSynaptic-FX UDP 数据推送。支持通过按键操作的多页面 UI，以及通过 Python 脚本进行数据监控与分析。

---

## 目录

- [硬件连接](#硬件连接)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [UI 页面说明](#ui-页面说明)
- [REST API](#rest-api)
- [Python 监控工具](#python-监控工具)
- [配置说明](#配置说明)
- [构建与烧录](#构建与烧录)
- [故障排除](#故障排除)

---

## 硬件连接

### ESP32 引脚分配

| 功能 | GPIO |
|------|------|
| DHT11 数据线 | GPIO 4 |
| 报警输出 | GPIO 15 |
| 背光 PWM | GPIO 32 |
| 按键 Up | GPIO 16 |
| 按键 Down | GPIO 17 |
| 按键 OK | GPIO 33 |
| 按键 Back | GPIO 15 |

### TFT 显示屏（TFT1 — VSPI）

| 信号 | GPIO |
|------|------|
| SCK | 18 |
| MOSI | 23 |
| MISO | 19 |
| CS | 5 |
| DC | 21 |
| RST | 22 |

### TFT 显示屏（TFT2 — HSPI）

| 信号 | GPIO |
|------|------|
| SCK | 14 |
| MOSI | 13 |
| MISO | 12 |
| CS | 27 |
| DC | 26 |
| RST | 25 |

### DHT11 接线

```
DHT11 引脚 1 (VCC)  → 3.3V
DHT11 引脚 2 (DATA) → GPIO 4
DHT11 引脚 3 (NC)   → 悬空
DHT11 引脚 4 (GND)  → GND
```

---

## 功能特性

- **双屏显示**：TFT1 显示导航菜单，TFT2 同步显示当前页面内容
- **DHT11 采集**：可配置采样间隔（500 ms ~ 10000 ms），实时读取温度和湿度
- **历史曲线**：保存最近 64 个采样点，以折线图直观呈现趋势
- **报警系统**：独立配置温度 / 湿度上下限，超限时报警输出引脚置高并在屏幕上高亮提示
- **PWM 背光**：亮度可在 0 % ~ 100 % 之间连续调节
- **WiFi AP 模式**：设备自建热点，不依赖外部路由器
- **内置 Web 仪表盘**：浏览器访问即可查看实时数据并修改配置
- **REST API**：提供 JSON 接口，便于第三方集成
- **OSynaptic-FX UDP 推送**：以二进制格式向端口 9000 广播传感器数据
- **NVS 持久化**：所有配置掉电不丢失，存储于 ESP32 非易失性存储

---

## 快速开始

### 1. 烧录固件

```bash
cd ESP32-DualDisplay-DHT11-Monitor
pio run --target upload
```

### 2. 连接 WiFi

设备上电后自动创建热点：

| 项目 | 默认值 |
|------|--------|
| SSID | `ESP32-DHT11-API` |
| 密码 | `12345678` |
| 设备 IP | `192.168.4.1` |

### 3. 打开 Web 仪表盘

在浏览器中访问：`http://192.168.4.1`

### 4. 运行 Python 监控

```bash
# 进入项目目录并激活虚拟环境
cd ESP32-DualDisplay-DHT11-Monitor
source .venv/bin/activate

# 双通道监控（UDP + HTTP）
python monitor.py

# 演示模式（无需连接设备）
python EA.py --demo
```

---

## UI 页面说明

TFT1 作为菜单导航屏，通过 **Up / Down** 按键移动选项，**OK** 进入页面，**Back** 返回菜单。TFT2 同步显示所选页面内容。

| 页面 | 说明 |
|------|------|
| **Live Data** | 实时温湿度数值 + 进度条，报警时背景变红 |
| **Pin Map** | DHT11 引脚接线图 |
| **Sensor State** | CPU 频率、堆内存占用、CPU 负载、报警状态 |
| **Curve** | 最近 64 个采样点的温度（红线）/ 湿度（绿线）折线图 |
| **Settings** | 可编辑所有阈值、背光、WiFi SSID/密码，保存后立即生效 |

### Settings 页面字段

| 字段 | 说明 | 默认值 |
|------|------|--------|
| Temp Low | 温度下限报警阈值 (°C) | 18.0 |
| Temp High | 温度上限报警阈值 (°C) | 32.0 |
| Humi Low | 湿度下限报警阈值 (%) | 30.0 |
| Humi High | 湿度上限报警阈值 (%) | 80.0 |
| Sample ms | DHT11 采样间隔 (ms) | 1200 |
| Brightness | 屏幕背光亮度 (%) | 80 |
| Alarm | 报警开关 | 开启 |
| WiFi SSID | AP 热点名称 | ESP32-DHT11-API |
| WiFi PASS | AP 热点密码（≥8 位） | 12345678 |
| Save+Apply | 保存并立即应用 | — |
| Exit | 退出 Settings 页 | — |

---

## REST API

设备 IP 默认为 `192.168.4.1`，HTTP 服务监听端口 **80**。

### GET /

返回内置 Web 仪表盘 HTML 页面，浏览器可直接操作。

### GET /sensor

返回当前传感器状态（JSON）。

```json
{
  "online": true,
  "alarm": false,
  "temp_c": 24.50,
  "humi_pct": 58.00,
  "last_ok_ms": 12345,
  "uptime_ms": 60000,
  "cpu_mhz": 240,
  "cpu_load_pct": 12,
  "heap_free": 204800,
  "heap_used_pct": 38
}
```

### GET /settings

返回当前配置（JSON）。

```json
{
  "temp_low": 18.0,
  "temp_high": 32.0,
  "humi_low": 30.0,
  "humi_high": 80.0,
  "sample_ms": 1200,
  "brightness": 80,
  "alarm_enable": true,
  "ssid": "ESP32-DHT11-API",
  "pass": "12345678"
}
```

### POST /settings

以 `application/x-www-form-urlencoded` 格式提交，更新配置并保存到 NVS。

**参数（均为可选，仅提交需要修改的字段）：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `temp_low` | float | 温度下限 |
| `temp_high` | float | 温度上限 |
| `humi_low` | float | 湿度下限 |
| `humi_high` | float | 湿度上限 |
| `sample_ms` | int | 采样间隔 (500–10000) |
| `brightness` | int | 背光亮度 (0–100) |
| `alarm_enable` | int | 报警开关 (1=开, 0=关) |
| `ssid` | string | AP 名称（最长 24 字符） |
| `pass` | string | AP 密码（最长 24 字符，≥8 位） |

**示例（curl）：**

```bash
curl -X POST http://192.168.4.1/settings \
  -d "temp_high=30.0&humi_high=75.0&brightness=60"
```

成功返回 HTTP 200，响应体为 `saved`。

---

## Python 监控工具

项目提供两个独立的 Python 监控脚本，均支持 UDP 和 HTTP 双通道。

### monitor.py — 持久化监控

```bash
# 默认模式（连接 192.168.4.1）
python monitor.py

# 指定地址和端口
python monitor.py --host 192.168.4.1 --port 9000 --poll 10

# 仅 UDP（不轮询 HTTP）
python monitor.py --no-http

# 仅 HTTP 轮询（不监听 UDP）
python monitor.py --no-udp

# 指定日志文件
python monitor.py --log monitor.log
```

日志同时输出到终端和 `monitor.log` 文件。

### EA.py — OpenSynaptic 集成监控

```bash
# 演示模式（无需设备，使用模拟数据）
python EA.py --demo

# 实时模式
python EA.py --host 192.168.4.1

# 安装 OpenSynaptic 依赖
python EA.py --install

# 仅接收 UDP 推送
python EA.py --no-http

# 仅 HTTP 轮询
python EA.py --no-udp

# 调整轮询间隔（秒）
python EA.py --poll 5
```

也可以使用 Shell 包装脚本：

```bash
chmod +x run-ea.sh
./run-ea.sh
```

### 依赖安装

```bash
cd ESP32-DualDisplay-DHT11-Monitor
python -m venv .venv
source .venv/bin/activate
pip install requests opensynaptic
```

---

## 配置说明

### platformio.ini

| 选项 | 值 | 说明 |
|------|-----|------|
| `platform` | `espressif32` | Espressif ESP32 平台 |
| `board` | `esp32dev` | 通用 ESP32 开发板 |
| `framework` | `arduino` | Arduino 框架 |
| `monitor_speed` | `115200` | 串口波特率 |
| `build_type` | `release` | 发布优化构建 |

构建标志启用了 `-Os` 体积优化、`-ffunction-sections` / `-fdata-sections` + `--gc-sections` 死代码消除，以及关闭异常和 RTTI 来减小固件体积。

### OSynaptic-FX 编译宏

| 宏 | 值 | 说明 |
|----|----|------|
| `OSFX_FUSION_MAX_ENTRIES` | 16 | 融合条目数上限 |
| `OSFX_ID_MAX_ENTRIES` | 64 | ID 条目数上限 |
| `OSFX_FUSION_MAX_SENSORS` | 8 | 融合传感器数上限 |
| `OSFX_TMPL_MAX_SENSORS` | 8 | 模板传感器数上限 |
| `OSFX_FUSION_MAX_VALS` | 16 | 融合值数上限 |
| `OSFX_FUSION_MAX_TAG_LEN` | 16 | 标签最大长度 |

---

## 构建与烧录

```bash
# 编译
pio run

# 编译并上传
pio run --target upload

# 打开串口监视器
pio device monitor --baud 115200

# 清理构建缓存
pio run --target clean
```

---

## 故障排除

| 症状 | 可能原因 | 解决方法 |
|------|---------|---------|
| 屏幕白屏 / 无显示 | SPI 接线错误 | 对照引脚表重新检查 CS / DC / RST |
| DHT11 显示 `OFFLINE` | 数据线未接或接错 | 确认 DATA 接 GPIO 4，并接上拉电阻（4.7 kΩ） |
| 找不到 WiFi 热点 | AP 启动失败 | 查看串口日志中的 `[API]` 输出 |
| Web 页面无法打开 | 未连接到设备热点 | 先连接 `ESP32-DHT11-API`，再访问 `192.168.4.1` |
| Python 脚本无数据 | requests 未安装 | `pip install requests` |
| UDP 无数据 | 防火墙拦截端口 9000 | 检查本机防火墙规则，或改用 `--no-udp` |
| 保存设置后密码失效 | 密码短于 8 位 | WiFi 密码必须 ≥ 8 个字符 |
