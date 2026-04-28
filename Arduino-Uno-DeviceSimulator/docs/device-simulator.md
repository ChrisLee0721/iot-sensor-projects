# Arduino Uno 设备模拟器 — 技术文档

## 概览

本项目在 Arduino Uno 上模拟智能家居设备（空调、窗户、报警器），通过 LED 直观显示设备状态。指令由树莓派（Pi）单向下发，Uno 只负责接收并执行，不向 Pi 回报任何状态。

```
遥控器 / App / 任何控制来源
           ↓
      树莓派（唯一状态管理者）
           ↓ OSynaptic 二进制帧（单向）
      Arduino Uno（纯执行器）
           ↓
         LED 显示设备状态
```

---

## 硬件接线

| 引脚 | LED 颜色 | 含义 | 亮 = |
|------|---------|------|------|
| D5 | 红 | 空调制热 | `AC=heat` |
| D4 | 蓝 | 空调制冷 | `AC=cool` |
| D3 | 黄 | 窗户开启 | `WIN=1` |
| D2 | 绿 | 窗户关闭 | `WIN=0`（默认上电即亮）|
| D6 | 白 | 报警 | `ALM=1` |

> 每颗 LED 串联 220Ω 限流电阻接 GND。

---

## 通信协议

### 传输层

| 参数 | 值 |
|------|-----|
| 接口 | UART（`/dev/ttyUSB0`，CH340）|
| 波特率 | 9600 bps |
| 方向 | **仅 Pi → Uno（单向）**，Uno 不回复 |
| 帧格式 | OSynaptic FULL 二进制帧 |
| 库 | [OSynaptic-RX v1.0.0](https://github.com/OpenSynaptic/OSynaptic-RX) |

### 帧边界检测

Uno 使用 **15 ms 空闲间隙** 作为帧尾标志：串口连续收到字节时持续喂给解析器，超过 15 ms 无新字节则调用 `osrx_feed_done()` 触发解析。

### CRC 校验

每帧包含双重校验，任一失败即静默丢弃：
- **CRC-8/SMBUS**（body 段）
- **CRC-16/CCITT-FALSE**（整帧）

---

## 指令约定（Pi 发送端必须遵守）

Pi 使用 OSynaptic-TX 库或 OpenSynaptic Python hub 构造帧，以下为字段约定：

### 空调控制（sensor_id = `"AC"`）

| unit | scaled 值 | 含义 |
|------|-----------|------|
| `"md"` | `0` | 空调关闭 |
| `"md"` | `10000` | 制热模式 |
| `"md"` | `20000` | 制冷模式 |

> `scaled` 为整数，真实值 = `scaled / OSRX_VALUE_SCALE`（默认 10000）。

### 窗户控制（sensor_id = `"WIN"`）

| unit | scaled 值 | 含义 |
|------|-----------|------|
| `"st"` | `0` | 窗户关闭 |
| `"st"` | `10000` | 窗户开启 |

### 报警控制（sensor_id = `"ALM"`）

| unit | scaled 值 | 含义 |
|------|-----------|------|
| `"st"` | `0` | 报警关闭 |
| `"st"` | `10000` | 报警触发 |

---

## Pi 端发送示例

### Python（使用 OpenSynaptic Python hub）

```python
from opensynaptic import OSTXSensor, serial_emit
import serial, time

port = serial.Serial("/dev/ttyUSB0", 9600)
emit = serial_emit(port)

# 开启制热
ac = OSTXSensor(agent_id=0x00000001, sensor_id="AC", unit="md")
ac.send(scaled=10000, emit=emit)   # heat

# 打开窗户
win = OSTXSensor(agent_id=0x00000001, sensor_id="WIN", unit="st")
win.send(scaled=10000, emit=emit)  # open

# 触发报警
alm = OSTXSensor(agent_id=0x00000001, sensor_id="ALM", unit="st")
alm.send(scaled=10000, emit=emit)  # alarm on
```

### C（使用 OSynaptic-TX，API C 流式）

```c
#include <OSynaptic-TX.h>

OSTX_STATIC_DEFINE(s_ac,  0x00000001UL, "AC",  "md");
OSTX_STATIC_DEFINE(s_win, 0x00000001UL, "WIN", "st");
OSTX_STATIC_DEFINE(s_alm, 0x00000001UL, "ALM", "st");

static void emit(ostx_u8 b, void *) { Serial.write(b); }
static ostx_u8 tid = 0;

// 空调制热
ostx_stream_pack(&s_ac,  tid++, time(NULL), 10000L, emit, NULL);

// 窗户开
ostx_stream_pack(&s_win, tid++, time(NULL), 10000L, emit, NULL);

// 报警关
ostx_stream_pack(&s_alm, tid++, time(NULL), 0L,     emit, NULL);
```

---

## 上电默认状态

| 设备 | 默认状态 | 对应 LED |
|------|---------|---------|
| 空调 | 关闭 | 红/蓝 全灭 |
| 窗户 | **关闭** | 绿灯亮（正常现象）|
| 报警 | 关闭 | 白灯灭 |

---

## 设计决策说明

### 为什么单向（Uno 不回报）

Pi 作为唯一状态管理者（Source of Truth），自己记录下发的指令即可推断当前状态，无需 Uno 确认。这与 Philips Hue、小米智能家居等商业方案的 Command-only actuator 模型一致。

**已知局限：**
- 若串口丢包，Pi 与 Uno 状态会短暂分叉
- Uno 意外重启后状态归零，Pi 不感知

对于模拟器场景，重新下发一次指令即可恢复，不影响使用。

### 为什么使用 OSynaptic-RX 而非纯文本协议

| 对比项 | 旧文本协议 `CMD:KEY:VAL` | OSynaptic-RX |
|--------|------------------------|-------------|
| 数据完整性 | 无校验，噪声可导致误动作 | CRC-8 + CRC-16 双校验 |
| 帧同步 | 依赖换行符，易被噪声破坏 | 15 ms 空闲间隙，更健壮 |
| Flash 占用 | 极小 | ~616 B（ATmega328P 32 KB Flash，可忽略）|
| 与 Pi 生态兼容性 | 仅限本项目 | 与 OpenSynaptic Python hub 直接对接 |

---

## 依赖库

| 库 | 版本 | 来源 |
|----|------|------|
| OSynaptic-RX | v1.0.0 | https://github.com/OpenSynaptic/OSynaptic-RX |

PlatformIO 会在编译时自动拉取，无需手动安装。
