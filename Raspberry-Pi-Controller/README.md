# 树莓派智能决策控制器

> 本模块是三子系统 IoT 平台的核心中枢。  
> 上游：ESP32 DHT11 传感器（REST API）+ Open-Meteo 实时天气  
> 下游：Arduino Uno 设备模拟器（OSynaptic 串口帧）+ Gsyn-Java Android App（UDP）

---

## 系统定位

```
          ┌────────────────────────────────────────┐
          │          Internet (eth0)               │
          │     Open-Meteo 免费天气 API             │
          └─────────────────┬──────────────────────┘
                            │ HTTPS
          ┌─────────────────▼──────────────────────┐
WiFi ────▶│        Raspberry Pi（本模块）           │────▶ UDP 9876 ──▶ Gsyn-Java
(wlan0)   │                                        │                    Android App
ESP32 ◀── │  在线 ML 决策引擎（Hoeffding Tree）    │◀─── UDP 9877 ──── 手机远程控制
REST API  │                                        │
          └─────────────────┬──────────────────────┘
                            │ UART 9600bps (USB)
          ┌─────────────────▼──────────────────────┐
          │         Arduino Uno                    │
          │  OSynaptic-RX 解析 → LED 设备状态       │
          └────────────────────────────────────────┘
```

树莓派扮演**三个角色**：
1. **决策器** — 融合室内外数据，用 ML + 规则做控制决策
2. **执行者** — 将决策通过 OSynaptic 帧发送给 Arduino
3. **桥接器** — 将 ESP32 数据透明转发给手机 App，同时接收手机的手动指令

---

## 文件说明

| 文件 | 说明 |
|---|---|
| `pi_controller.py` | 主程序，包含所有逻辑 |
| `osrx_tx.py` | 纯 Python 的 OSynaptic TX 实现（无第三方依赖） |
| `eval_synthetic.py` | 离线仿真验证脚本（用于在没有硬件时验证 ML pipeline） |
| `requirements.txt` | Python 依赖列表 |
| `data_log.csv` | 运行时自动生成的数据日志 |
| `eval_result.csv` | `eval_synthetic.py` 运行结果 |

---

## 快速启动

### 前置条件

| 条件 | 验证命令 |
|---|---|
| Arduino Uno 通过 USB 连接至 Pi | `ls /dev/ttyUSB0` |
| Pi wlan0 连接 ESP32 SoftAP | `curl http://192.168.4.1/sensor` |
| Pi eth0 有公网（天气 API） | 已有 SSH = 已通 |

### 安装依赖

```bash
pip3 install river pyserial requests --break-system-packages
```

### 启动主程序

```bash
cd ~/iot-sensor-projects/Raspberry-Pi-Controller
PYTHONIOENCODING=utf-8 python3 pi_controller.py
```

### 离线仿真验证（无需硬件）

```bash
python3 eval_synthetic.py
```

---

## 配置项说明

`pi_controller.py` 顶部的 `CFG` 字典包含所有可调参数：

```python
CFG = {
    "esp32_ip":           "192.168.4.1",   # ESP32 SoftAP 地址
    "serial_port":        "/dev/ttyUSB0",  # Arduino 串口设备
    "serial_baud":        9600,            # 波特率（与 Arduino 固件一致）
    "poll_interval_s":    10,              # 采集间隔（秒）
    "latitude":           31.23,           # 地理位置（影响天气 API）
    "longitude":          121.47,
    "temp_comfort_low":   20.0,            # 舒适温度下限 °C
    "temp_comfort_high":  28.0,            # 舒适温度上限 °C
    "humi_comfort_low":   40.0,            # 舒适湿度下限 %
    "humi_comfort_high":  70.0,            # 舒适湿度上限 %
    "bootstrap_n":        20,              # 引导期样本数（用规则训练模型）
    "udp_broadcast_port": 9876,            # Gsyn-Java 监控广播端口
    "udp_listen_port":    9877,            # 接收手机控制指令端口
}
```

