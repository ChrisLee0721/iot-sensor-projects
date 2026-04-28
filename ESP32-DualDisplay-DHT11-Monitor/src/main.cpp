 
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <DHT.h>
#include <Preferences.h>
#include <SPI.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <OSynapticFX.h>
#include <cstring>
namespace HW {
struct TftPins { uint8_t sck, mosi, miso, cs, dc, rst; };
constexpr TftPins TFT1 = {18, 23, 19, 5, 21, 22};
constexpr TftPins TFT2 = {14, 13, 12, 27, 26, 25};
namespace Backlight { constexpr uint8_t Pin = 32, Channel = 0, Res = 8; constexpr uint16_t Freq = 5000; constexpr bool ActiveHigh = true; }
namespace Sensor { constexpr uint8_t DhtPin = 4, DhtType = DHT11, AlarmPin = 15; }
namespace Buttons { constexpr uint8_t Pins[] = {16, 17, 33, 15}; }
namespace Net { constexpr char DefaultSsid[] = "ESP32-DHT11-API", DefaultPass[] = "12345678"; }
constexpr uint16_t BtnDebounceMs = 50;
constexpr uint8_t StableInitMode = INITR_BLACKTAB;
}
namespace UI { constexpr uint16_t Navy = 0x000F, DarkGreen = 0x0320; }
SPIClass vspi(VSPI);
SPIClass hspi(HSPI);
Adafruit_ST7735 tft(&vspi, HW::TFT1.cs, HW::TFT1.dc, HW::TFT1.rst);
Adafruit_ST7735 tft2(&hspi, HW::TFT2.cs, HW::TFT2.dc, HW::TFT2.rst);
DHT dht(HW::Sensor::DhtPin, HW::Sensor::DhtType);
WebServer apiServer(80);
Preferences prefs;
enum class Page : uint8_t { LiveData = 0, PinMap = 1, SensorState = 2, Curve = 3, Settings = 4, Count = 5 };
enum class Btn : uint8_t { Up = 0, Down = 1, Ok = 2, Back = 3, Count = 4 };
enum class SettingField : uint8_t { TempLow = 0, TempHigh = 1, HumiLow = 2, HumiHigh = 3, SampleMs = 4, Brightness = 5, AlarmEnable = 6, WifiSsid = 7, WifiPass = 8, SaveApply = 9, Exit = 10, Count = 11 };
constexpr const char *PAGE_NAMES[] = {"Live Data", "Pin Map", "Sensor State", "Curve", "Settings"};
constexpr const char *SETTING_NAMES[] = {"Temp Low", "Temp High", "Humi Low", "Humi High", "Sample ms", "Brightness", "Alarm", "WiFi SSID", "WiFi PASS", "Save+Apply", "Exit"};
struct AppSettings { float tempLow, tempHigh, humiLow, humiHigh; uint16_t sampleMs; uint8_t brightness; bool alarmEnable; String apSsid, apPass; };
constexpr uint8_t HISTORY_LEN = 64;
constexpr char TEXT_CHARSET[] = " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.@";
constexpr uint8_t WIFI_TEXT_MAX_LEN = 24;
enum class ExitConfirmMode : uint8_t { None = 0, Active = 1 };
struct UiState {
  Page activePage;
  Page lastPageDrawn;
  uint8_t menuCursor;
  uint8_t settingsCursor;
  bool settingEdit;
  bool textEditMode;
  SettingField textEditField;
  String textEditBuffer;
  uint8_t textEditPos;
  ExitConfirmMode exitConfirmMode;
  uint8_t exitConfirmCursor;
  ExitConfirmMode lastExitConfirmMode;
};
struct ButtonState { bool stable, lastRead, pressed, wasPressed; uint32_t lastChangeMs; };
struct SensorData { float temp, humi; bool online, alarmActive; uint32_t lastDhtOkMs; };
struct SystemMetrics { uint8_t cpuLoadPct, heapUsedPct; uint32_t lastDhtReadMs, alarmBlinkMs; bool alarmBlinkState; };
struct RuntimeState { SensorData sensor; SystemMetrics metrics; };
AppSettings gCfg;
UiState gUi = {Page::LiveData, Page::Count, 0, 0, false, false, SettingField::WifiSsid, "", 0, ExitConfirmMode::None, 0, ExitConfirmMode::None};
ButtonState gButtons[static_cast<uint8_t>(Btn::Count)] = {{HIGH, HIGH, false, false, 0}, {HIGH, HIGH, false, false, 0}, {HIGH, HIGH, false, false, 0}, {HIGH, HIGH, false, false, 0}};
RuntimeState gRt = {{NAN, NAN, false, false, 0}, {0, 0, 0, 0, false}};
float gTempHistory[HISTORY_LEN];
float gHumiHistory[HISTORY_LEN];
uint8_t gHistoryIndex = 0;
bool gHistoryFilled = false;
// --- OSynaptic-FX UDP broadcast ---
static WiFiUDP           g_osfxUdp;
static WiFiUDP           g_pingUdp;          // plain-text heartbeat (debug)
static osfx_easy_context g_osfxCtx;
static uint8_t           g_osfxBuf[512];
static uint32_t          g_osfxEmitCount = 0UL;
static const uint16_t    OSFX_UDP_PORT   = 9000U;
static const uint32_t    OSFX_RESYNC_N   = 30UL;
// ----------------------------------
static const char WEB_INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>ESP32 DHT11</title><style>body{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:12px}section{background:#111827;border:1px solid #334155;padding:8px;margin:8px 0;border-radius:8px}input{width:100%;padding:5px;background:#020617;color:#e2e8f0;border:1px solid #334155}button{padding:7px 10px;background:#2563eb;color:#fff;border:0;border-radius:6px;margin-top:8px}</style></head><body>
<h3>ESP32 DHT11</h3><section><div id='live'>loading...</div></section>
<section><label>Temp Low<input id='tLow'></label><label>Temp High<input id='tHigh'></label><label>Humi Low<input id='hLow'></label><label>Humi High<input id='hHigh'></label><label>Sample ms<input id='smp'></label><label>Brightness<input id='bl'></label><label>Alarm 1/0<input id='alm'></label><label>SSID<input id='ssid'></label><label>PASS<input id='pass'></label><button onclick='saveCfg()'>Save</button></section>
<script>
const $=id=>document.getElementById(id);
async function tick(){const s=await (await fetch('/sensor')).json();$('live').textContent=`online=${s.online} alarm=${s.alarm} temp=${s.temp_c}C humi=${s.humi_pct}%`;}
async function loadCfg(){const c=await (await fetch('/settings')).json();tLow.value=c.temp_low;tHigh.value=c.temp_high;hLow.value=c.humi_low;hHigh.value=c.humi_high;smp.value=c.sample_ms;bl.value=c.brightness;alm.value=c.alarm_enable?1:0;ssid.value=c.ssid;pass.value=c.pass;}
async function saveCfg(){const q=`temp_low=${encodeURIComponent(tLow.value)}&temp_high=${encodeURIComponent(tHigh.value)}&humi_low=${encodeURIComponent(hLow.value)}&humi_high=${encodeURIComponent(hHigh.value)}&sample_ms=${encodeURIComponent(smp.value)}&brightness=${encodeURIComponent(bl.value)}&alarm_enable=${encodeURIComponent(alm.value)}&ssid=${encodeURIComponent(ssid.value)}&pass=${encodeURIComponent(pass.value)}`;const r=await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:q});alert(await r.text());loadCfg();}
setInterval(tick,1500);tick();loadCfg();
</script></body></html>
)HTML";
void setupBacklightPwm() {
  ledcSetup(HW::Backlight::Channel, HW::Backlight::Freq, HW::Backlight::Res);
  ledcAttachPin(HW::Backlight::Pin, HW::Backlight::Channel);
}
void setBacklightPercent(uint8_t percent) {
  if (percent > 100) {
    percent = 100;
  }
  uint8_t duty = static_cast<uint8_t>((percent * 255) / 100);
  if (!HW::Backlight::ActiveHigh) {
    duty = 255 - duty;
  }
  ledcWrite(HW::Backlight::Channel, duty);
}
void setAlarmOutput(bool on) {
  digitalWrite(HW::Sensor::AlarmPin, on ? HIGH : LOW);
}
String safeStringArg(const String &v, uint8_t maxLen) {
  String out = v;
  out.trim();
  if (out.length() > maxLen) {
    out = out.substring(0, maxLen);
  }
  return out;
}
int findCharIndex(char c) {
  for (int i = 0; TEXT_CHARSET[i] != '\0'; ++i) {
    if (TEXT_CHARSET[i] == c) {
      return i;
    }
  }
  return 0;
}
void trimTrailingSpaces(String &s) {
  while (s.length() > 0 && s[s.length() - 1] == ' ') {
    s.remove(s.length() - 1);
  }
}
void beginTextEdit(SettingField field) {
  gUi.textEditMode = true;
  gUi.textEditField = field;
  gUi.textEditBuffer = (field == SettingField::WifiSsid) ? gCfg.apSsid : gCfg.apPass;
  if (gUi.textEditBuffer.length() == 0) {
    gUi.textEditBuffer = " ";
  }
  if (gUi.textEditBuffer.length() > WIFI_TEXT_MAX_LEN) {
    gUi.textEditBuffer = gUi.textEditBuffer.substring(0, WIFI_TEXT_MAX_LEN);
  }
  gUi.textEditPos = 0;
}
void commitTextEdit() {
  String out = gUi.textEditBuffer;
  trimTrailingSpaces(out);
  if (gUi.textEditField == SettingField::WifiSsid) {
    if (out.length() < 1) out = HW::Net::DefaultSsid;
    gCfg.apSsid = out;
  } else {
    if (out.length() < 8) out = HW::Net::DefaultPass;
    gCfg.apPass = out;
  }
  gUi.textEditMode = false;
}
void loadSettings() {
  prefs.begin("cfg", true);
  gCfg.tempLow = prefs.getFloat("tLow", 18.0f);
  gCfg.tempHigh = prefs.getFloat("tHigh", 32.0f);
  gCfg.humiLow = prefs.getFloat("hLow", 30.0f);
  gCfg.humiHigh = prefs.getFloat("hHigh", 80.0f);
  gCfg.sampleMs = prefs.getUInt("smp", 1200);
  gCfg.brightness = prefs.getUChar("bl", 80);
  gCfg.alarmEnable = prefs.getBool("alarmEn", true);
  gCfg.apSsid = prefs.getString("ssid", HW::Net::DefaultSsid);
  gCfg.apPass = prefs.getString("pass", HW::Net::DefaultPass);
  prefs.end();
  if (gCfg.sampleMs < 500) gCfg.sampleMs = 500;
  if (gCfg.sampleMs > 10000) gCfg.sampleMs = 10000;
  if (gCfg.brightness > 100) gCfg.brightness = 100;
  if (gCfg.apSsid.length() < 1) gCfg.apSsid = HW::Net::DefaultSsid;
  if (gCfg.apPass.length() < 8) gCfg.apPass = HW::Net::DefaultPass;
}
void saveSettings() {
  prefs.begin("cfg", false);
  prefs.putFloat("tLow", gCfg.tempLow);
  prefs.putFloat("tHigh", gCfg.tempHigh);
  prefs.putFloat("hLow", gCfg.humiLow);
  prefs.putFloat("hHigh", gCfg.humiHigh);
  prefs.putUInt("smp", gCfg.sampleMs);
  prefs.putUChar("bl", gCfg.brightness);
  prefs.putBool("alarmEn", gCfg.alarmEnable);
  prefs.putString("ssid", gCfg.apSsid);
  prefs.putString("pass", gCfg.apPass);
  prefs.end();
}
void restartSoftAp() {
  WiFi.softAPdisconnect(true);
  bool ok = WiFi.softAP(gCfg.apSsid.c_str(), gCfg.apPass.c_str());
  if (ok) {
    Serial.printf("[API] AP restarted: %s\n", gCfg.apSsid.c_str());
    Serial.printf("[API] AP IP: %s\n", WiFi.softAPIP().toString().c_str());
  } else {
    Serial.println("[API] AP restart failed");
  }
}
String buildSensorJson() {
  char buf[360];
  snprintf(buf, sizeof(buf),
           "{\"online\":%s,\"alarm\":%s,\"temp_c\":%.2f,\"humi_pct\":%.2f,\"last_ok_ms\":%lu,\"uptime_ms\":%lu,\"cpu_mhz\":%u,\"cpu_load_pct\":%u,\"heap_free\":%u,\"heap_used_pct\":%u}",
           gRt.sensor.online ? "true" : "false",
           gRt.sensor.alarmActive ? "true" : "false",
           gRt.sensor.online ? gRt.sensor.temp : -999.0f,
           gRt.sensor.online ? gRt.sensor.humi : -999.0f,
           static_cast<unsigned long>(gRt.sensor.lastDhtOkMs),
           static_cast<unsigned long>(millis()),
           static_cast<unsigned int>(ESP.getCpuFreqMHz()),
           static_cast<unsigned int>(gRt.metrics.cpuLoadPct),
           static_cast<unsigned int>(ESP.getFreeHeap()),
           static_cast<unsigned int>(gRt.metrics.heapUsedPct));
  return String(buf);
}
String buildSettingsJson() {
  char buf[420];
  snprintf(buf, sizeof(buf),
           "{\"temp_low\":%.1f,\"temp_high\":%.1f,\"humi_low\":%.1f,\"humi_high\":%.1f,\"sample_ms\":%u,\"brightness\":%u,\"alarm_enable\":%s,\"ssid\":\"%s\",\"pass\":\"%s\"}",
           gCfg.tempLow,
           gCfg.tempHigh,
           gCfg.humiLow,
           gCfg.humiHigh,
           static_cast<unsigned int>(gCfg.sampleMs),
           static_cast<unsigned int>(gCfg.brightness),
           gCfg.alarmEnable ? "true" : "false",
           gCfg.apSsid.c_str(),
           gCfg.apPass.c_str());
  return String(buf);
}
void setupWifiApi() {
  WiFi.mode(WIFI_AP); restartSoftAp();
  apiServer.on("/", HTTP_GET, []() { apiServer.send_P(200, "text/html", WEB_INDEX_HTML); });
  apiServer.on("/sensor", HTTP_GET, []() { apiServer.send(200, "application/json", buildSensorJson()); });
  apiServer.on("/settings", HTTP_GET, []() { apiServer.send(200, "application/json", buildSettingsJson()); });
  apiServer.on("/settings", HTTP_POST, []() {
    if (apiServer.hasArg("temp_low")) gCfg.tempLow = apiServer.arg("temp_low").toFloat();
    if (apiServer.hasArg("temp_high")) gCfg.tempHigh = apiServer.arg("temp_high").toFloat();
    if (apiServer.hasArg("humi_low")) gCfg.humiLow = apiServer.arg("humi_low").toFloat();
    if (apiServer.hasArg("humi_high")) gCfg.humiHigh = apiServer.arg("humi_high").toFloat();
    if (apiServer.hasArg("sample_ms")) gCfg.sampleMs = static_cast<uint16_t>(apiServer.arg("sample_ms").toInt());
    if (apiServer.hasArg("brightness")) gCfg.brightness = static_cast<uint8_t>(apiServer.arg("brightness").toInt());
    if (apiServer.hasArg("alarm_enable")) gCfg.alarmEnable = (apiServer.arg("alarm_enable").toInt() != 0);
    if (apiServer.hasArg("ssid")) gCfg.apSsid = safeStringArg(apiServer.arg("ssid"), 24);
    if (apiServer.hasArg("pass")) gCfg.apPass = safeStringArg(apiServer.arg("pass"), 24);
    if (gCfg.tempLow > gCfg.tempHigh - 0.5f) gCfg.tempLow = gCfg.tempHigh - 0.5f;
    if (gCfg.humiLow > gCfg.humiHigh - 1.0f) gCfg.humiLow = gCfg.humiHigh - 1.0f;
    if (gCfg.sampleMs < 500) gCfg.sampleMs = 500;
    if (gCfg.sampleMs > 10000) gCfg.sampleMs = 10000;
    if (gCfg.brightness > 100) gCfg.brightness = 100;
    if (gCfg.apSsid.length() < 1) gCfg.apSsid = HW::Net::DefaultSsid;
    if (gCfg.apPass.length() < 8) gCfg.apPass = HW::Net::DefaultPass;
    saveSettings(); setBacklightPercent(gCfg.brightness); restartSoftAp(); apiServer.send(200, "text/plain", "saved");
  });
  apiServer.begin(); Serial.println("[API] HTTP server started");
}
void drawHeaderTft2(const char *title) {
  tft2.fillRect(0, 0, 128, 24, UI::Navy);
  tft2.fillRect(0, 0, 128, 12, UI::Navy);
  tft2.setTextSize(1);
  tft2.setTextColor(ST77XX_YELLOW, UI::Navy);
  tft2.setCursor(4, 6);
  tft2.print(title);
  tft2.drawFastHLine(0, 24, 128, ST77XX_BLUE);
}
void drawMenuOnTft1() {
  digitalWrite(HW::TFT1.cs, LOW);
  tft.fillScreen(ST77XX_BLACK);
  tft.fillRect(0, 0, 128, 24, UI::Navy);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_YELLOW, UI::Navy);
  tft.setCursor(4, 7);
  tft.print("TFT1 MENU");
  for (uint8_t i = 0; i < static_cast<uint8_t>(Page::Count); ++i) {
    const int y = 30 + static_cast<int>(i) * 24;
    const bool selected = (i == gUi.menuCursor);
    tft.fillRect(6, y - 2, 116, 18, selected ? ST77XX_BLUE : ST77XX_BLACK);
    tft.drawRect(6, y - 2, 116, 18, ST77XX_WHITE);
    tft.setCursor(12, y + 2);
    tft.setTextColor(selected ? ST77XX_WHITE : ST77XX_CYAN, selected ? ST77XX_BLUE : ST77XX_BLACK);
    tft.print(PAGE_NAMES[i]);
  }
  tft.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
  tft.setCursor(6, 146);
  tft.print("DHT11 Menu");
  digitalWrite(HW::TFT1.cs, HIGH);
}
void drawLiveDataOnTft2(bool fullRefresh) {
  digitalWrite(HW::TFT2.cs, LOW);
  if (fullRefresh) {
    tft2.fillScreen(ST77XX_BLACK);
    drawHeaderTft2("TFT2 LIVE DATA");
    tft2.fillRect(0, 24, 128, 136, ST77XX_BLACK);
    tft2.drawRect(4, 44, 120, 34, ST77XX_BLUE);
    tft2.drawRect(34, 84, 90, 8, ST77XX_WHITE);
    tft2.drawRect(34, 97, 90, 8, ST77XX_WHITE);
    tft2.drawRect(4, 108, 120, 48, ST77XX_MAGENTA);
    tft2.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
    tft2.setCursor(8, 112);
    tft2.print("DHT11 4-Pin");
    tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
    tft2.setCursor(8, 124);
    tft2.print("1:VCC 2:DATA");
    tft2.setCursor(8, 136);
    tft2.print("3:NC  4:GND");
    tft2.setTextColor(ST77XX_GREEN, ST77XX_BLACK);
    tft2.setCursor(8, 148);
    tft2.print("DATA -> GPIO4");
  }
  uint16_t statusBg = gRt.sensor.alarmActive ? ST77XX_RED : (gRt.sensor.online ? UI::DarkGreen : ST77XX_RED);
  tft2.fillRect(4, 26, 76, 12, statusBg);
  tft2.setTextColor(ST77XX_WHITE, statusBg);
  tft2.setCursor(8, 28);
  if (gRt.sensor.alarmActive) {
    tft2.print("ALARM");
  } else {
    tft2.print(gRt.sensor.online ? "SENSOR OK" : "OFFLINE");
  }
  tft2.fillRect(8, 48, 112, 22, ST77XX_BLACK);
  tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft2.setCursor(8, 48);
  if (gRt.sensor.online) {
    tft2.printf("Temp: %4.1f C", gRt.sensor.temp);
    tft2.setCursor(8, 62);
    tft2.printf("Humi: %4.1f %%", gRt.sensor.humi);
  } else {
    tft2.setTextColor(ST77XX_RED, ST77XX_BLACK);
    tft2.print("Sensor Offline");
    tft2.setCursor(8, 62);
    tft2.print("Check GPIO4");
  }
  tft2.fillRect(35, 85, 88, 6, ST77XX_BLACK);
  tft2.fillRect(35, 98, 88, 6, ST77XX_BLACK);
  if (gRt.sensor.online) {
    int tempBar = static_cast<int>(gRt.sensor.temp * 2.0f);
    int humiBar = static_cast<int>(gRt.sensor.humi);
    if (tempBar < 0) tempBar = 0;
    if (tempBar > 100) tempBar = 100;
    if (humiBar < 0) humiBar = 0;
    if (humiBar > 100) humiBar = 100;
    tft2.setTextColor(ST77XX_CYAN, ST77XX_BLACK);
    tft2.setCursor(4, 82);
    tft2.print("Temp");
    tft2.fillRect(35, 85, tempBar * 88 / 100, 6, ST77XX_RED);
    tft2.setCursor(4, 95);
    tft2.print("Humi");
    tft2.fillRect(35, 98, humiBar * 88 / 100, 6, ST77XX_GREEN);
  }
  digitalWrite(HW::TFT2.cs, HIGH);
}
void drawPinMapOnTft2() {
  digitalWrite(HW::TFT2.cs, LOW);
  tft2.fillScreen(ST77XX_BLACK); drawHeaderTft2("TFT2 PIN MAP");
  tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft2.setCursor(8, 40); tft2.print("DHT11 Pinout");
  tft2.setCursor(8, 64); tft2.print("1: VCC");
  tft2.setCursor(8, 78); tft2.print("2: DATA -> GPIO4");
  tft2.setCursor(8, 92); tft2.print("3: NC");
  tft2.setCursor(8, 106); tft2.print("4: GND");
  digitalWrite(HW::TFT2.cs, HIGH);
}
void drawSensorStateOnTft2(bool fullRefresh) {
  digitalWrite(HW::TFT2.cs, LOW);
  if (fullRefresh) {
    tft2.fillScreen(ST77XX_BLACK);
    drawHeaderTft2("TFT2 SYS STATE");
  }
  tft2.fillRect(0, 24, 128, 136, ST77XX_BLACK);

  tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft2.setCursor(6, 34);
  tft2.print("Status:");
  tft2.setTextColor(gRt.sensor.online ? ST77XX_GREEN : ST77XX_RED, ST77XX_BLACK);
  tft2.setCursor(60, 34);
  tft2.print(gRt.sensor.online ? "ONLINE" : "OFFLINE");

  tft2.setTextColor(ST77XX_CYAN, ST77XX_BLACK);
  tft2.setCursor(6, 52);
  tft2.printf("CPU: %u MHz", static_cast<unsigned int>(ESP.getCpuFreqMHz()));
  tft2.setCursor(6, 66);
  tft2.printf("Heap:%u", static_cast<unsigned int>(ESP.getFreeHeap()));
  tft2.setCursor(6, 80);
  tft2.printf("Alarm:%s", gRt.sensor.alarmActive ? "ON" : "OFF");

  tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft2.setCursor(6, 94);
  tft2.printf("CPU Load:%u%%", static_cast<unsigned int>(gRt.metrics.cpuLoadPct));
  tft2.drawRect(70, 96, 52, 7, ST77XX_WHITE);
  tft2.fillRect(71, 97, (gRt.metrics.cpuLoadPct * 50) / 100, 5, ST77XX_RED);

  tft2.setCursor(6, 106);
  tft2.printf("Mem Used:%u%%", static_cast<unsigned int>(gRt.metrics.heapUsedPct));
  tft2.drawRect(70, 108, 52, 7, ST77XX_WHITE);
  tft2.fillRect(71, 109, (gRt.metrics.heapUsedPct * 50) / 100, 5, ST77XX_GREEN);

  tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK);
  tft2.setCursor(6, 118);
  if (gRt.sensor.online) {
    tft2.printf("T:%.1fC H:%.1f%%", gRt.sensor.temp, gRt.sensor.humi);
  } else {
    tft2.print("T:N/A H:N/A");
  }

  tft2.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
  tft2.setCursor(6, 132);
  tft2.print("AP:");
  tft2.setCursor(6, 146);
  tft2.print(gCfg.apSsid.substring(0, 16));
  digitalWrite(HW::TFT2.cs, HIGH);
}
void drawCurveOnTft2(bool fullRefresh) {
  digitalWrite(HW::TFT2.cs, LOW);
  if (fullRefresh) {
    tft2.fillScreen(ST77XX_BLACK);
    drawHeaderTft2("TFT2 CURVE");
  }
  tft2.fillRect(0, 24, 128, 136, ST77XX_BLACK);

  const int x0 = 8;
  const int y0 = 32;
  const int w = 112;
  const int h = 110;
  tft2.drawRect(x0, y0, w, h, ST77XX_WHITE);
  tft2.drawFastHLine(x0, y0 + h / 2, w, ST77XX_BLUE);
  tft2.setTextColor(ST77XX_CYAN, ST77XX_BLACK);
  tft2.setCursor(8, 146);
  tft2.print("R:Temp G:Humi");

  uint8_t valid = gHistoryFilled ? HISTORY_LEN : gHistoryIndex;
  if (valid >= 2) {
    const uint8_t drawCount = (valid > w - 2) ? (w - 2) : valid;
    const uint8_t start = (valid > drawCount) ? (valid - drawCount) : 0;
    int prevX = 0;
    int prevTempY = 0;
    int prevHumiY = 0;

    for (uint8_t i = 0; i < drawCount; ++i) {
      uint8_t logical = start + i;
      uint8_t idx = gHistoryFilled ? (gHistoryIndex + logical) % HISTORY_LEN : logical;
      float temp = gTempHistory[idx];
      float humi = gHumiHistory[idx];

      float tn = (temp + 10.0f) / 60.0f;
      if (tn < 0.0f) tn = 0.0f;
      if (tn > 1.0f) tn = 1.0f;
      float hn = humi / 100.0f;
      if (hn < 0.0f) hn = 0.0f;
      if (hn > 1.0f) hn = 1.0f;

      int x = x0 + 1 + i;
      int tempY = y0 + h - 2 - static_cast<int>(tn * (h - 3));
      int humiY = y0 + h - 2 - static_cast<int>(hn * (h - 3));

      if (i > 0) {
        tft2.drawLine(prevX, prevTempY, x, tempY, ST77XX_RED);
        tft2.drawLine(prevX, prevHumiY, x, humiY, ST77XX_GREEN);
      }
      prevX = x;
      prevTempY = tempY;
      prevHumiY = humiY;
    }
  } else {
    tft2.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
    tft2.setCursor(18, 84);
    tft2.print("Collecting data...");
  }
  digitalWrite(HW::TFT2.cs, HIGH);
}
void drawSettingTempLow() { tft2.printf("%.1f", gCfg.tempLow); }
void drawSettingTempHigh() { tft2.printf("%.1f", gCfg.tempHigh); }
void drawSettingHumiLow() { tft2.printf("%.1f", gCfg.humiLow); }
void drawSettingHumiHigh() { tft2.printf("%.1f", gCfg.humiHigh); }
void drawSettingSampleMs() { tft2.printf("%u", static_cast<unsigned int>(gCfg.sampleMs)); }
void drawSettingBrightness() { tft2.printf("%u%%", static_cast<unsigned int>(gCfg.brightness)); }
void drawSettingAlarmEnable() { tft2.print(gCfg.alarmEnable ? "ON" : "OFF"); }
void drawSettingWifiSsid() { tft2.print(gCfg.apSsid.substring(0, 10)); }
void drawSettingWifiPass() {
  if (gCfg.apPass.length() <= 4) tft2.print(gCfg.apPass);
  else { tft2.print(gCfg.apPass.substring(0, 2)); tft2.print("***"); tft2.print(gCfg.apPass.substring(gCfg.apPass.length() - 2)); }
}
void drawSettingOk() { tft2.print("OK"); }
using SettingValueDrawFn = void (*)();
constexpr SettingValueDrawFn SETTING_VALUE_DRAWERS[] = {
    drawSettingTempLow, drawSettingTempHigh, drawSettingHumiLow, drawSettingHumiHigh, drawSettingSampleMs, drawSettingBrightness,
    drawSettingAlarmEnable, drawSettingWifiSsid, drawSettingWifiPass, drawSettingOk, drawSettingOk};
