# 项目分工与代码解读手册

> **用途**：Presentation 背景资料，分发给组员 A 和 B  
> **设计者 / 硬件负责人**：C  
> **版本日期**：2026-04-28

---

## 目录

0. [开始之前——环境配置](#0-开始之前环境配置)
1. [项目总览](#1-项目总览)
2. [三人分工总表](#2-三人分工总表)
3. [C（设计者）的职责](#3-c设计者的职责)
4. [A 的职责与任务清单](#4-a-的职责与任务清单)
5. [B 的职责与任务清单](#5-b-的职责与任务清单)
6. [代码解读——公共数据结构与全局变量](#6-代码解读公共数据结构与全局变量)
7. [代码解读——A 负责的部分](#7-代码解读a-负责的部分)
8. [代码解读——B 负责的部分](#8-代码解读b-负责的部分)
9. [A 与 B 的接口约定](#9-a-与-b-的接口约定)
10. [编译与烧录说明](#10-编译与烧录说明)
11. [ESP32 main.cpp 布局地图](#11-esp32-maincpp-布局地图)
12. [各阶段验证检查点](#12-各阶段验证检查点)
13. [常见陷阱与排错](#13-常见陷阱与排错)

---

## 0. 开始之前——环境配置

**A 和 B 在写任何代码之前，必须先完成以下步骤。**

### 步骤 1：安装 VS Code

下载并安装 [Visual Studio Code](https://code.visualstudio.com/)。

### 步骤 2：安装 PlatformIO 插件

1. 打开 VS Code，点击左侧活动栏的 **Extensions**（四方块图标）
2. 搜索 `PlatformIO IDE`，点击 **Install**
3. 安装完成后 VS Code 会提示重启，点击 **Restart**
4. 重启后左侧活动栏会出现一个蚂蚁头图标，即 PlatformIO

### 步骤 3：克隆项目仓库

```bash
git clone https://github.com/ChrisLee0721/iot-sensor-projects.git
cd iot-sensor-projects
```

### 步骤 4：用 VS Code 打开项目

- **A**：用 VS Code 打开 `Arduino-Uno-DeviceSimulator/` 文件夹（File → Open Folder）
- **B**：用 VS Code 打开 `ESP32-DualDisplay-DHT11-Monitor/` 文件夹
- **同时负责两个项目的人**：也可以打开最外层 `iot-sensor-projects/` 文件夹，PlatformIO 会自动识别两个子项目

> PlatformIO 检测到 `platformio.ini` 后会自动在底部状态栏显示项目名称，此时即可使用底部工具栏的 ✓（编译）和 →（上传）按钮。

### 步骤 5：第一次编译（验证环境）

VS Code 底部状态栏点击 ✓ 号（Build），PlatformIO 会自动下载所有依赖库（首次约需 2~5 分钟，需要网络）。看到 `SUCCESS` 即表示环境配置完成。

```
====== [SUCCESS] Took XX.XX seconds ======
```

如果出现 `Error: library not found`，检查网络连接，然后在终端运行：

```bash
pio lib install
```

### 步骤 6：连接开发板并上传

1. 用 USB 线连接 ESP32 或 Arduino Uno
2. VS Code 底部工具栏点击 → 号（Upload）
3. 上传成功后，点击插头图标（Serial Monitor）打开串口监视器

---

## 1. 项目总览

本次项目由两个子系统组成，共同构成一套智能家居温湿度感知与设备控制演示平台：

### 子系统一：ESP32 双屏 DHT11 监控器
**文件夹**：`ESP32-DualDisplay-DHT11-Monitor/`

ESP32 作为数据中枢，实时采集 DHT11 温湿度传感器数据，通过两块 ST7735 TFT 显示屏展示多页面 UI，同时提供：
- WiFi AP 热点（自建，无需路由器）
- 内置 Web 仪表盘（浏览器可访问）
- REST API（JSON 接口）
- OSynaptic-FX UDP 广播（向 PC 端推送传感器数据包）

### 子系统二：Arduino Uno 设备模拟器
**文件夹**：`Arduino-Uno-DeviceSimulator/`

Arduino Uno 作为纯执行终端，通过 UART 接收树莓派（Pi）下发的 OSynaptic 二进制指令帧，控制 5 颗 LED 模拟智能家居设备（空调制热/制冷、窗户开/关、报警器）的状态。

### 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                     PC / 浏览器                          │
│  browser → http://192.168.4.1  (Web 仪表盘)             │
│  monitor.py / EA.py → UDP:9000  (OSynaptic-FX 数据接收) │
└────────────────────┬────────────────────────────────────┘
                     │ WiFi (SoftAP)
┌────────────────────▼────────────────────────────────────┐
│               ESP32 (子系统一)                           │
│  DHT11(GPIO4) → 采集 → TFT1(菜单) + TFT2(数据页面)     │
│                      → REST API(:80)                     │
│                      → OSynaptic-FX UDP:9000 广播       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    树莓派 (Pi)                           │
│  用 OSynaptic-TX 或 Python 脚本发送指令帧               │
└────────────────────┬────────────────────────────────────┘
                     │ UART 9600bps（单向，Pi→Uno）
┌────────────────────▼────────────────────────────────────┐
│               Arduino Uno (子系统二)                    │
│  OSynaptic-RX 解析帧 → LED 显示设备状态                 │
│  D5:红(AC热) D4:蓝(AC冷) D3:黄(窗开) D2:绿(窗关)      │
│  D6:白(报警)                                            │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 三人分工总表

| 职责域 | C（设计者） | A（实现者） | B（实现者） |
|--------|------------|------------|------------|
| 系统架构设计 | ✅ 负责 | — | — |
| 通信协议约定（OSynaptic 帧格式） | ✅ 负责 | — | — |
| 硬件搭建（接线、焊接） | ✅ 负责 | — | — |
| 项目文档（README.md、本文件） | ✅ 负责 | — | — |
| Python 工具链（monitor.py、EA.py） | ✅ 负责 | — | — |
| **Arduino Uno 固件**（main.cpp） | — | ✅ 负责 | — |
| **ESP32 网络/API/NVS/OSynaptic 层** | — | ✅ 负责 | — |
| **ESP32 UI/TFT/按键/DHT11/报警层** | — | — | ✅ 负责 |
| ESP32 platformio.ini | — | A 与 B 共同维护 | A 与 B 共同维护 |
| 联调验证 | ✅ 主导 | 参与 | 参与 |

---

## 3. C（设计者）的职责

C 是项目的设计者，负责在 A 和 B 开始工作之前提供所有必要的规格与前提条件。

### 已完成的设计输出

| 产出 | 文件位置 | 说明 |
|------|---------|------|
| ESP32 系统文档 | `ESP32-DualDisplay-DHT11-Monitor/README.md` | 硬件引脚、API 规格、UI 行为完整说明 |
| Arduino 技术文档 | `Arduino-Uno-DeviceSimulator/docs/device-simulator.md` | 通信协议、LED 行为、帧格式约定 |
| 本分工手册 | `TEAM_ASSIGNMENT.md` | A 和 B 的任务与代码解读 |
| Python 持久化监控 | `ESP32-DualDisplay-DHT11-Monitor/monitor.py` | PC 端数据接收与记录工具 |
| Python 分析脚本 | `ESP32-DualDisplay-DHT11-Monitor/EA.py` | OpenSynaptic 集成数据处理工具 |
| Shell 启动脚本 | `ESP32-DualDisplay-DHT11-Monitor/run-ea.sh` | 简化 EA.py 的运行方式 |

### C 提供给 A 和 B 的关键约定

1. **所有全局变量命名规则**：`g` 前缀（如 `gCfg`、`gRt`、`gUi`）
2. **硬件命名空间**：所有引脚定义在 `namespace HW` 中，A 和 B 不得硬编码 GPIO 编号
3. **OSynaptic-FX 每次采样后广播**：每隔 `gCfg.sampleMs` 毫秒广播一次，由 B 的采样循环触发
4. **设置变更后必须调用 `restartSoftAp()`**：由 A 实现，B 可以直接调用
5. **TFT CS 引脚操作规则**：每次操作某块屏之前必须 `digitalWrite(cs, LOW)`，操作完毕立即 `digitalWrite(cs, HIGH)`，防止 SPI 总线冲突

---

## 4. A 的职责与任务清单

### A 负责的代码范围

**文件 1**：`Arduino-Uno-DeviceSimulator/src/main.cpp`（全部，约 80 行）

**文件 2**：`ESP32-DualDisplay-DHT11-Monitor/src/main.cpp` 中以下函数（约 250 行）：

| 函数名 | 行为简述 |
|--------|---------|
| `safeStringArg()` | 字符串参数安全裁剪辅助函数 |
| `loadSettings()` | 从 NVS 读取所有配置项到 `gCfg` |
| `saveSettings()` | 将 `gCfg` 所有字段写入 NVS 持久化 |
| `restartSoftAp()` | 重启 WiFi SoftAP，使用当前 `gCfg.apSsid` 和 `gCfg.apPass` |
| `buildSensorJson()` | 将 `gRt.sensor` 和 `gRt.metrics` 序列化为 JSON 字符串 |
| `buildSettingsJson()` | 将 `gCfg` 所有字段序列化为 JSON 字符串 |
| `setupWifiApi()` | 初始化 WiFi AP 模式，注册所有 HTTP 路由（含内嵌 HTML、`/sensor`、`/settings`） |
| `setupOsfx()` | 初始化 OSynaptic-FX 上下文和 UDP socket |
| `broadcastOsfxPacket()` | 打包 8 路传感器数据，向 192.168.4.255:9000 广播 OSynaptic-FX 二进制帧 |

### A 的详细任务清单

**Arduino Uno 固件部分（`Arduino-Uno-DeviceSimulator/src/main.cpp`）**

- [ ] 理解 OSynaptic-RX 库的解析器初始化方式（`osrx_parser_init`），配置帧回调函数 `on_frame`
- [ ] 实现 `on_frame` 回调：根据 `sensor_id`（AC / WIN / ALM）和 `scaled` 值，更新 `ac_mode`、`window_open`、`alarm_on` 三个状态变量，并调用 `applyLeds()`
- [ ] 实现 `applyLeds()`：将三个状态变量映射到 5 颗 LED 的高低电平输出
- [ ] 实现 `loop()` 中的帧尾检测逻辑：连续读取串口字节喂给解析器，超过 15 ms 无新字节时调用 `osrx_feed_done()` 触发解析
- [ ] 在 `setup()` 中初始化串口（9600 bps）、5 个 LED 引脚为 OUTPUT，并初始化解析器
- [ ] 配置 `platformio.ini` 使用 OSynaptic-RX 库依赖

**ESP32 网络层部分（`ESP32-DualDisplay-DHT11-Monitor/src/main.cpp`）**

- [ ] 实现 `loadSettings()`：用 `prefs.begin("cfg", true)` 打开只读 NVS 命名空间，用 `prefs.getFloat/getUInt/getUChar/getBool/getString` 读取各配置项（含合法性边界检查）
- [ ] 实现 `saveSettings()`：用 `prefs.begin("cfg", false)` 打开读写 NVS 命名空间，用 `prefs.putFloat/putUInt/putUChar/putBool/putString` 写入各配置项
- [ ] 实现 `restartSoftAp()`：先 `WiFi.softAPdisconnect(true)` 断开旧 AP，再用 `WiFi.softAP(ssid, pass)` 启动新 AP，通过串口打印结果
- [ ] 实现 `buildSensorJson()` 和 `buildSettingsJson()`：用 `snprintf` 构造 JSON 字符串，注意浮点格式 `%.2f` 和布尔值需手动写 `"true"/"false"`
- [ ] 实现 `setupWifiApi()`：调用 `WiFi.mode(WIFI_AP)` 和 `restartSoftAp()`，用 `apiServer.on()` 注册以下 4 条路由：
  - `GET /` → 返回内嵌的 `WEB_INDEX_HTML` 静态页面
  - `GET /sensor` → 调用 `buildSensorJson()` 返回 JSON
  - `GET /settings` → 调用 `buildSettingsJson()` 返回 JSON
  - `POST /settings` → 解析 URL 编码参数，更新 `gCfg`，验证边界，调用 `saveSettings()`、`setBacklightPercent()`、`restartSoftAp()`
- [ ] 实现 `setupOsfx()`：初始化 `osfx_easy_context` 上下文，设置 AID=1、TID=1、节点名 `"DHT11_NODE"`，调用 `g_osfxUdp.begin(9000)` 和 `g_pingUdp.begin(9001)`
- [ ] 实现 `broadcastOsfxPacket()`：
  - 先在端口 9001 发送纯文本心跳包（用于调试 UDP 连通性）
  - 每隔 `OSFX_RESYNC_N`（30）包重置一次融合状态（防止接收端状态不同步）
  - 填充 8 路 `osfx_core_sensor_input` 数组：DHT11_TEMP、DHT11_HUMI、SYS_CPU_LOAD、SYS_CPU_MHZ、SYS_HEAP_FREE、SYS_HEAP_USED、SYS_UPTIME、SYS_ALARM
  - 调用 `osfx_easy_encode_multi_sensor_auto()` 编码，成功后通过 `g_osfxUdp` 广播到 `192.168.4.255:9000`

---

## 5. B 的职责与任务清单

### B 负责的代码范围

**文件**：`ESP32-DualDisplay-DHT11-Monitor/src/main.cpp` 中以下函数（约 350 行）：

| 函数名 | 行为简述 |
|--------|---------|
| `setupBacklightPwm()` | 用 LEDC 初始化 PWM 背光通道 |
| `setBacklightPercent()` | 将 0~100% 亮度换算为 0~255 duty cycle 写入 LEDC |
| `setAlarmOutput()` | 设置 GPIO15 报警输出引脚高低电平 |
| `findCharIndex()` | 在字符集数组中查找字符位置（文本编辑辅助） |
| `trimTrailingSpaces()` | 去除字符串尾部空格 |
| `beginTextEdit()` | 进入 WiFi SSID/密码文本编辑模式，初始化编辑缓冲区 |
| `commitTextEdit()` | 确认文本编辑，将结果写回 `gCfg.apSsid` 或 `gCfg.apPass` |
| `drawHeaderTft2()` | 在 TFT2 顶部绘制统一格式的标题栏 |
| `drawMenuOnTft1()` | 在 TFT1 上绘制完整的 5 项页面导航菜单 |
| `drawLiveDataOnTft2()` | TFT2 实时数据页：温湿度数值、状态栏、进度条 |
| `drawPinMapOnTft2()` | TFT2 引脚图页：显示 DHT11 4 个引脚接线 |
| `drawSensorStateOnTft2()` | TFT2 系统状态页：CPU/内存/报警状态 |
| `drawCurveOnTft2()` | TFT2 历史曲线页：64 点温湿度折线图 |
| `drawSettingsOnTft2()` | TFT2 设置页：11 个配置项滚动列表 |
| `drawExitConfirmDialog()` | TFT2 退出确认对话框（保存或放弃） |
| `drawCurrentPageOnTft2()` | 根据 `gUi.activePage` 分发调用对应的绘制函数 |
| `hardwareResetTft()` | 通过 RST 引脚硬件复位指定的 TFT |
| `initTfts()` | 初始化两条 SPI 总线和两块 TFT 屏幕 |
| `initButtons()` | 初始化 4 个按键引脚为 INPUT_PULLUP |
| `scanButtons()` | 每次 loop 扫描所有按键，含 50 ms 消抖逻辑 |
| `consumeBtn()` | 读取并清除某个按键的"已按下"标志 |
| `handleSettingsConfirmMode()` | Settings 页：退出确认对话框的按键处理 |
| `handleSettingsTextEditMode()` | Settings 页：WiFi 文本编辑模式的按键处理 |
| `applySettingDelta()` | 对当前选中的设置项执行 +1/-1 步进修改 |
| `handleSettingsValueEditMode()` | Settings 页：数值编辑模式的按键处理 |
| `handleSettingsListMode()` | Settings 页：列表导航模式的按键处理 |
| `handleSettingsButtons()` | Settings 页按键处理总分发（依据当前子模式） |
| `handleMenuButtons()` | 主菜单按键处理（上下移动、OK 进入页面） |
| `updateAlarmState()` | 判断温湿度是否超出阈值，控制报警输出和屏幕闪烁 |
| `setup()` | 系统初始化入口（调用 A 和 B 各自的 init 函数） |
| `loop()` | 主循环（调用 A 的 API 处理 + B 的按键/采样/绘制） |

### B 的详细任务清单

**初始化部分**

- [ ] 实现 `setupBacklightPwm()`：调用 `ledcSetup(channel=0, freq=5000, resolution=8)` 和 `ledcAttachPin(GPIO32, channel=0)`
- [ ] 实现 `setBacklightPercent(uint8_t percent)`：将 `percent*255/100` 换算为 duty，调用 `ledcWrite(channel, duty)`
- [ ] 实现 `initTfts()`：先设置 CS/DC/RST 为 OUTPUT，再分别调用 `vspi.begin()` 和 `hspi.begin()` 初始化两条 SPI 总线，对每块屏执行 `hardwareResetTft()` 硬复位，再调用 `tft.initR(INITR_BLACKTAB)` 和 `tft.setRotation(0)`。注意每次操作前都要拉低对应 CS 引脚，操作完立即拉高
- [ ] 实现 `initButtons()`：遍历 `HW::Buttons::Pins[]` 数组，设置每个引脚为 `INPUT_PULLUP`，初始化 `gButtons[]` 状态（stable=HIGH, wasPressed=false）

**按键扫描与消抖**

- [ ] 实现 `scanButtons(uint32_t nowMs)`：遍历 4 个按键，每次读取 `digitalRead()`，若电平发生变化则记录时间戳；若稳定时间超过 `HW::BtnDebounceMs`（50 ms）且电平确实改变，则更新 `stable`，若为低电平（按下）则置 `pressed = true`
- [ ] 实现 `consumeBtn(Btn id)`：读取 `gButtons[id].pressed`，若为 true 则清零并返回 true，否则返回 false。**注意**：所有按键逻辑都必须通过此函数消费事件，不得直接读 gButtons

**TFT 绘制函数**

- [ ] 实现 `drawHeaderTft2(const char *title)`：填充顶部 24px 深蓝色标题栏，用黄色小字居左打印 title，底部画一条蓝色水平线。**每个绘制函数开头都必须 `digitalWrite(TFT2.cs, LOW)` 结尾都必须 `digitalWrite(TFT2.cs, HIGH)`**
- [ ] 实现 `drawMenuOnTft1()`：TFT1 专属。顶部标题 "TFT1 MENU"，从 y=30 开始每隔 24px 绘制一个菜单项矩形（116×18 px），当前选中项（`gUi.menuCursor`）填充蓝色，其余黑色，文字颜色对应切换
- [ ] 实现 `drawLiveDataOnTft2(bool fullRefresh)`：
  - `fullRefresh=true` 时：清屏、绘制标题栏、画温湿度框（矩形）、进度条空槽、底部 DHT11 引脚提示文字
  - 每次（含仅刷新）：更新状态栏颜色（在线=绿，报警=红，离线=红），更新温湿度文字，更新进度条填充宽度（温度条=红，湿度条=绿）
- [ ] 实现 `drawSensorStateOnTft2(bool fullRefresh)`：显示 ONLINE/OFFLINE 状态、CPU 频率、堆内存剩余、CPU 负载进度条（红色）、内存占用进度条（绿色）、当前温湿度、当前 AP SSID 名
- [ ] 实现 `drawCurveOnTft2(bool fullRefresh)`：从 `gTempHistory[]` 和 `gHumiHistory[]` 环形缓冲区读取最近至多 110 个点，按比例映射到绘图区域内（温度红线、湿度绿线），数据不足 2 点时显示 "Collecting data..."
- [ ] 实现 `drawSettingsOnTft2(bool fullRefresh)`：从 `gUi.settingsCursor` 计算出显示窗口起点，滚动显示 6 个设置项（最多），选中项蓝底，每项右侧调用 `SETTING_VALUE_DRAWERS[idx]()` 显示当前值；若处于文本编辑模式则在底部显示编辑状态和光标

**Settings 页交互逻辑**

- [ ] 实现 `applySettingDelta(int8_t d)`：根据 `gUi.settingsCursor` 当前指向的字段，对 `gCfg` 中对应值增减（温度步进 0.5°C，湿度步进 1.0%，采样时间步进 100ms，亮度步进 5%，报警取反），并做边界夹紧
- [ ] 实现 4 个 `handleSettings*Mode()` 函数：
  - **ListMode**：Up/Down 移动 `settingsCursor`（循环），OK 根据字段类型进入编辑子模式或直接执行动作，Back 回到 LiveData 页
  - **ValueEditMode**：Up/Down 调用 `applySettingDelta(±1)`，OK 或 Back 退出编辑模式
  - **TextEditMode**：Up/Down 切换当前字符（在 `TEXT_CHARSET` 字符集内循环），OK 前进光标（末尾时结束编辑），Back 弹出退出确认对话框
  - **ConfirmMode**：Up/Down 切换对话框选项（0=保存并应用 / 1=放弃），OK 执行对应动作，Back 关闭对话框继续编辑

**传感器采集与报警**

- [ ] 实现 `updateAlarmState(uint32_t now)`：判断 `gRt.sensor` 中温度和湿度是否超出 `gCfg` 中的四条阈值线，若超出且 `gCfg.alarmEnable` 为 true 且传感器在线则置 `alarmActive=true`，并以 250 ms 为周期翻转 `setAlarmOutput()` 实现闪烁效果
- [ ] 实现 `setup()` 中的初始化顺序：
  ```
  Serial.begin(115200) → dht.begin() → loadSettings() → setupBacklightPwm() →
  setBacklightPercent() → pinMode(AlarmPin, OUTPUT) → setAlarmOutput(false) →
  initButtons() → initTfts() → 初始化历史缓冲区为 NAN →
  drawMenuOnTft1() → drawCurrentPageOnTft2(true) → setupWifiApi() → setupOsfx()
  ```
- [ ] 实现 `loop()` 的完整逻辑：
  1. 记录 `loopStartUs = micros()`
  2. 调用 `apiServer.handleClient()`（A 实现的 HTTP 服务）
  3. 调用 `scanButtons(now)`
  4. 根据当前页面分发按键处理（Settings 页或其他页）
  5. 若有 UI 变化则重绘菜单和内容页
  6. 每隔 `gCfg.sampleMs` 读取一次 DHT11，写入历史缓冲区，调用 `updateAlarmState()`，调用 `broadcastOsfxPacket()`（A 实现），触发数据页刷新
  7. 计算 CPU 负载（指数平滑：`(old*7 + new) / 8`）和内存占用率
  8. `delay(10)`

---

## 6. 代码解读——公共数据结构与全局变量

A 和 B 都会频繁访问以下全局变量，必须理解其含义。

### 主要数据结构

```cpp
// 所有可持久化的用户配置
struct AppSettings {
    float tempLow, tempHigh;    // 温度报警下限 / 上限（°C）
    float humiLow, humiHigh;    // 湿度报警下限 / 上限（%）
    uint16_t sampleMs;          // DHT11 采样间隔（毫秒，500~10000）
    uint8_t brightness;         // 背光亮度（0~100%）
    bool alarmEnable;           // 是否启用报警
    String apSsid, apPass;      // WiFi AP 的 SSID 和密码
};

// UI 显示和交互状态
struct UiState {
    Page activePage;            // 当前显示页面
    Page lastPageDrawn;         // 上次实际绘制的页面（用于检测是否需要 fullRefresh）
    uint8_t menuCursor;         // TFT1 菜单光标位置
    uint8_t settingsCursor;     // Settings 页当前光标行
    bool settingEdit;           // 是否处于数值编辑子模式
    bool textEditMode;          // 是否处于文本编辑子模式（WiFi SSID/密码）
    SettingField textEditField; // 当前编辑的是 SSID 还是密码
    String textEditBuffer;      // 文本编辑中的临时缓冲区
    uint8_t textEditPos;        // 文本编辑光标在缓冲区的位置
    ExitConfirmMode exitConfirmMode;    // 是否显示退出确认对话框
    uint8_t exitConfirmCursor;          // 对话框中选中的选项
    ExitConfirmMode lastExitConfirmMode; // 上次对话框状态（用于重绘判断）
};

// 传感器运行时数据
struct SensorData {
    float temp, humi;           // 最新温湿度读数
    bool online;                // DHT11 是否在线（最近一次读数是否成功）
    bool alarmActive;           // 当前是否处于报警状态
    uint32_t lastDhtOkMs;       // 最近一次成功读数的时间戳（毫秒）
};

// 系统性能指标
struct SystemMetrics {
    uint8_t cpuLoadPct;         // CPU 负载百分比（指数平滑）
    uint8_t heapUsedPct;        // 堆内存占用百分比
    uint32_t lastDhtReadMs;     // 上次触发 DHT11 读取的时间戳
    uint32_t alarmBlinkMs;      // 报警闪烁计时器
    bool alarmBlinkState;       // 报警输出当前的高/低电平状态
};
```

### 全局变量一览

| 变量名 | 类型 | 谁会读写 | 说明 |
|--------|------|---------|------|
| `gCfg` | `AppSettings` | A（读写 NVS）、B（读阈值/采样率）、A（写 HTTP POST）| 所有持久化配置 |
| `gUi` | `UiState` | B（读写全部字段）| UI 状态，仅 B 操作 |
| `gRt.sensor` | `SensorData` | B（DHT11 写入）、A（JSON 序列化读取）| 传感器实时值 |
| `gRt.metrics` | `SystemMetrics` | B（CPU/内存计算写入）、A（JSON 序列化读取）| 系统指标 |
| `gTempHistory[]` | `float[64]` | B（写入）、B（曲线页读取）| 环形温度历史缓冲区 |
| `gHumiHistory[]` | `float[64]` | B（写入）、B（曲线页读取）| 环形湿度历史缓冲区 |
| `gHistoryIndex` | `uint8_t` | B | 环形缓冲区写指针 |
| `gHistoryFilled` | `bool` | B | 缓冲区是否已绕回（满） |
| `gButtons[]` | `ButtonState[4]` | B | 按键去抖状态 |

### 枚举类型

```cpp
// 页面枚举（0~4）
enum class Page : uint8_t {
    LiveData = 0,   // 实时数据
    PinMap = 1,     // 引脚图
    SensorState = 2,// 系统状态
    Curve = 3,      // 历史曲线
    Settings = 4    // 设置
};

// 按键枚举（对应 GPIO16/17/33/15）
enum class Btn : uint8_t { Up=0, Down=1, Ok=2, Back=3 };

// 设置字段枚举（0~10）
enum class SettingField : uint8_t {
    TempLow=0, TempHigh=1, HumiLow=2, HumiHigh=3,
    SampleMs=4, Brightness=5, AlarmEnable=6,
    WifiSsid=7, WifiPass=8, SaveApply=9, Exit=10
};
```

---

## 7. 代码解读——A 负责的部分

### 7.1 Arduino 固件（`Arduino-Uno-DeviceSimulator/src/main.cpp`）

#### 整体结构（约 80 行）

```
#include → 引脚定义 → 设备状态变量 → applyLeds() → on_frame() → 解析器变量 → setup() → loop()
```

#### `on_frame` 回调——最核心的逻辑

```cpp
static void on_frame(const osrx_packet_meta  *meta,
                     const osrx_sensor_field *field,
                     const osrx_u8 *, int, void *)
{
    // 1. 先检查 CRC，两个都必须通过，否则丢弃（帧损坏或传输错误）
    if (!meta->crc8_ok || !meta->crc16_ok) return;
    if (!field) return;  // 非传感器帧（可能是心跳帧），忽略

    // 2. 读取 scaled 值并换算（÷ OSRX_VALUE_SCALE = ÷ 10000）
    long val = (long)(field->scaled / OSRX_VALUE_SCALE);

    // 3. 根据 sensor_id 分发
    if (strcmp(field->sensor_id, "AC") == 0) {
        ac_mode = (int)val;   // 0=关, 1=制热, 2=制冷
    } else if (strcmp(field->sensor_id, "WIN") == 0) {
        window_open = (val != 0);  // 0=关, 1=开
    } else if (strcmp(field->sensor_id, "ALM") == 0) {
        alarm_on = (val != 0);
    }
    // 4. 立即刷新 LED
    applyLeds();
}
```

**注意**：Pi 发送端约定的 scaled 值（整数）：
- AC 关=0，制热=10000，制冷=20000  → 除以 10000 得 0/1/2
- WIN 关=0，开=10000               → 除以 10000 得 0/1
- ALM 关=0，开=10000               → 除以 10000 得 0/1

#### 帧边界检测（loop 中的 15 ms 机制）

OSynaptic 是二进制帧协议，没有固定帧头帧尾标志。Arduino 用**静默间隙**判断帧的结束：
- 串口来字节 → 实时喂给 `osrx_feed_byte()`
- 超过 15 ms 未收到新字节 → 认为这一帧已完整收到 → 调用 `osrx_feed_done()` 触发解析 → 解析器在内部调用 `on_frame` 回调

```cpp
void loop() {
    while (Serial.available()) {
        osrx_feed_byte(&parser, (osrx_u8)Serial.read());
        last_byte_ms = millis();
        got_byte = true;
    }
    if (got_byte && millis() - last_byte_ms > 15) {
        osrx_feed_done(&parser);
        got_byte = false;
    }
}
```

---

### 7.2 ESP32 NVS 配置层（`loadSettings` / `saveSettings`）

ESP32 的 NVS（Non-Volatile Storage）是内置 flash 中的键值存储，相当于一个小型数据库。

```cpp
void loadSettings() {
    prefs.begin("cfg", true);   // "cfg" = 命名空间，true = 只读模式
    gCfg.tempLow = prefs.getFloat("tLow", 18.0f);  // 键名="tLow"，默认18.0
    // ... 其余字段类似
    prefs.end();  // 必须 end，否则下次 begin 可能失败

    // 边界检查（从 NVS 读出的值可能因人为破坏而越界）
    if (gCfg.sampleMs < 500) gCfg.sampleMs = 500;
    if (gCfg.brightness > 100) gCfg.brightness = 100;
    if (gCfg.apPass.length() < 8) gCfg.apPass = HW::Net::DefaultPass;
}
```

**NVS 键名映射（A 必须保持一致）**：

| 配置字段 | NVS 键名 | 类型 | 默认值 |
|---------|---------|------|--------|
| `tempLow` | `"tLow"` | float | 18.0 |
| `tempHigh` | `"tHigh"` | float | 32.0 |
| `humiLow` | `"hLow"` | float | 30.0 |
| `humiHigh` | `"hHigh"` | float | 80.0 |
| `sampleMs` | `"smp"` | uint | 1200 |
| `brightness` | `"bl"` | uchar | 80 |
| `alarmEnable` | `"alarmEn"` | bool | true |
| `apSsid` | `"ssid"` | String | "ESP32-DHT11-API" |
| `apPass` | `"pass"` | String | "12345678" |

---

### 7.3 ESP32 REST API 层（`setupWifiApi`）

内嵌 HTML `WEB_INDEX_HTML` 存放在程序内存（`PROGMEM`），通过 `apiServer.send_P()` 发送。HTML 本身是一个单页应用，用 `fetch()` 每 1.5 秒轮询 `/sensor`，用表单 `POST /settings` 保存配置。

POST `/settings` 处理器的逻辑流程：
```
解析 URL 参数 → 更新 gCfg 字段 → 边界夹紧 → saveSettings() → 
setBacklightPercent() → restartSoftAp() → 返回 "saved"
```

**安全注意**：所有字符串参数必须通过 `safeStringArg(v, maxLen)` 过滤，防止超长字符串写入 NVS。

---

### 7.4 ESP32 OSynaptic-FX 广播层（`broadcastOsfxPacket`）

每次 DHT11 采样完成后，`broadcastOsfxPacket()` 将 8 路数据打包成 OSynaptic-FX 二进制帧并 UDP 广播。

**广播目标地址**：`192.168.4.255`（SoftAP 子网广播地址，所有连接到 AP 的设备均可收到）

**重同步机制**：每发送 30 个包（`OSFX_RESYNC_N=30`）重置一次融合状态，确保接收端（PC 上的 monitor.py / EA.py）即使中途加入也能正确解码。

**同时广播两个端口**：
- **9000**：OSynaptic-FX 标准二进制格式（供 monitor.py / EA.py 解码）
- **9001**：纯文本心跳（`PING ms=xxx t=xx.x h=xx.x`），供调试时用 netcat 验证 UDP 连通性

---

## 8. 代码解读——B 负责的部分

### 8.1 双 SPI 总线与 CS 引脚管理

ESP32 有两条硬件 SPI 总线：
- **VSPI**（GPIO18/23/19）驱动 TFT1（菜单屏）— 使用 `SPIClass vspi(VSPI)`
- **HSPI**（GPIO14/13/12）驱动 TFT2（内容屏）— 使用 `SPIClass hspi(HSPI)`

**关键规则**：两块屏的 CS（片选）引脚由软件手动控制，操作哪块屏，就拉低对应 CS；操作完毕**立即**拉高。绝对不允许同时拉低两个 CS。

```cpp
// 正确模式（每个 draw 函数的标准模板）
void drawXxxOnTft2(...) {
    digitalWrite(HW::TFT2.cs, LOW);   // ← 操作开始
    // ... tft2.xxx() 调用 ...
    digitalWrite(HW::TFT2.cs, HIGH);  // ← 操作结束
}
```

---

### 8.2 按键消抖机制

4 个按键均为**低有效**（按下 = LOW），通过 `INPUT_PULLUP` 上拉，空闲为 HIGH。

`scanButtons()` 实现了**稳定状态机消抖**：
```
读 raw → 若 raw != lastRead 则记录时间戳 → 
若稳定超过 50ms 且 stable 改变 → 更新 stable →
若 stable == LOW 且 wasPressed==false → 置 pressed=true, wasPressed=true
若 stable == HIGH → 清除 wasPressed（允许下次按下被响应）
```

`consumeBtn()` 是消费事件的唯一接口，确保每次按下只触发一次动作。

---

### 8.3 TFT 绘制的 fullRefresh 参数

所有绘制函数都接收 `bool fullRefresh` 参数：
- `fullRefresh=true`：从头完整重绘整个页面（切换页面时，或首次绘制时）
- `fullRefresh=false`：只更新会变化的区域（如温湿度数值、进度条），避免闪烁

在 `drawCurrentPageOnTft2()` 中调用时：
```cpp
// 切换了页面 → fullRefresh=true
// 同一页面中数据更新 → fullRefresh = (lastPageDrawn != activePage)
```

---

### 8.4 Settings 页的四种子模式

Settings 页的按键逻辑通过 `currentSettingsInputMode()` 判断当前处于哪种子模式：

```
ListMode（默认）
    ↓ OK 选中数值类字段
ValueEditMode     ← Up/Down 增减数值，OK 或 Back 退出
    
ListMode
    ↓ OK 选中 SSID 或 PASS
TextEditMode      ← Up/Down 切换字符，OK 前进，Back 弹出对话框
    ↓ Back
ExitConfirmMode   ← Up/Down 选择"保存"或"放弃"，OK 执行，Back 继续编辑
```

**文本编辑器的字符集**：

```cpp
constexpr char TEXT_CHARSET[] = " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.@";
```

Up 键在字符集中向前滚动，Down 键向后滚动，循环不断。光标到达缓冲区末尾位置时，按 OK 即结束编辑（调用 `commitTextEdit()`）。

---

### 8.5 历史曲线缓冲区（环形数组）

历史数据使用长度为 64 的环形缓冲区：

```cpp
float gTempHistory[64];  // 温度历史
float gHumiHistory[64];  // 湿度历史
uint8_t gHistoryIndex;   // 下一次写入位置
bool gHistoryFilled;     // 是否已经写满过一圈（用于判断有效数据量）
```

每次 DHT11 读取成功后：
```cpp
gTempHistory[gHistoryIndex] = t;
gHumiHistory[gHistoryIndex] = h;
gHistoryIndex = (gHistoryIndex + 1) % HISTORY_LEN;
if (gHistoryIndex == 0) gHistoryFilled = true;
```

绘制曲线时，若 `gHistoryFilled=true` 则有效点数为 64，否则为 `gHistoryIndex`。绘制从最旧的点连线到最新的点：

```cpp
// 温度归一化（映射到 -10°C ~ 50°C 范围内 → 0.0~1.0）
float tn = (temp + 10.0f) / 60.0f;
// 湿度归一化（0% ~ 100% → 0.0~1.0）
float hn = humi / 100.0f;
```

---

### 8.6 CPU 负载的计算方式

`loop()` 末尾用**指数加权平均**（EWMA）平滑 CPU 负载：

```cpp
uint32_t workUs   = micros() - loopStartUs;        // 本次循环实际工作时间（微秒）
uint32_t totalUs  = workUs + 10000;                // +10000 是 delay(10) 的 10ms
uint8_t  instant  = (workUs * 100U) / totalUs;    // 本次即时负载（%）
// 7/8 历史权重 + 1/8 当前值，平滑变化
gRt.metrics.cpuLoadPct = (gRt.metrics.cpuLoadPct * 7 + instant) / 8;
```

---

## 9. A 与 B 的接口约定

A 和 B 共享同一个 `main.cpp` 文件，以下是二者之间的调用边界，必须严格遵守：

### B 可以直接调用 A 的函数

| A 的函数 | B 调用时机 |
|---------|-----------|
| `loadSettings()` | `setup()` 最开始 |
| `saveSettings()` | Settings 页 "Save+Apply" 执行时 |
| `setBacklightPercent(gCfg.brightness)` | 初始化时、亮度修改时 |
| `restartSoftAp()` | Settings 页保存 WiFi 配置后 |
| `setupWifiApi()` | `setup()` 末尾 |
| `setupOsfx()` | `setup()` 末尾 |
| `apiServer.handleClient()` | `loop()` 每轮执行 |
| `broadcastOsfxPacket()` | 每次 DHT11 采样成功后 |

### A 不得直接访问以下 B 的内部状态

| B 管理的变量 | 原因 |
|------------|------|
| `gUi.*` | UI 状态由 B 完全控制，A 不需要知道 |
| `gButtons[]` | 按键状态由 B 完全控制 |
| `gTempHistory[]` / `gHumiHistory[]` | 历史数组由 B 填写，A 通过 `gRt.sensor` 读当前值 |

### A 写、B 读的共享字段

| 字段 | A 的动作 | B 的动作 |
|------|---------|---------|
| `gCfg`（HTTP POST 触发时） | A 更新 gCfg、存 NVS | B 读取阈值判断报警、读取 sampleMs 控制采样节奏 |
| `gCfg.brightness`（初始加载） | A 从 NVS 读出 | B 用于初始化背光 |

### B 写、A 读的共享字段

| 字段 | B 的动作 | A 的动作 |
|------|---------|---------|
| `gRt.sensor.temp/humi/online/alarmActive` | B 每次 DHT11 采样后写入 | A 在 `buildSensorJson()` 中读取并序列化 |
| `gRt.metrics.cpuLoadPct/heapUsedPct` | B 每轮 loop 末尾计算写入 | A 在 `buildSensorJson()` 中读取并序列化 |

---

## 10. 编译与烧录说明

### 环境要求

- PlatformIO（VS Code 插件或命令行工具均可）
- Python 3.8+（用于 monitor.py / EA.py，C 自行维护）

### ESP32 项目

```bash
cd ESP32-DualDisplay-DHT11-Monitor

# 编译
pio run

# 编译 + 烧录
pio run --target upload

# 串口监视器（115200 bps）
pio device monitor --baud 115200
```

**库依赖**（已写入 `platformio.ini`，编译时自动下载）：
- `Adafruit GFX Library`
- `Adafruit ST7735 and ST7789 Library`
- `DHT sensor library`
- `Adafruit Unified Sensor`
- `OSynaptic-FX`（从 GitHub 自动拉取）

### Arduino 项目

```bash
cd Arduino-Uno-DeviceSimulator

# 编译 + 烧录
pio run --target upload

# 串口监视器（9600 bps）
pio device monitor --baud 9600
```

**库依赖**（已写入 `platformio.ini`，编译时自动下载）：
- `OSynaptic-RX`（已配置，无需手动添加）

### 验证步骤（按顺序）

1. 烧录 ESP32，上电后检查串口输出：出现 `[API] HTTP server started` 和 `[OSFX] OSynaptic-FX ready` 表示正常
2. 手机或 PC 连接 WiFi `ESP32-DHT11-API`（密码 `12345678`）
3. 浏览器访问 `http://192.168.4.1`，能看到仪表盘页面
4. 访问 `http://192.168.4.1/sensor` 检查 JSON 是否有温湿度数据
5. 烧录 Arduino，用 Pi 或 USB 串口适配器发送测试帧，检查对应 LED 是否响应

---

## 11. ESP32 main.cpp 布局地图

`ESP32-DualDisplay-DHT11-Monitor/src/main.cpp` 全长约 980 行，**A 和 B 共用同一个文件**。下表说明文件的逻辑分区——哪些是 C 已写好的框架（不要动），哪些是 A 实现的，哪些是 B 实现的。

```
┌─────────────────────────────────────────────────────────────────┐
│ 区域 1：头文件与命名空间（C 已写，勿动）                          │
│  #include <...>                                                 │
│  namespace HW { ... }   ← 所有引脚定义                          │
│  namespace UI { ... }   ← 颜色常量                             │
├─────────────────────────────────────────────────────────────────┤
│ 区域 2：全局对象声明（C 已写，勿动）                              │
│  SPIClass vspi / hspi                                           │
│  Adafruit_ST7735 tft / tft2                                     │
│  DHT dht / WebServer apiServer / Preferences prefs             │
├─────────────────────────────────────────────────────────────────┤
│ 区域 3：枚举与常量（C 已写，勿动）                               │
│  enum class Page / Btn / SettingField / ExitConfirmMode         │
│  PAGE_NAMES[] / SETTING_NAMES[] / TEXT_CHARSET[]               │
│  HISTORY_LEN = 64 / WIFI_TEXT_MAX_LEN = 24                     │
├─────────────────────────────────────────────────────────────────┤
│ 区域 4：结构体定义（C 已写，勿动）                               │
│  struct AppSettings / UiState / ButtonState                     │
│  struct SensorData / SystemMetrics / RuntimeState              │
├─────────────────────────────────────────────────────────────────┤
│ 区域 5：全局变量（C 已写，勿动）                                 │
│  AppSettings gCfg                                               │
│  UiState gUi = { ... }  ← 含初始值，不要重新赋值               │
│  ButtonState gButtons[4]                                        │
│  RuntimeState gRt                                               │
│  float gTempHistory[64] / gHumiHistory[64]                     │
│  OSynaptic-FX 相关全局变量（g_osfxUdp 等）                      │
├─────────────────────────────────────────────────────────────────┤
│ 区域 6：内嵌 HTML 字符串（C 已写，勿动）                         │
│  WEB_INDEX_HTML[] PROGMEM = R"HTML(...)HTML"                    │
├─────────────────────────────────────────────────────────────────┤
│ 区域 7：B 实现 — 背光 + 报警输出                                 │
│  setupBacklightPwm()                                            │
│  setBacklightPercent()                                          │
│  setAlarmOutput()                                               │
├─────────────────────────────────────────────────────────────────┤
│ 区域 8：A 实现 — 字符串工具 / 文本编辑辅助（A 写 safeStringArg） │
│         B 实现 — 文本编辑辅助（B 写其余 4 个）                  │
│  safeStringArg()          ← A                                   │
│  findCharIndex()          ← B                                   │
│  trimTrailingSpaces()     ← B                                   │
│  beginTextEdit()          ← B                                   │
│  commitTextEdit()         ← B                                   │
├─────────────────────────────────────────────────────────────────┤
│ 区域 9：A 实现 — NVS 配置层                                     │
│  loadSettings()                                                 │
│  saveSettings()                                                 │
├─────────────────────────────────────────────────────────────────┤
│ 区域 10：A 实现 — WiFi / REST API                               │
│  restartSoftAp()                                                │
│  buildSensorJson()                                              │
│  buildSettingsJson()                                            │
│  setupWifiApi()                                                 │
├─────────────────────────────────────────────────────────────────┤
│ 区域 11：B 实现 — TFT 绘制函数                                  │
│  drawHeaderTft2()                                               │
│  drawMenuOnTft1()                                               │
│  drawLiveDataOnTft2()                                           │
│  drawPinMapOnTft2()                                             │
│  drawSensorStateOnTft2()                                        │
│  drawCurveOnTft2()                                              │
│  draw Settings 相关辅助函数（drawSettingTempLow 等）            │
│  drawSettingsOnTft2()                                           │
│  drawExitConfirmDialog()                                        │
│  drawCurrentPageOnTft2()                                        │
├─────────────────────────────────────────────────────────────────┤
│ 区域 12：B 实现 — TFT 初始化                                    │
│  hardwareResetTft()                                             │
│  initTfts()                                                     │
│  initButtons()                                                  │
├─────────────────────────────────────────────────────────────────┤
│ 区域 13：B 实现 — 按键处理                                      │
│  scanButtons()                                                  │
│  consumeBtn()                                                   │
│  handleSettings*() 系列函数                                     │
│  handleMenuButtons()                                            │
├─────────────────────────────────────────────────────────────────┤
│ 区域 14：A 实现 — OSynaptic-FX UDP 广播                         │
│  setupOsfx()                                                    │
│  broadcastOsfxPacket()                                          │
├─────────────────────────────────────────────────────────────────┤
│ 区域 15：B 实现 — 报警逻辑 + 主程序入口                          │
│  updateAlarmState()                                             │
│  setup()         ← 调用 A 和 B 双方的 init 函数                 │
│  loop()          ← 调用 A 的 API 处理 + B 的采样/按键/绘制      │
└─────────────────────────────────────────────────────────────────┘
```

> **规则**：区域 1~6 是 C 已经写好的框架代码，**A 和 B 绝对不能修改这些区域**。A 只在区域 7~10、14 中写代码，B 只在区域 7~13、15 中写代码。

---

## 12. 各阶段验证检查点

每完成一个主要任务后，用以下方法确认实现是否正确。**所有验证都需要开发板已通过 USB 连接 PC，并打开串口监视器。**

### A 的验证检查点

#### A-1：`loadSettings()` + `saveSettings()`
- 烧录后打开串口监视器，观察 `[API]` 输出，不应有崩溃或挂起
- 在 Web 仪表盘修改任意设置后断电重启，重启后设置应保持不变
- **预期串口输出**：首次启动时全部读取默认值，无报错

#### A-2：`restartSoftAp()`
```
[API] AP restarted: ESP32-DHT11-API
[API] AP IP: 192.168.4.1
```
- 用手机/PC WiFi 扫描，能看到热点 `ESP32-DHT11-API`

#### A-3：`setupWifiApi()` — HTTP 路由
- 连接热点后，浏览器访问 `http://192.168.4.1`，应出现仪表盘页面
- 访问 `http://192.168.4.1/sensor`，应返回 JSON（用 `temp_c`、`humi_pct` 字段）
- 访问 `http://192.168.4.1/settings`，应返回 JSON（用 `temp_low` 等字段）
- 用 curl 发 POST，检查返回 `saved`：
  ```bash
  curl -X POST http://192.168.4.1/settings -d "brightness=50"
  ```

#### A-4：`setupOsfx()` + `broadcastOsfxPacket()`
- **预期串口输出**（每隔 `sampleMs` 毫秒出现一次）：
  ```
  [PING] PING ms=12345 t=25.3 h=60.1
  [OSFX] encode ret=1 pktLen=87
  [OSFX] beginPacket=1
  [OSFX] FULL len=87 sent OK
  ```
- 在 PC 上运行 `python monitor.py`，应能看到 UDP 数据被接收和解码

#### A-5：Arduino `on_frame` + `applyLeds()`
- 串口监视器（9600 bps）中，发送一个测试帧后，对应 LED 应亮起
- 若没有 Pi，可以用 Python 测试：
  ```python
  # 安装：pip install opensynaptic pyserial
  from opensynaptic import OSTXSensor, serial_emit
  import serial
  port = serial.Serial("/dev/ttyUSB0", 9600)
  ac = OSTXSensor(agent_id=1, sensor_id="AC", unit="md")
  ac.send(scaled=10000, emit=serial_emit(port))  # 应点亮红色 LED
  ```

---

### B 的验证检查点

#### B-1：`setupBacklightPwm()` + `setBacklightPercent()`
- 上电后屏幕背光应以 80% 亮度点亮
- 在 Settings 页调整 Brightness，屏幕亮度应实时变化

#### B-2：`initTfts()`
- 两块屏幕应在上电约 1 秒内显示内容（TFT1 显示菜单，TFT2 显示 Live Data）
- 若屏幕全白：CS 引脚接线错误或忘记拉低 CS
- 若屏幕全黑：RST 复位时序问题，检查 `hardwareResetTft()` 的延时是否足够（20ms LOW + 120ms HIGH）

#### B-3：`scanButtons()` + `consumeBtn()`
- 用手按下各按键，观察串口是否无乱码（消抖正常）
- TFT1 菜单光标应随 Up/Down 移动，按 OK 进入对应页面
- **每个按键只触发一次动作**，若触发多次说明消抖逻辑有误

#### B-4：各 TFT 页面绘制
- **LiveData 页**：DHT11 接好时显示温湿度数值，进度条随数值变化；传感器未接时显示 `Sensor Offline`
- **Curve 页**：等待约 2 个采样周期后出现折线，不足时显示 `Collecting data...`
- **SensorState 页**：CPU 频率应显示 240 MHz，Heap 应为约 200~300 KB
- **Settings 页**：Up/Down 移动光标，OK 进入编辑，修改 Brightness 立即看到屏幕亮度变化

#### B-5：`updateAlarmState()`
- 临时将 Temp High 阈值设置为比当前温度低（如室温 25°C，设 Temp High=20）
- 保存后：GPIO15 应以约 250ms 频率闪烁，状态栏变红显示 `ALARM`
- 恢复阈值后：报警立即解除，GPIO15 变低

---

## 13. 常见陷阱与排错

以下是实现过程中最容易踩的坑，遇到问题先对照这张表。

### A 相关陷阱

| 症状 | 原因 | 解决方法 |
|------|------|----------|
| 上电后死机（看门狗重启） | `prefs.begin()` 后忘了调用 `prefs.end()` | 每个 `prefs.begin()` 必须配对一个 `prefs.end()` |
| WiFi 热点创建失败 | 密码短于 8 位 | WiFi 密码必须 ≥ 8 字符，`loadSettings()` 中已有兜底 |
| `/sensor` 返回 `-999` | `gRt.sensor.online` 为 false | DHT11 未接好，或 B 的采样循环未正确写入 `gRt.sensor` |
| UDP 发出但 PC 收不到 | PC 防火墙拦截了 UDP:9000 | 关闭防火墙或放行 UDP 9000 端口 |
| `snprintf` 输出被截断 | `buf` 数组太小 | `buildSensorJson` 用的 buf=360，`buildSettingsJson` 用的 buf=420，不要缩小 |
| Arduino LED 不亮 | `on_frame` 里 CRC 校验不通过 | 先打印 `meta->crc8_ok` 和 `meta->crc16_ok` 排查；或用 C 注释掉 CRC 检查验证逻辑 |
| Arduino `osrx_feed_done()` 从不触发 | `got_byte` 未正确置 true | 确认 `loop()` 中 `got_byte = true` 在喂字节之后 |

### B 相关陷阱

| 症状 | 原因 | 解决方法 |
|------|------|----------|
| TFT 显示花屏或乱码 | 操作 tft2 前忘记拉低 TFT2 的 CS | 每个 draw 函数的**第一行** `digitalWrite(HW::TFT2.cs, LOW)` |
| TFT 两块屏互相干扰 | 某个 draw 函数结尾漏了 `digitalWrite(cs, HIGH)` | 检查每个 draw 函数结尾 |
| 按键触发两次 | `wasPressed` 未在 stable=HIGH 时清除 | 检查 `scanButtons()` 中 `if (b.stable == HIGH) b.wasPressed = false;` |
| DHT11 读数全是 NaN | 采样间隔太短（< 1 秒） | `gCfg.sampleMs` 默认 1200ms，不要设低于 1000 |
| Curve 页只显示一条水平线 | 温度值归一化范围写错 | 温度用 `(temp + 10.0f) / 60.0f`（对应 -10°C ~ 50°C），不要用 `temp/100` |
| Settings 页按键无响应 | `currentSettingsInputMode()` 判断错误 | 检查 `gUi.exitConfirmMode`、`gUi.textEditMode`、`gUi.settingEdit` 的状态是否正确重置 |
| 背光不亮但代码看起来对 | LEDC channel 冲突 | channel 固定用 0，不要改成其他值 |
| `isnan()` 判断 NaN 无效 | 使用了 `== NAN` 而不是 `isnan()` | 浮点 NaN 不能用 `==` 比较，必须用 `isnan(temp)` |

### 通用陷阱

| 症状 | 原因 | 解决方法 |
|------|------|----------|
| 编译报 `undefined reference` | 函数声明顺序问题（C++ 需要先声明再调用） | 在文件顶部加前向声明，或调整函数顺序 |
| `uint8_t` 运算溢出 | 如 `brightness - 5` 在值为 0 时下溢变 255 | 用 `if (brightness >= 5) brightness -= 5;` 做边界检查 |
| 串口监视器乱码 | 波特率设置错误 | ESP32 用 115200，Arduino 用 9600 |
| OTA/上传失败 | 串口被占用（串口监视器未关闭） | 上传前先关闭串口监视器窗口 |