---

## 架构详解

### 1. 数据采集层

**室内**：每 10 秒向 ESP32 发起 HTTP GET：
```
GET http://192.168.4.1/sensor
→ {"temp_c": 24.5, "humi_pct": 58.0, "online": true}
```

**室外**：每 10 分钟向 Open-Meteo 请求（免费，无需 API Key，结果本地缓存）：
```
GET https://api.open-meteo.com/v1/forecast?...
→ temperature_2m, relative_humidity_2m, apparent_temperature
```

---

### 2. 在线机器学习引擎

使用 **Hoeffding Tree**（`river` 库），专为 IoT 流式数据设计：每条样本到达即更新，无需存储历史数据，内存占用恒定。

**特征向量（9 维）**：

| 特征 | 来源 | 説明 |
|---|---|---|
| `in_temp` | ESP32 | 室内温度 |
| `in_humi` | ESP32 | 室内湿度 |
| `out_temp` | Open-Meteo | 室外温度 |
| `out_humi` | Open-Meteo | 室外湿度 |
| `feels_like` | Open-Meteo | 体感温度 |
| `hour` | 系统时钟 | 当前小时（0-23）|
| `weekday` | 系统时钟 | 星期几（0=周一）|
| `temp_diff` | 衍生 | 室内外温差 |
| `humi_diff` | 衍生 | 室内外湿差 |

**输出标签（6 类）**：

| 标签 | 动作 | Arduino LED |
|---|---|---|
| 0 | 维持现状 | — |
| 1 | 开制热 | D5 红灯 |
| 2 | 开制冷 | D4 蓝灯 |
| 3 | 开窗 | D3 黄灯 |
| 4 | 关窗 | D2 绿灯 |
| 5 | 报警 | D6 白灯 |

**两阶段运行逻辑**：

```
第 1-20 条（引导期）：
  规则引擎做决策 → 发给 Arduino
  同时将 (特征, 规则标签) 喂给 ML 训练

第 21 条起（ML 期）：
  ML 预测做决策 → 发给 Arduino
  仍用规则标签持续训练（数据自迭代）
```

规则引擎的意义：在冷启动阶段保证系统安全运转，并作为 ML 的"老师"提供初始标签。

---

### 3. 规则引擎

规则引擎同时作为**决策 fallback** 和**训练标签来源**，逻辑如下：

```
湿度 > 80% 或 < 30%  →  报警（5）
温度 < 18°C          →  制热（1）
温度 > 30°C          →  制冷（2）
温度、湿度均在舒适区
  且室内外温差 < 3°C  →  开窗（3）
其他                  →  维持（0）
```

规则引擎**不使用**时间特征（hour/weekday）——这正是 ML 的理论优势所在。

---

### 4. OSynaptic 串口通信

本模块自行实现了 OSynaptic TX 协议（`osrx_tx.py`），与 Arduino 上运行的官方 OSynaptic-RX C 库完全兼容。

**帧格式**（FULL 模式，cmd=0x3F）：

```
字节  0     : cmd = 0x3F (63, DATA_FULL)
字节  1     : route_count = 1
字节  2-5   : aid (big-endian uint32)
字节  6     : tid (0-255 滚动递增)
字节  7-12  : timestamp (48-bit big-endian, Unix 秒)
字节 13-N-4 : body = "sensor_id|unit|Base62(scaled)"
字节  N-3   : CRC-8/SMBUS (body)
字节 N-2..N-1: CRC-16/CCITT-FALSE (全帧)
```

每次决策变化时发送 3 条帧（先全归零，再设置目标设备）：

```python
AC.send(scaled=0)      # 先关空调
WIN.send(scaled=0)     # 先关窗
ALM.send(scaled=0)     # 先消警
AC.send(scaled=10000)  # 再开制热（如果决策=1）
```

