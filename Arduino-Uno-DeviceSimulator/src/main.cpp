#include <Arduino.h>
#include <OSynaptic-RX.h>
#include <string.h>

// ── LED 引脚定义 ─────────────────────────────────────────────
#define LED_AC_HEAT   5   // 红：空调制热
#define LED_AC_COOL   4   // 蓝：空调制冷
#define LED_WIN_OPEN  3   // 黄：窗户开启
#define LED_WIN_CLOSE 2   // 绿：窗户关闭
#define LED_ALARM     6   // 白：报警

// ── 设备状态 ─────────────────────────────────────────────────
// ac_mode: 0=off  1=heat  2=cool
static int  ac_mode     = 0;
static bool window_open = false;
static bool alarm_on    = false;

// ── 更新 LED ─────────────────────────────────────────────────
static void applyLeds() {
    digitalWrite(LED_AC_HEAT,   (ac_mode == 1) ? HIGH : LOW);
    digitalWrite(LED_AC_COOL,   (ac_mode == 2) ? HIGH : LOW);
    digitalWrite(LED_WIN_OPEN,   window_open   ? HIGH : LOW);
    digitalWrite(LED_WIN_CLOSE,  window_open   ? LOW  : HIGH);
    digitalWrite(LED_ALARM,      alarm_on       ? HIGH : LOW);
}

// ── OSynaptic-RX 帧回调 ──────────────────────────────────────
// Pi 发送帧约定（树莓派用 OSynaptic-TX 或 Python hub 发送）：
//   sensor_id="AC",  unit="md",  scaled: 0=off, 10000=heat, 20000=cool
//   sensor_id="WIN", unit="st",  scaled: 0=关,  10000=开
//   sensor_id="ALM", unit="st",  scaled: 0=关,  10000=开
static void on_frame(const osrx_packet_meta  *meta,
                     const osrx_sensor_field *field,
                     const osrx_u8 *, int, void *)
{
    if (!meta->crc8_ok || !meta->crc16_ok) return;  // 丢弃坏帧
    if (!field) return;                               // 非传感器帧

    long val = (long)(field->scaled / OSRX_VALUE_SCALE);

    if (strcmp(field->sensor_id, "AC") == 0) {
        ac_mode = (int)val;   // 0/1/2
    } else if (strcmp(field->sensor_id, "WIN") == 0) {
        window_open = (val != 0);
    } else if (strcmp(field->sensor_id, "ALM") == 0) {
        alarm_on = (val != 0);
    }

    applyLeds();
}

// ── 流式解析器 ────────────────────────────────────────────────
static OSRXParser        parser;
static unsigned long     last_byte_ms = 0;
static bool              got_byte     = false;

// ── 初始化 ────────────────────────────────────────────────────
void setup() {
    Serial.begin(9600);
    pinMode(LED_AC_HEAT,   OUTPUT);
    pinMode(LED_AC_COOL,   OUTPUT);
    pinMode(LED_WIN_OPEN,  OUTPUT);
    pinMode(LED_WIN_CLOSE, OUTPUT);
    pinMode(LED_ALARM,     OUTPUT);
    applyLeds();
    osrx_parser_init(&parser, on_frame, nullptr);
}

// ── 主循环 ────────────────────────────────────────────────────
void loop() {
    while (Serial.available()) {
        osrx_feed_byte(&parser, (osrx_u8)Serial.read());
        last_byte_ms = millis();
        got_byte = true;
    }
    // 15 ms 无新字节 → 判定帧尾，触发解析
    if (got_byte && millis() - last_byte_ms > 15) {
        osrx_feed_done(&parser);
        got_byte = false;
    }
}

