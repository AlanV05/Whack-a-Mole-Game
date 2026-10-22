/*
  RCWL-1601 ultrasonic sensor on ESP32 -> sends distance over WiFi (UDP)
  TIME-DIVISION version: the board only fires when the PC tells it to.
  =====================================================================
  Upload this SAME sketch to all 3 boards. On each board, change SENSOR_ID
  to "LEFT", "MID", "MID2", or "RIGHT".

  HOW IT WORKS
    The PC (sensor_to_processing_zoned.py) sends "FIRE" to one board at a
    time, in turn. A board fires its sensor ONLY when it gets "FIRE", then
    replies "LEFT 123.45". So no two sensors ever ping at the same moment and
    they can't hear each other's echoes (no crosstalk).

    While the PC isn't polling it (e.g. Python not running yet), the board
    sends "HELLO LEFT" twice a second so the PC can learn its IP address.

  Pairs with: sensor_to_processing_zoned.py
    board -> PC  on UDP 9000 (readings + HELLO)
    PC -> board  on UDP 9002 (FIRE)

  WIRING (same on every board):
    TRIG -> GPIO25  (direct, 3.3V is enough to trigger)
    ECHO -> GPIO26  THROUGH A VOLTAGE DIVIDER (ECHO is 5V, ESP32 pins are 3.3V!)
            ECHO --[1k]--+--[2k]-- GND
                         |
                       GPIO26
    VCC  -> 5V
    GND  -> GND
*/

#include <WiFi.h>
#include <WiFiUdp.h>

// ---------------- SET THESE ----------------
const char* WIFI_SSID = "AlanV";
const char* WIFI_PASS = "****";
const char* PC_IP     = "172.20.10.14";   // your PC's IPv4 address
const int   PC_PORT   = 9000;             // must match UDP_LISTEN_PORT in the Python
const int   POLL_PORT = 9002;             // must match POLL_PORT in the Python
const char* SENSOR_ID = "MID2";           // "LEFT" / "MID" / "MID2"/ "RIGHT"  -- change per board
// --------------------------------------------

#define TRIG_PIN 25
#define ECHO_PIN 26
#define ECHO_TIMEOUT_US 15000   // ~2.5m max range; keeps each turn short

WiFiUDP udp;
unsigned long lastFireMs  = 0;
unsigned long lastHelloMs = 0;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // WiFi power-save adds big random delays to FIRE -> keep it off
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.print("\nConnected. This board's IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("Sensor: ");
  Serial.println(SENSOR_ID);
  udp.begin(POLL_PORT);
}

void sendToPC(const char* msg) {
  udp.beginPacket(PC_IP, PC_PORT);
  udp.write((const uint8_t*)msg, strlen(msg));
  udp.endPacket();
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  return (duration == 0) ? -1.0f : duration * 0.0343f / 2.0f;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  int size = udp.parsePacket();
  if (size > 0) {
    char buf[16];
    int n = udp.read(buf, sizeof(buf) - 1);
    buf[n > 0 ? n : 0] = '\0';

    // Throw away any extra queued FIREs - a stale one would make us ping
    // outside our turn. The PC just retries on its next round.
    while (udp.parsePacket() > 0) { udp.flush(); }

    if (strncmp(buf, "FIRE", 4) == 0) {
      float d = readDistanceCm();
      char msg[32];
      snprintf(msg, sizeof(msg), "%s %.2f", SENSOR_ID, d);
      sendToPC(msg);
      lastFireMs = millis();
      Serial.println(msg);   // USB debugging
    }
  }

  // Not being polled? Announce ourselves so the PC learns our IP.
  unsigned long now = millis();
  if (now - lastFireMs > 1000 && now - lastHelloMs > 500) {
    char hello[24];
    snprintf(hello, sizeof(hello), "HELLO %s", SENSOR_ID);
    sendToPC(hello);
    lastHelloMs = now;
  }
}