---

### 5. Gsyn-Java 双向 UDP 桥接

Pi 同时作为 Android App（Gsyn-Java）的数据桥，ESP32 固件和 Arduino 均不需要任何修改。

**广播（Pi → 手机，端口 9876）**：
- 每 10 秒将 ESP32 温湿度封装成 Gsyn-Java 兼容的 OSynaptic UDP 帧广播
- 手机 Gsyn-Java 设置页面开启 UDP，端口填 9876 即可收到数据

**监听（手机 → Pi → Arduino，端口 9877）**：
- Gsyn-Java Send 界面填写 Host=Pi IP、Port=9877 发送控制帧
- Pi 解析后立即转发给 Arduino，**优先级高于 ML 决策**
- 支持手动控制：AC（制热=1.0/制冷=2.0/关=0）、WIN（开=1.0/关=0）、ALM（开=1.0/关=0）

---

### 6. 数据日志（data_log.csv）

每个控制周期自动追加一行：

| 列 | 说明 |
|---|---|
| `timestamp` | ISO 8601 时间戳 |
| `in_temp` / `in_humi` | 室内温湿度（ESP32） |
| `out_temp` / `out_humi` / `feels_like` | 室外天气 |
| `rule_label` | 规则引擎决策 |
| `ml_pred` | ML 原始预测（引导期为空） |
| `decision` | 实际执行的决策 |
| `phase` | `引导` 或 `ML` |
| `ml_accuracy_pct` | ML 与规则标签的一致率（引导期为空） |
| `diverged` | 1=ML 与规则决策不同 |
| `comfortable_next` | 1=下一轮室内处于舒适区（事后验证用） |

---

## ML 有效性验证说明

### 为什么 ml_accuracy_pct 不能作为证明

`ml_accuracy_pct` 衡量"ML 与规则标签的吻合程度"。由于 ML 本身就是用规则标签训练的，高精度只证明模型成功复现了规则，不证明 ML 提供了额外价值。

### 正确的验证指标

ML 的唯一实际优势是**时间特征**（规则引擎完全不使用 hour/weekday）。通过分析 CSV 的 `diverged` 和 `comfortable_next` 列：

```python
import pandas as pd
df = pd.read_csv("data_log.csv")
ml = df[df["phase"] == "ML"]

# 发散率：ML 相比规则做出了不同决策的频率
print(f"发散率: {ml['diverged'].mean()*100:.1f}%")

# 发散时 vs 不发散时，哪种结果更好
print(ml.groupby("diverged")["comfortable_next"].mean())
```

**解读**：若发散时 `comfortable_next` 均值 > 不发散时，说明 ML 利用时间特征做出了比规则更好的判断。

### 离线仿真（无需实际硬件）

```bash
python3 eval_synthetic.py
```

与真实系统使用完全相同的 ML pipeline，生成 4 周仿真数据并输出分析报告。

> **重要**：仿真数据中的时间规律是人为设定的，仿真结果只能验证 pipeline 逻辑正确性，不能作为 ML 超越规则的依据。真实验证需要实际运行数据。

---

## 依赖说明

| 库 | 用途 | 安装方式 |
|---|---|---|
| `river` 0.24.2 | 在线机器学习（Hoeffding Tree） | pip3 |
| `pyserial` 3.5 | USB 串口通信 | pip3 |
| `requests` | ESP32 REST API + 天气 API HTTP 请求 | pip3 |
| `osrx_tx.py` | OSynaptic TX 帧构建（本地实现） | 无需安装 |

> **注**：`opensynaptic` 官方 Python 库不适用于本场景。官方库面向云平台 OSynaptic 协议（cmd=0x7F 心跳包），而 Arduino 固件运行的是 OSynaptic-RX 嵌入式协议（仅接受 cmd=0x3F FULL 数据帧）。`osrx_tx.py` 根据 OSynaptic-RX 的 C 源码逆向实现，经 CRC 验证兼容。