void drawSettingsOnTft2(bool fullRefresh) {
  digitalWrite(HW::TFT2.cs, LOW);
  if (fullRefresh) { tft2.fillScreen(ST77XX_BLACK); drawHeaderTft2("TFT2 SETTINGS"); }
  tft2.fillRect(0, 24, 128, 136, ST77XX_BLACK);
  uint8_t start = (gUi.settingsCursor > 4) ? (gUi.settingsCursor - 4) : 0;
  for (uint8_t i = 0; i < 6; ++i) {
    uint8_t idx = start + i;
    if (idx >= static_cast<uint8_t>(SettingField::Count)) break;
    int y = 30 + i * 18; bool selected = (idx == gUi.settingsCursor);
    tft2.fillRect(2, y - 1, 124, 16, selected ? ST77XX_BLUE : ST77XX_BLACK);
    tft2.setTextColor(selected ? ST77XX_WHITE : ST77XX_CYAN, selected ? ST77XX_BLUE : ST77XX_BLACK);
    tft2.setCursor(4, y + 2); tft2.print(SETTING_NAMES[idx]); tft2.setCursor(72, y + 2); SETTING_VALUE_DRAWERS[idx]();
  }
  tft2.setTextColor(ST77XX_YELLOW, ST77XX_BLACK); tft2.setCursor(4, 132);
  if (gUi.textEditMode) {
    tft2.print("WiFi Text Edit Mode"); tft2.setCursor(4, 142); tft2.print("UP/DN char OK next");
    String label = (gUi.textEditField == SettingField::WifiSsid) ? "SSID" : "PASS";
    tft2.fillRect(0, 112, 128, 18, ST77XX_BLACK); tft2.setTextColor(ST77XX_WHITE, ST77XX_BLACK); tft2.setCursor(4, 114); tft2.print(label); tft2.print(":");
    String shown = gUi.textEditBuffer;
    if (shown.length() > 14) shown = shown.substring(0, 14);
    tft2.setCursor(34, 114); tft2.print(shown);
    uint8_t drawPos = gUi.textEditPos;
    if (drawPos > 13) drawPos = 13;
    uint8_t cursorX = 34 + drawPos * 6;
    if (gUi.textEditPos >= gUi.textEditBuffer.length()) {
      tft2.setCursor(104, 114); tft2.print("DONE");
      cursorX = 104;
    }
    tft2.drawFastHLine(cursorX, 126, 6, ST77XX_RED);
  } else {
    tft2.print("WiFi SSID/PASS editable"); tft2.setCursor(4, 142);
    tft2.print(gUi.settingEdit ? "EDIT: UP/DN value" : "UP/DN sel OK edit");
  }
  digitalWrite(HW::TFT2.cs, HIGH);
}
void drawExitConfirmDialog() {
  digitalWrite(HW::TFT2.cs, LOW);
  tft2.fillRect(10, 48, 108, 102, ST77XX_BLACK);
  const int dialogX = 12;
  const int dialogY = 50;
  const int dialogW = 104;
  const int dialogH = 80;
  tft2.fillRect(dialogX, dialogY, dialogW, dialogH, UI::Navy);
  tft2.drawRect(dialogX, dialogY, dialogW, dialogH, ST77XX_WHITE);
  tft2.setTextColor(ST77XX_YELLOW, UI::Navy);
  tft2.setCursor(20, 58);
  tft2.print("Exit WiFi Edit?");
  const int option1Y = 76;
  const int option2Y = 92;
  const int optionX = 18;
  bool isOption1Selected = (gUi.exitConfirmCursor == 0);
  tft2.fillRect(optionX - 2, option1Y - 1, 100, 12, isOption1Selected ? ST77XX_BLUE : UI::Navy);
  tft2.setTextColor(isOption1Selected ? ST77XX_WHITE : ST77XX_CYAN, isOption1Selected ? ST77XX_BLUE : UI::Navy);
  tft2.setCursor(optionX, option1Y);
  tft2.print("[Save & Apply]");
  bool isOption2Selected = (gUi.exitConfirmCursor == 1);
  tft2.fillRect(optionX - 2, option2Y - 1, 100, 12, isOption2Selected ? ST77XX_BLUE : UI::Navy);
  tft2.setTextColor(isOption2Selected ? ST77XX_WHITE : ST77XX_CYAN, isOption2Selected ? ST77XX_BLUE : UI::Navy);
  tft2.setCursor(optionX, option2Y);
  tft2.print("[Discard Exit]");
  tft2.setTextColor(ST77XX_YELLOW, ST77XX_BLACK);
  tft2.setCursor(16, 116);
  tft2.print("UP/DN select OK");
  tft2.setCursor(16, 128);
  tft2.print("BACK to continue");
  digitalWrite(HW::TFT2.cs, HIGH);
}
void drawCurrentPageOnTft2(bool fullRefresh) {
  using PageDrawFn = void (*)(bool);
  static const PageDrawFn PAGE_DRAWERS[] = {drawLiveDataOnTft2, [](bool) { drawPinMapOnTft2(); }, drawSensorStateOnTft2, drawCurveOnTft2, drawSettingsOnTft2};
  if (fullRefresh) {
    digitalWrite(HW::TFT2.cs, LOW);
    tft2.fillScreen(ST77XX_BLACK);
    digitalWrite(HW::TFT2.cs, HIGH);
  }
  PAGE_DRAWERS[static_cast<uint8_t>(gUi.activePage)](fullRefresh);
  if (gUi.exitConfirmMode == ExitConfirmMode::Active) {
    drawExitConfirmDialog();
  }
  gUi.lastPageDrawn = gUi.activePage;
}
void hardwareResetTft(uint8_t rstPin) {
  pinMode(rstPin, OUTPUT);
  digitalWrite(rstPin, HIGH);
  delay(5);
  digitalWrite(rstPin, LOW);
  delay(20);
  digitalWrite(rstPin, HIGH);
  delay(120);
}
void initTfts() {
  pinMode(HW::TFT1.cs, OUTPUT);
  pinMode(HW::TFT1.dc, OUTPUT);
  pinMode(HW::TFT1.rst, OUTPUT);
  pinMode(HW::TFT2.cs, OUTPUT);
  pinMode(HW::TFT2.dc, OUTPUT);
  pinMode(HW::TFT2.rst, OUTPUT);
  digitalWrite(HW::TFT1.dc, HIGH);
  digitalWrite(HW::TFT1.cs, HIGH);
  digitalWrite(HW::TFT2.dc, HIGH);
  digitalWrite(HW::TFT2.cs, HIGH);
  vspi.begin(HW::TFT1.sck, HW::TFT1.miso, HW::TFT1.mosi, HW::TFT1.cs);
  hspi.begin(HW::TFT2.sck, HW::TFT2.miso, HW::TFT2.mosi, HW::TFT2.cs);
  digitalWrite(HW::TFT1.cs, LOW);
  hardwareResetTft(HW::TFT1.rst);
  tft.initR(HW::StableInitMode);
  tft.setRotation(0);
  digitalWrite(HW::TFT1.cs, HIGH);
  digitalWrite(HW::TFT2.cs, LOW);
  hardwareResetTft(HW::TFT2.rst);
  tft2.initR(HW::StableInitMode);
  tft2.setRotation(0);
  digitalWrite(HW::TFT2.cs, HIGH);
}
void initButtons() {
  for (uint8_t i = 0; i < static_cast<uint8_t>(Btn::Count); ++i) {
    pinMode(HW::Buttons::Pins[i], INPUT_PULLUP);
    gButtons[i].stable = HIGH;
    gButtons[i].lastRead = HIGH;
    gButtons[i].pressed = false;
    gButtons[i].lastChangeMs = 0;
    gButtons[i].wasPressed = false;
  }
}
void scanButtons(uint32_t nowMs) {
  for (uint8_t i = 0; i < static_cast<uint8_t>(Btn::Count); ++i) {
    ButtonState &b = gButtons[i];
    bool raw = digitalRead(HW::Buttons::Pins[i]);
    if (raw != b.lastRead) {
      b.lastRead = raw;
      b.lastChangeMs = nowMs;
    }
    if ((nowMs - b.lastChangeMs) >= HW::BtnDebounceMs && raw != b.stable) {
      b.stable = raw;
      if (b.stable == LOW && !b.wasPressed) {
        b.pressed = true;
        b.wasPressed = true;
      }
    }
    if (b.stable == HIGH) {
      b.wasPressed = false;
    }
  }
}
bool consumeBtn(Btn id) {
  ButtonState &b = gButtons[static_cast<uint8_t>(id)];
  if (b.pressed) {
    b.pressed = false;
    return true;
  }
  return false;
}
enum class SettingsInputMode : uint8_t { Confirm = 0, TextEdit = 1, ValueEdit = 2, List = 3 };
SettingsInputMode currentSettingsInputMode() {
  if (gUi.exitConfirmMode == ExitConfirmMode::Active) return SettingsInputMode::Confirm;
  if (gUi.textEditMode) return SettingsInputMode::TextEdit;
  if (gUi.settingEdit) return SettingsInputMode::ValueEdit;
  return SettingsInputMode::List;
}
bool handleSettingsConfirmMode() {
  bool changed = false;
  if (consumeBtn(Btn::Up) || consumeBtn(Btn::Down)) { gUi.exitConfirmCursor = (gUi.exitConfirmCursor + 1) % 2; changed = true; }
  if (consumeBtn(Btn::Ok)) {
    if (gUi.exitConfirmCursor == 0) { commitTextEdit(); saveSettings(); setBacklightPercent(gCfg.brightness); restartSoftAp(); }
    else gUi.textEditMode = false;
    gUi.settingEdit = false; gUi.exitConfirmMode = ExitConfirmMode::None; gUi.exitConfirmCursor = 0;
    changed = true;
  }
  if (consumeBtn(Btn::Back)) { gUi.exitConfirmMode = ExitConfirmMode::None; gUi.exitConfirmCursor = 0; changed = true; }
  return changed;
}
bool handleSettingsTextEditMode() {
  bool changed = false;
  bool upPressed = consumeBtn(Btn::Up);
  bool downPressed = consumeBtn(Btn::Down);
  if (upPressed || downPressed) {
    int step = upPressed ? 1 : -1;
    if (gUi.textEditBuffer.length() == 0) gUi.textEditBuffer = " ";
    if (gUi.textEditPos < gUi.textEditBuffer.length()) {
      int idx = findCharIndex(gUi.textEditBuffer[gUi.textEditPos]);
      int charsetLen = static_cast<int>(strlen(TEXT_CHARSET));
      idx = (idx + charsetLen + step) % charsetLen;
      gUi.textEditBuffer.setCharAt(gUi.textEditPos, TEXT_CHARSET[idx]);
    }
    changed = true;
  }
  if (consumeBtn(Btn::Ok)) {
    if (gUi.textEditPos < gUi.textEditBuffer.length()) {
      if (gUi.textEditPos == gUi.textEditBuffer.length() - 1 && gUi.textEditBuffer.length() < WIFI_TEXT_MAX_LEN) {
        gUi.textEditBuffer += ' ';
      }
      ++gUi.textEditPos;
    } else {
      commitTextEdit();
      gUi.settingEdit = false;
    }
    changed = true;
  }
  if (consumeBtn(Btn::Back)) { gUi.exitConfirmMode = ExitConfirmMode::Active; gUi.exitConfirmCursor = 0; changed = true; }
  return changed;
}
void applySettingDelta(int8_t d) {
  switch (static_cast<SettingField>(gUi.settingsCursor)) {
    case SettingField::TempLow:
      gCfg.tempLow += 0.5f * d;
      if (gCfg.tempLow < -10.0f) gCfg.tempLow = -10.0f;
      if (gCfg.tempLow > gCfg.tempHigh - 0.5f) gCfg.tempLow = gCfg.tempHigh - 0.5f;
      break;
    case SettingField::TempHigh:
      gCfg.tempHigh += 0.5f * d;
      if (gCfg.tempHigh > 60.0f) gCfg.tempHigh = 60.0f;
      if (gCfg.tempHigh < gCfg.tempLow + 0.5f) gCfg.tempHigh = gCfg.tempLow + 0.5f;
      break;
    case SettingField::HumiLow:
      gCfg.humiLow += 1.0f * d;
      if (gCfg.humiLow < 0.0f) gCfg.humiLow = 0.0f;
      if (gCfg.humiLow > gCfg.humiHigh - 1.0f) gCfg.humiLow = gCfg.humiHigh - 1.0f;
      break;
    case SettingField::HumiHigh:
      gCfg.humiHigh += 1.0f * d;
      if (gCfg.humiHigh > 100.0f) gCfg.humiHigh = 100.0f;
      if (gCfg.humiHigh < gCfg.humiLow + 1.0f) gCfg.humiHigh = gCfg.humiLow + 1.0f;
      break;
    case SettingField::SampleMs:
      gCfg.sampleMs = static_cast<uint16_t>(gCfg.sampleMs + 100 * d);
      if (gCfg.sampleMs < 500) gCfg.sampleMs = 500;
      if (gCfg.sampleMs > 10000) gCfg.sampleMs = 10000;
      break;
    case SettingField::Brightness:
      if (d > 0 && gCfg.brightness < 100) gCfg.brightness += 5;
      if (d < 0 && gCfg.brightness > 5) gCfg.brightness -= 5;
      setBacklightPercent(gCfg.brightness);
      break;
    case SettingField::AlarmEnable:
      gCfg.alarmEnable = !gCfg.alarmEnable;
      break;
    default:
      break;
  }
}
bool handleSettingsValueEditMode() {
  bool changed = false;
  if (consumeBtn(Btn::Up)) { applySettingDelta(+1); changed = true; }
  if (consumeBtn(Btn::Down)) { applySettingDelta(-1); changed = true; }
  if (consumeBtn(Btn::Ok) || consumeBtn(Btn::Back)) {
    gUi.settingEdit = false;
    changed = true;
  }
  return changed;
}
bool handleSettingsListMode() {
  bool changed = false;
  if (consumeBtn(Btn::Up)) {
    gUi.settingsCursor = (gUi.settingsCursor + static_cast<uint8_t>(SettingField::Count) - 1) % static_cast<uint8_t>(SettingField::Count);
    changed = true;
  }
  if (consumeBtn(Btn::Down)) {
    gUi.settingsCursor = (gUi.settingsCursor + 1) % static_cast<uint8_t>(SettingField::Count);
    changed = true;
  }
  if (consumeBtn(Btn::Ok)) {
    SettingField f = static_cast<SettingField>(gUi.settingsCursor);
    if (f == SettingField::SaveApply) {
      saveSettings();
      setBacklightPercent(gCfg.brightness);
      restartSoftAp();
    } else if (f == SettingField::Exit) {
      gUi.activePage = Page::LiveData;
      gUi.menuCursor = static_cast<uint8_t>(Page::LiveData);
    } else if (f == SettingField::WifiSsid || f == SettingField::WifiPass) {
      gUi.settingEdit = true;
      beginTextEdit(f);
    } else {
      gUi.settingEdit = true;
    }
    changed = true;
  }
  if (consumeBtn(Btn::Back)) { gUi.activePage = Page::LiveData; gUi.menuCursor = static_cast<uint8_t>(Page::LiveData); changed = true; }
  return changed;
}
bool handleSettingsButtons() {
  using ModeHandlerFn = bool (*)();
  static const ModeHandlerFn MODE_HANDLERS[] = {handleSettingsConfirmMode, handleSettingsTextEditMode, handleSettingsValueEditMode, handleSettingsListMode};
  return MODE_HANDLERS[static_cast<uint8_t>(currentSettingsInputMode())]();
}
bool handleMenuButtons() {
  bool changed = false;
  if (consumeBtn(Btn::Up)) { gUi.menuCursor = (gUi.menuCursor + static_cast<uint8_t>(Page::Count) - 1) % static_cast<uint8_t>(Page::Count); changed = true; }
  if (consumeBtn(Btn::Down)) { gUi.menuCursor = (gUi.menuCursor + 1) % static_cast<uint8_t>(Page::Count); changed = true; }
  if (consumeBtn(Btn::Ok)) { gUi.activePage = static_cast<Page>(gUi.menuCursor); changed = true; }
  if (consumeBtn(Btn::Back)) { gUi.activePage = Page::LiveData; gUi.menuCursor = static_cast<uint8_t>(Page::LiveData); changed = true; }
  return changed;
}
static void setupOsfx() {
  osfx_easy_init(&g_osfxCtx);
  osfx_easy_set_aid(&g_osfxCtx, 1U);
  osfx_easy_set_tid(&g_osfxCtx, 1U);
  (void)osfx_easy_set_node(&g_osfxCtx, "DHT11_NODE", "ONLINE");
  g_osfxUdp.begin(OSFX_UDP_PORT);
  g_pingUdp.begin(OSFX_UDP_PORT + 1);  // plain-text heartbeat on 9001
  Serial.println("[OSFX] OSynaptic-FX ready, broadcasting on port 9000");
}
static void broadcastOsfxPacket() {
  // --- plain-text heartbeat on port 9001 (独立于 OSFX，用于诊断 UDP 是否可达) ---
  {
    char ping[64];
    snprintf(ping, sizeof(ping), "PING ms=%lu t=%.1f h=%.1f",
             (unsigned long)millis(), (double)gRt.sensor.temp, (double)gRt.sensor.humi);
    if (g_pingUdp.beginPacket(IPAddress(192,168,4,255), OSFX_UDP_PORT + 1)) {
      g_pingUdp.write(reinterpret_cast<const uint8_t*>(ping), strlen(ping));
      g_pingUdp.endPacket();
    }
    Serial.printf("[PING] %s\n", ping);
  }

  if (OSFX_RESYNC_N > 0UL && g_osfxEmitCount > 0UL &&
      (g_osfxEmitCount % OSFX_RESYNC_N) == 0UL) {
    osfx_fusion_state_reset(&g_osfxCtx.tx_state);
  }
  const char *sensorState = gRt.sensor.online ? "OK" : "FAIL";
  uint32_t now_ms   = millis();
  uint32_t heapFree = ESP.getFreeHeap();
  uint8_t  cpuMhz   = static_cast<uint8_t>(ESP.getCpuFreqMHz());

  osfx_core_sensor_input sensors[8];
  // 0: 温度
  sensors[0].sensor_id             = "DHT11_TEMP";
  sensors[0].sensor_state          = sensorState;
  sensors[0].value                 = gRt.sensor.online ? static_cast<double>(gRt.sensor.temp) : -999.0;
  sensors[0].unit                  = "Cel";
  sensors[0].geohash_id            = "";
  sensors[0].supplementary_message = "";
  sensors[0].resource_url          = "";
  // 1: 湿度
  sensors[1].sensor_id             = "DHT11_HUMI";
  sensors[1].sensor_state          = sensorState;
  sensors[1].value                 = gRt.sensor.online ? static_cast<double>(gRt.sensor.humi) : -999.0;
  sensors[1].unit                  = "%";
  sensors[1].geohash_id            = "";
  sensors[1].supplementary_message = "";
  sensors[1].resource_url          = "";
  // 2: CPU 负载
  sensors[2].sensor_id             = "SYS_CPU_LOAD";
  sensors[2].sensor_state          = "OK";
  sensors[2].value                 = static_cast<double>(gRt.metrics.cpuLoadPct);
  sensors[2].unit                  = "%";
  sensors[2].geohash_id            = "";
  sensors[2].supplementary_message = "";
  sensors[2].resource_url          = "";
  // 3: CPU 主频
  sensors[3].sensor_id             = "SYS_CPU_MHZ";
  sensors[3].sensor_state          = "OK";
  sensors[3].value                 = static_cast<double>(cpuMhz);
  sensors[3].unit                  = "MHz";
  sensors[3].geohash_id            = "";
  sensors[3].supplementary_message = "";
  sensors[3].resource_url          = "";
  // 4: 空闲堆
  sensors[4].sensor_id             = "SYS_HEAP_FREE";
  sensors[4].sensor_state          = "OK";
  sensors[4].value                 = static_cast<double>(heapFree);
  sensors[4].unit                  = "B";
  sensors[4].geohash_id            = "";
  sensors[4].supplementary_message = "";
  sensors[4].resource_url          = "";
  // 5: 堆使用率
  sensors[5].sensor_id             = "SYS_HEAP_USED";
  sensors[5].sensor_state          = "OK";
  sensors[5].value                 = static_cast<double>(gRt.metrics.heapUsedPct);
  sensors[5].unit                  = "%";
  sensors[5].geohash_id            = "";
  sensors[5].supplementary_message = "";
  sensors[5].resource_url          = "";
  // 6: 运行时间 (s)
  sensors[6].sensor_id             = "SYS_UPTIME";
  sensors[6].sensor_state          = "OK";
  sensors[6].value                 = static_cast<double>(now_ms / 1000UL);
  sensors[6].unit                  = "s";
  sensors[6].geohash_id            = "";
  sensors[6].supplementary_message = "";
  sensors[6].resource_url          = "";
  // 7: 告警状态
  sensors[7].sensor_id             = "SYS_ALARM";
  sensors[7].sensor_state          = gRt.sensor.alarmActive ? "ALARM" : "OK";
  sensors[7].value                 = gRt.sensor.alarmActive ? 1.0 : 0.0;
  sensors[7].unit                  = "bool";
  sensors[7].geohash_id            = "";
  sensors[7].supplementary_message = "";
  sensors[7].resource_url          = "";

  int      pktLen = 0;
  uint8_t  cmd    = 0;
  uint64_t ts     = 1710000000ULL + static_cast<uint64_t>(now_ms / 1000UL);
  int encRet = osfx_easy_encode_multi_sensor_auto(
      &g_osfxCtx, ts, sensors, 8U,
      g_osfxBuf, sizeof(g_osfxBuf), &pktLen, &cmd);
  Serial.printf("[OSFX] encode ret=%d pktLen=%d\n", encRet, pktLen);
  if (encRet != 0 && pktLen > 0) {
    // Broadcast on the default SoftAP subnet (192.168.4.255)
    bool bp = g_osfxUdp.beginPacket(IPAddress(192, 168, 4, 255), OSFX_UDP_PORT);
    Serial.printf("[OSFX] beginPacket=%d\n", (int)bp);
    if (bp) {
      g_osfxUdp.write(g_osfxBuf, static_cast<size_t>(pktLen));
      g_osfxUdp.endPacket();
      Serial.printf("[OSFX] %s len=%d sent OK\n", osfx_easy_cmd_name(cmd), pktLen);
    }
  }
  ++g_osfxEmitCount;
}
void updateAlarmState(uint32_t now) {
  bool outOfRange = gRt.sensor.online && (gRt.sensor.temp < gCfg.tempLow || gRt.sensor.temp > gCfg.tempHigh || gRt.sensor.humi < gCfg.humiLow || gRt.sensor.humi > gCfg.humiHigh);
  gRt.sensor.alarmActive = gCfg.alarmEnable && gRt.sensor.online && outOfRange;
  if (!gRt.sensor.alarmActive) { setAlarmOutput(false); return; }
  if (now - gRt.metrics.alarmBlinkMs >= 250) {
    gRt.metrics.alarmBlinkMs = now; gRt.metrics.alarmBlinkState = !gRt.metrics.alarmBlinkState; setAlarmOutput(gRt.metrics.alarmBlinkState);
  }
}
void setup() {
  Serial.begin(115200); dht.begin(); loadSettings(); setupBacklightPwm(); setBacklightPercent(gCfg.brightness);
  pinMode(HW::Sensor::AlarmPin, OUTPUT); setAlarmOutput(false); initButtons(); initTfts();
  for (uint8_t i = 0; i < HISTORY_LEN; ++i) {
    gTempHistory[i] = NAN; gHumiHistory[i] = NAN;
  }
  drawMenuOnTft1(); drawCurrentPageOnTft2(true); setupWifiApi(); setupOsfx();
}
void loop() {
  uint32_t now = millis(), loopStartUs = micros();
  apiServer.handleClient(); scanButtons(now);
  bool changed = (gUi.activePage == Page::Settings) ? handleSettingsButtons() : handleMenuButtons();
  if (changed) {
    if (gUi.exitConfirmMode == ExitConfirmMode::Active && gUi.lastExitConfirmMode == ExitConfirmMode::Active) drawExitConfirmDialog();
    else { drawMenuOnTft1(); drawCurrentPageOnTft2(true); }
  }
  if (gUi.exitConfirmMode != gUi.lastExitConfirmMode) gUi.lastExitConfirmMode = gUi.exitConfirmMode;
  if (now - gRt.metrics.lastDhtReadMs >= gCfg.sampleMs) {
    gRt.metrics.lastDhtReadMs = now;
    float h = dht.readHumidity(), t = dht.readTemperature();
    if (!isnan(h) && !isnan(t)) {
      gRt.sensor.temp = t; gRt.sensor.humi = h; gRt.sensor.online = true; gRt.sensor.lastDhtOkMs = now;
      gTempHistory[gHistoryIndex] = t; gHumiHistory[gHistoryIndex] = h;
      gHistoryIndex = (gHistoryIndex + 1) % HISTORY_LEN;
      if (gHistoryIndex == 0) gHistoryFilled = true;
    } else gRt.sensor.online = false;
    updateAlarmState(now);
    broadcastOsfxPacket();
    if (gUi.activePage == Page::LiveData || gUi.activePage == Page::SensorState || gUi.activePage == Page::Curve) drawCurrentPageOnTft2(gUi.lastPageDrawn != gUi.activePage);
  }
  updateAlarmState(now);
  uint32_t workUs = micros() - loopStartUs;
  uint32_t totalUs = workUs + 10000; // plus delay(10)
  uint8_t instantCpu = static_cast<uint8_t>((workUs * 100U) / (totalUs == 0 ? 1 : totalUs));
  gRt.metrics.cpuLoadPct = static_cast<uint8_t>((gRt.metrics.cpuLoadPct * 7 + instantCpu) / 8);
  uint32_t heapFree = ESP.getFreeHeap(), heapTotal = ESP.getHeapSize();
  if (heapTotal > 0) {
    uint32_t used = heapTotal - heapFree; gRt.metrics.heapUsedPct = static_cast<uint8_t>((used * 100U) / heapTotal);
  }
  delay(10);
}
