# IoT Sensor Projects

A collection of embedded IoT projects built with PlatformIO, featuring real-time sensor monitoring, dual TFT displays, REST APIs, and OSynaptic binary communication.

---

## Projects

### 1. ESP32 Dual-Display DHT11 Monitor
**Folder**: `ESP32-DualDisplay-DHT11-Monitor/`

An ESP32-based temperature and humidity monitoring system with:
- Two ST7735 TFT displays (128×160) — navigation menu + live data pages
- DHT11 sensor with configurable sampling interval and alarm thresholds
- Built-in WiFi Access Point (no external router needed)
- Web dashboard accessible from any browser
- REST API (`/sensor`, `/settings`) for third-party integration
- OSynaptic-FX binary UDP broadcast on port 9000
- NVS persistent configuration (survives power cycles)
- Python monitoring tools (`monitor.py`, `EA.py`) for PC-side data capture

→ [Full documentation](ESP32-DualDisplay-DHT11-Monitor/README.md)

---

### 2. Arduino Uno Device Simulator
**Folder**: `Arduino-Uno-DeviceSimulator/`

An Arduino Uno acting as a smart-home device executor, receiving OSynaptic binary command frames from a Raspberry Pi over UART and reflecting device states via LEDs:

| LED | Color | Device |
|-----|-------|--------|
| D5 | Red | AC Heating |
| D4 | Blue | AC Cooling |
| D3 | Yellow | Window Open |
| D2 | Green | Window Closed |
| D6 | White | Alarm |

→ [Full documentation](Arduino-Uno-DeviceSimulator/docs/device-simulator.md)

---

## System Architecture

```
┌─────────────────────────────────┐
│         PC / Browser            │
│  http://192.168.4.1  (Web UI)   │
│  UDP:9000  (OSynaptic-FX data)  │
└────────────┬────────────────────┘
             │ WiFi (SoftAP)
┌────────────▼────────────────────┐
│     ESP32 — DHT11 Monitor       │
│  Sensor → TFT UI → API → UDP   │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│       Raspberry Pi              │
│  Sends OSynaptic command frames │
└────────────┬────────────────────┘
             │ UART 9600 bps (one-way)
┌────────────▼────────────────────┐
│   Arduino Uno — Device Sim      │
│  Receives frames → drives LEDs  │
└─────────────────────────────────┘
```

---

## Getting Started

### Prerequisites
- [PlatformIO](https://platformio.org/) (VS Code extension or CLI)
- Python 3.8+ (for PC monitoring tools)

### ESP32 Project
```bash
cd ESP32-DualDisplay-DHT11-Monitor
pio run --target upload
pio device monitor --baud 115200
```

Connect to WiFi `ESP32-DHT11-API` (password: `12345678`), then open `http://192.168.4.1` in a browser.

### Arduino Project
```bash
cd Arduino-Uno-DeviceSimulator
pio run --target upload
```

### Python Monitoring Tools
```bash
cd ESP32-DualDisplay-DHT11-Monitor
python -m venv .venv && source .venv/bin/activate
pip install requests opensynaptic
python monitor.py        # dual-channel UDP + HTTP monitor
python EA.py --demo      # demo mode (no device needed)
```

---

## Team

| Role | Responsibilities |
|------|-----------------|
| **C** (Designer) | System architecture, hardware wiring, communication protocol design, documentation, Python tools |
| **A** (Implementer) | Arduino firmware, ESP32 network/API/NVS/OSynaptic layer |
| **B** (Implementer) | ESP32 TFT UI, button input, DHT11 sampling, alarm logic |

See [TEAM_ASSIGNMENT.md](TEAM_ASSIGNMENT.md) for the detailed breakdown.

---

## Libraries Used

| Library | Purpose |
|---------|---------|
| Adafruit GFX | TFT graphics primitives |
| Adafruit ST7735/ST7789 | ST7735 TFT driver |
| DHT sensor library | DHT11 temperature/humidity reading |
| OSynaptic-FX | Binary sensor data encoding & UDP broadcast |
| OSynaptic-RX | Binary frame decoding on Arduino |