---

## Present 快速问答

**Q: 为什么用 Hoeffding Tree 而不是其他模型？**
> Hoeffding Tree 是为流式数据设计的增量学习算法，每条样本只处理一次，内存占用恒定，适合树莓派这类资源受限设备。传统模型（Random Forest、SVM）需要批量重训练，与 IoT 实时采集场景不兼容。

**Q: 数据自迭代是什么意思？**
> 系统无需人工标注。规则引擎作为"自动标注器"，每一轮产生一个标签并喂给 ML，ML 在运行中持续学习，不需要离线准备训练集。

**Q: ML 的精度是多少？**
> `ml_accuracy_pct` 显示的是 ML 与规则标签的一致率，约 77-85%。这个数字只说明模型学会了规则的逻辑，不能作为 ML 超越规则的证明。真正的验证需要分析 `diverged` 样本的后验结果。

**Q: 没有 demo 数据怎么办？**
> 可以现场启动系统：LED 响应、ESP32 数据读取、手机 App 接收，整个端到端链路均可实时演示。ML 的长期效果评估需要持续运行数周，这与工业上 A/B 测试的逻辑一致。

---

## 代码实现详解

本章节面向技术 present，逐函数解析两个核心模块的实现思路。

---

### 一、`osrx_tx.py` — OSynaptic TX 帧构建器

#### 背景：为什么需要自行实现？

官方 `opensynaptic` Python 库面向云平台协议，其心跳包 `cmd=0x7F` 被 Arduino OSynaptic-RX 固件直接丢弃。Arduino 只接受 `cmd=0x3F`（FULL 数据帧）。本文件根据 OSynaptic-RX 的 C 源码逆向推导，在纯 Python 中重新实现了发送侧全部逻辑，并通过 CRC 自测验证（CRC-8=`0x0A` ✓，CRC-16=`0xC2C7` ✓）。

---

#### 1.1 CRC-8/SMBUS — 帧体完整性校验

```python
def _crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    crc = init & 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc
```

**算法参数**：CRC-8/SMBUS（又称 CRC-8-ATM），多项式 `x⁸+x²+x+1`（0x07），初始值 0x00，无输入/输出反射，无最终异或。

**覆盖范围**：只对 body 字符串（ASCII 字节）计算，用于快速检测帧体中的位翻转。Arduino 接收时先用此值核验 body 合法性，再进入 CRC-16 全帧验证。

**按位处理**：每个字节先与 CRC 寄存器异或，再对每一位做条件异或移位——这是 CRC 的标准无查表实现，代码量小，Pi 上运行速度足够（每帧约 20 字节）。

---

#### 1.2 CRC-16/CCITT-FALSE — 全帧端到端完整性校验

```python
def _crc16(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init & 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
```

**算法参数**：CRC-16/CCITT-FALSE（又称 CRC-CCITT），多项式 `x¹⁶+x¹²+x⁵+1`（0x1021），初始值 0xFFFF，无反射，无最终异或。`init=0xFFFF` 的设计确保全零帧与全空帧产生不同 CRC，防御静默帧错误。

**覆盖范围**：覆盖帧的所有字节 `frame[0 .. N-3]`（包括头部、body 和 CRC-8），最后两个字节即此 CRC-16 结果（大端序）。Arduino OSynaptic-RX 解析器在接收时对整个帧（除最后 2 字节）重新计算并比对。

**与 CRC-8 的分工**：CRC-8 用于快速验证 body 内容；CRC-16 用于全帧端到端完整性验证——两级校验和 UART 的奇偶校验共同构成三层错误检测。

---

#### 1.3 Base62 编码 — 浮点数整型化传输

```python
_B62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

def _b62_encode(value: int) -> str:
    neg = value < 0
    n = abs(value)
    if n == 0:
        return "0"
    digits = []
    while n:
        digits.append(_B62_CHARS[n % 62])
        n //= 62
    if neg:
        digits.append("-")
    return "".join(reversed(digits))
```

**设计动机**：OSynaptic 协议在 body 中不传输原始浮点数，而是用 Base62 编码的整数。在发送前将浮点值放大 10000 倍（`OSRX_VALUE_SCALE = 10000`），保留 4 位小数精度，例如温度 `24.5°C` → `245000` → Base62 字符串 `"ndi"`。

**字母表选择**：`0-9a-zA-Z` 共 62 个可打印 ASCII 字符，不含任何分隔符（`|` 和 `:` 是 body 的分隔符），因此无需转义。负数用 `-` 前缀表示（例如室外 `-3°C` → `-30000` → `"-7X2"`）。

**编码逻辑**：标准的短除法——对绝对值不断除 62 取余（从低位到高位），收集各位后翻转，最后如为负数在末尾追加 `-` 再一并翻转。

---

#### 1.4 `build_frame()` — 帧组装

```
帧结构（N = 13 + len(body) + 3）：
 [0]      cmd    = 0x3F (63)  ← OSRX_CMD_DATA_FULL
 [1]      route  = 1
 [2..5]   aid    (u32 big-endian)
 [6]      tid    (u8，每帧递增，0-255 滚动)
 [7..8]   ts高16位 = 0x0000
 [9..12]  ts低32位 = Unix 秒 (big-endian)
 [13..N-4] body  = "sensor_id|unit|b62(scaled)"（ASCII）
 [N-3]   CRC-8/SMBUS(body)
 [N-2..N-1] CRC-16/CCITT-FALSE(frame[0..N-3])  (big-endian)
```

**body 格式**：`"AC|md|2Bi"` 代表 AC（空调）传感器，单位 `md`（模式），值 `1.0`（制热档）。Arduino 固件按 `|` 分割后，用 Base62 解码器还原整数，再除以 10000 得到浮点值。

**时间戳 48-bit 设计**：OSynaptic 用 48 位存时间戳，高 16 位为毫秒/微秒扩展（本实现置 0），低 32 位为 Unix 秒。这样既兼容标准 32 位时间戳，又为未来扩展亚秒精度保留接口。

**组装顺序**：`header(13B)` → `body(ASCII)` → `crc8(1B)` → `crc16(2B)`。CRC-8 必须在 CRC-16 之前计算，因为 CRC-16 的覆盖范围包含 CRC-8 字节本身——这是协议的两级嵌套完整性设计。

---

#### 1.5 `OSTXSensor` 类 — 有状态传感器句柄

```python
class OSTXSensor:
    def __init__(self, agent_id, sensor_id, unit):
        self.agent_id  = agent_id
        self.sensor_id = sensor_id
        self.unit      = unit
        self._tid      = 0          # 私有 TID 计数器

    def send(self, scaled, emit):
        frame = build_frame(aid=self.agent_id, tid=self._tid,
                            sensor_id=self.sensor_id, unit=self.unit,
                            scaled=scaled)
        self._tid = (self._tid + 1) & 0xFF   # 滚动 0-255
        emit(frame)
```

**状态封装的意义**：`_tid`（Transaction ID）是 OSynaptic-RX 用于去重和乱序检测的序号。如果每次调用时 TID 恒为 0，Arduino 会将后续帧识别为重复帧并丢弃。

**Bug 溯源**：代码早期版本在每次 `send_command()` 中 `new OSTXSensor(...)` 重新创建实例，导致 TID 始终归零。修复方案是在模块级保持三个持久化全局实例（`_ac_sensor / _win_sensor / _alm_sensor`），在整个程序生命周期内 TID 单调递增。

**`& 0xFF` 滚动**：TID 字段为 1 字节，对 256 取模用位运算 `& 0xFF` 替代 `% 256`，在 CPython 上性能等价，意图更明确。

---

#### 1.6 `serial_emit()` — 传输层解耦

```python
def serial_emit(port) -> callable:
    def _emit(data: bytes) -> None:
        port.write(data)
    return _emit
```

**闭包设计**：`serial_emit` 接收一个 `serial.Serial` 对象并返回一个闭包。`OSTXSensor.send()` 只需要一个 `emit(bytes) -> None` 的可调用对象，不依赖任何串口细节。

**解耦收益**：在 `eval_synthetic.py` 离线仿真中，可以传入一个把帧写入列表的 mock emit：`emit = lambda data: frames.append(data)`，不需要真实串口即可测试帧构建逻辑。这是依赖注入在函数式 Python 中的体现。

---

### 二、`pi_controller.py` — 主控制器

#### 2.1 全局状态管理

```python
# 持久化 OSTXSensor 实例
_ac_sensor = _win_sensor = _alm_sensor = None

def _get_sensors():
    global _ac_sensor, _win_sensor, _alm_sensor
    if _ac_sensor is None:        # 懒初始化：首次 send_command 时才尝试导入
        try:
            from osrx_tx import OSTXSensor
            _ac_sensor  = OSTXSensor(0x00000001, "AC",  "md")
            _win_sensor = OSTXSensor(0x00000001, "WIN", "st")
            _alm_sensor = OSTXSensor(0x00000001, "ALM", "st")
        except ImportError:
            pass                  # 模块缺失时优雅降级，不崩溃
    return _ac_sensor, _win_sensor, _alm_sensor
```

**懒初始化 vs 模块顶层初始化**：在模块顶层立即初始化需要 `osrx_tx` 导入成功，而 `_get_sensors()` 的懒初始化允许在没有 `osrx_tx.py` 的环境下运行（仅丢失串口功能，天气/ML 功能正常），提升了代码的可移植性。

**三传感器设计**：每种控制动作（AC / Window / Alarm）对应独立的 `OSTXSensor` 实例，拥有各自的 TID 计数器。这与 OSynaptic-RX 的多传感器协议设计一致——Arduino 端按 `sensor_id` 路由，不同传感器的 TID 互不干扰。

---

#### 2.2 在线机器学习 Pipeline

```python
model = compose.Pipeline(
    preprocessing.StandardScaler(),
    tree.HoeffdingTreeClassifier(
        grace_period=30,
        delta=1e-5,
        leaf_prediction="mc",
    ),
)
ml_accuracy = metrics.Accuracy()
```

**StandardScaler（流式归一化）**：不同特征量纲差异极大（`in_temp` 约 15-35，`hour` 约 0-23，`weekday` 约 0-6）。River 的 `StandardScaler` 维护每个特征的流式均值和方差，每条样本逐步更新，无需提前知道数据范围，输出 z-score 归一化值送入分类器。

**HoeffdingTreeClassifier（在线增量决策树）**：基于 Hoeffding 不等式（大数定律的高概率界），仅需少量样本就能以高置信度确定最优分裂特征，无需看完所有数据。关键参数：
- `grace_period=30`：每积累 30 条新样本才重新评估分裂条件，避免频繁重构树结构
- `delta=1e-5`：置信水平参数，允许错误选择最优分裂的概率上限为 0.001%
- `leaf_prediction="mc"`（majority class）：叶节点用最多数类别预测，适合类别不均衡场景

**`learn_one / predict_one` 流式接口**：每条样本独立处理，内存用量恒定，适合树莓派（512MB RAM）长期运行。无论运行多少天，模型大小只增长到树结构达到稳定为止。

---

#### 2.3 两阶段决策逻辑

```python
if sample_count <= CFG["bootstrap_n"]:      # 前 20 条：引导阶段
    ml_pred  = None
    decision = rule_label
    model.learn_one(feat, rule_label)
    phase = "引导"
else:                                        # 第 21 条起：ML 阶段
    ml_pred  = model.predict_one(feat)
    decision = ml_pred if ml_pred is not None else rule_label
    ml_accuracy.update(rule_label, decision)
    model.learn_one(feat, rule_label)        # 持续用规则标签迭代
    phase = "ML"
```

**冷启动问题**：Hoeffding Tree 在极少样本（<10 条）时无法稳定分裂，预测结果随机。`bootstrap_n=20` 的引导阶段让模型先"看"足够多的规则标签，使树的根节点分裂有意义，避免 ML 阶段初期做出荒谬决策。

**持续标注（Continuous Labeling）**：ML 阶段中，`rule_label` 仍然作为训练标签（不是 `ml_pred`）。这确保模型每轮都从规则"教师"处学习——即使规则和 ML 产生分歧，模型也会逐渐向规则修正，而不是学习自身预测的错误（自我强化偏差）。

**None 安全**：`predict_one` 在树还没有稳定叶节点时可能返回 `None`。`decision = ml_pred if ml_pred is not None else rule_label` 先做 fallback，再传给 `ml_accuracy.update`，避免 `None` 被当作一个独立类别导致精度统计失真。

---

#### 2.4 主循环 9 步

每 `poll_interval_s`（默认 10 秒）执行一轮：

```
步骤 1  fetch_esp32()          — HTTP GET ESP32 /sensor，超时 3 秒
步骤 1b udp_broadcast_gsyn()   — 将温湿度数据广播给 Gsyn-Java 手机 App
步骤 2  fetch_weather()        — Open-Meteo API（TTL 10 分钟缓存）
步骤 3  make_features()        — 构造 9 维特征向量（含 temp_diff / humi_diff 衍生特征）
步骤 4  rule_based_decision()  — 静态规则，产生标签（始终计算，作为 ML 训练标签）
步骤 5  ML 决策                — 引导阶段：跟规则；ML 阶段：model.predict_one()
步骤 6  _remote_cmd_q.get_nowait() — 检查手机远程指令（优先级高于 ML 决策）
步骤 7  串口发送               — 决策变化或收到远程指令时才发送，避免频繁串口写入
步骤 8  数据日志               — CSV 写入，记录 diverged 和 comfortable_next 列
步骤 9  time.sleep()           — 补足剩余时间（扣除本轮执行耗时）
```

**只在决策变化时发送**：`if decision != last_action: send_command(decision)` 避免每 10 秒重复发送相同指令，减少 UART 总线负载和 Arduino 端的冗余解析。

**天气缓存**：`_WEATHER_TTL = 600` 秒（10 分钟）。Open-Meteo 免费端点限速约 10,000 次/天，10 秒一次轮询（8,640 次/天）本已接近上限，加缓存后降至 144 次/天，有大量余量。

---

#### 2.5 UDP 广播 — Pi 作透明桥接（`udp_broadcast_gsyn()`）

```python
# 1. 计算时间戳 Token（Gsyn-Java encodeTimestamp 格式）
ts_bytes = bytes([0, 0, ts>>24&0xFF, ts>>16&0xFF, ts>>8&0xFF, ts&0xFF])
ts_token = base64.urlsafe_b64encode(ts_bytes).rstrip(b"=").decode()

# 2. 构造 body（与 PacketBuilder.buildMultiSensorPacket 兼容）
body_str = f"{aid}.U.{ts_token}|TEMP>U.°C:{b62_temp}|HUM>U.%RH:{b62_humi}|"

# 3. 打包为 OSynaptic FULL 帧，广播到 255.255.255.255:9876
```

**Gsyn-Java 兼容性**：Android App 的 `PacketBuilder.buildMultiSensorPacket` 生成的 body 格式为 `{aid}.U.{ts_token}|{SID}>U.{unit}:{b62}|`。Pi 侧完全复现此格式，使 Gsyn-Java 的解析代码无需任何修改即可接收 Pi 广播的数据。

**时间戳编码**：Gsyn-Java 用 6 字节存储时间戳（与帧内 48-bit 时间戳一致），再做 URL-safe Base64（无 padding `=`）得到 8 字符的 token。例如时间戳 `1720000000` → 6字节 `[0x00, 0x00, 0x66, 0x94, 0x5A, 0x00]` → `"AABmlVoA"`。

**体感透明桥接**：ESP32 固件、Arduino Uno 代码均无任何改动。Pi 仅在软件层面充当 REST-to-UDP 协议转换器，体现了 OSynaptic 协议在 Pi 上的"软性网关"能力。

---

#### 2.6 UDP 监听线程 — 远程手动控制（`_udp_listener()`）

```python
sock.settimeout(2.0)           # 非阻塞等待，避免线程永久挂起
while True:
    try:
        data, addr = sock.recvfrom(512)
    except socket.timeout:
        continue               # 超时继续循环（检测程序是否退出）
    except Exception as e:
        log.error(f"UDP 监听线程异常退出: {e}")
        sock.close()           # 确保 socket 资源释放
        break
    # ... CRC-16 验证 → body 解析 → put_nowait
```

**2 秒超时设计**：`settimeout(2.0)` 确保线程每 2 秒至少检查一次状态，而非永久阻塞在 `recvfrom`。当主程序退出时，守护线程（`daemon=True`）被自动回收，不会造成资源泄漏。

**CRC-16 验证**：接收到帧后，对 `data[:-2]` 重新计算 CRC-16 并与 `data[-2:]` 对比。丢弃不匹配的包，防止误广播或网络噪声触发错误的设备动作。

**线程安全队列**：

```python
_remote_cmd_q = queue.Queue(maxsize=1)  # 容量 1，不积压旧指令

# 监听线程（生产者）：
try:
    _remote_cmd_q.put_nowait((action, addr_str))
except queue.Full:
    pass           # 丢弃：上条指令还没被主循环消费，更新的指令不会堆叠

# 主循环（消费者）：
try:
    remote_override, _ = _remote_cmd_q.get_nowait()
except queue.Empty:
    remote_override = None
```

**`maxsize=1` 的意义**：若使用无限队列（`Queue()`），10 秒轮询间隔内的多条手机指令会依次积压，主循环消费时执行"历史指令"序列，产生设备抖动。`maxsize=1` 确保队列中永远只有最新的一条指令，`put_nowait` 失败时静默丢弃，行为类似"最新值寄存器"。

---

#### 2.7 串口重连机制（`_get_serial()`）

```python
def _get_serial():
    global _serial_conn
    if _serial_conn is None or not _serial_conn.is_open:
        try:
            import serial
            _serial_conn = serial.Serial(CFG["serial_port"], CFG["serial_baud"], timeout=1)
            time.sleep(2)        # 等待 Arduino CH340 复位完成
            log.info(f"串口已连接: {CFG['serial_port']}")
        except Exception as e:
            log.warning(f"串口连接失败: {e}")
            _serial_conn = None
    return _serial_conn
```

**`is_open` 检查**：`serial.Serial` 对象在 USB 拔插后 `is_open` 变为 `False`，下次 `_get_serial()` 调用时会尝试重新打开，而不需要重启程序。这是面向生产环境的鲁棒性设计——Arduino 可以随时插拔，控制器不崩溃。

**2 秒延迟**：Arduino Uno 的 CH340 USB 转串口芯片在连接建立时会触发 DTR 信号，导致 Arduino 复位。`time.sleep(2)` 等待 Arduino bootloader 完成（约 1.5 秒），避免串口建立后立即发送帧时 Arduino 还在初始化。

**优雅降级**：失败时返回 `None`，调用方 `send_command` 检测到 `None` 则记日志并跳过发送，不抛出异常。控制器的天气采集、ML 决策、UDP 广播功能在无串口时依然正常运行。
