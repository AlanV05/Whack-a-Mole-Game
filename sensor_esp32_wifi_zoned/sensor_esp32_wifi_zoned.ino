/*
  RCWL-1601 ultrasonic sensor on ESP32 -> sends distance over WiFi (UDP)
  TIME-DIVISION + AUTO-DISCOVERY version (no PC IP address needed)
  =====================================================================
  Upload this SAME sketch to all 4 boards. On each board, change SENSOR_ID
  to "LEFT", "MID", "MID2" or "RIGHT". That is the only line that differs.

  WORKS ON ANY LAPTOP (no PC_IP to set)
    Until the game is running, the board shouts "HELLO MID2" to the whole
    network (UDP broadcast) twice a second. The game hears it and starts
    sending "FIRE". The first FIRE tells the board where the PC is, and every
    reading goes straight back to that PC. Plug in a different laptop, or the
    hotspot gives the Mac a new address -> nothing to change or reflash.
    If the game stops polling for 1 s the board goes back to broadcasting.

  TIME-DIVISION FIRING
    A board fires its sensor ONLY when it gets "FIRE", then replies
    "MID2 123.45". The PC fires one board at a time, so no two sensors ever
    ping together and they can't hear each other's echoes (no crosstalk).

  Pairs with: sensor_to_processing_zoned.py (unchanged)
    board -> PC  on UDP 9000 (readings + HELLO)
    PC -> board  on UDP 9002 (FIRE)

  WIRING (same on every board, no solder - Dupont jumpers):
    TRIG -> GPIO25
    ECHO -> GPIO26
    VCC  -> 3V3   (sensor on 3.3 V, so ECHO is already 3.3 V logic - no divider)
    GND  -> GND
    Battery: 4 x AA NiMH -> VIN (5V pin) and GND
*/

#include <WiFi.h>
#include <WiFiUdp.h>

// ---------------- SET THESE ----------------
const char* WIFI_SSID = "AlanV";
const char* WIFI_PASS = "jesalaalv76";   // never commit the real password
const char* SENSOR_ID = "RIGHT";                 // "LEFT" / "MID" / "MID2" / "RIGHT" -- change per board
const int   PC_PORT   = 9000;                   // must match UDP_LISTEN_PORT in the Python
const int   POLL_PORT = 9002;                   // must match POLL_PORT in the Python
// --------------------------------------------

#define TRIG_PIN 25
#define ECHO_PIN 26
#define ECHO_TIMEOUT_US 15000   // ~2.5 m max range; keeps each turn short
#define POLL_LOST_MS    1000    // no FIRE for this long -> go back to broadcasting HELLO
#define HELLO_EVERY_MS  500

WiFiUDP udp;
IPAddress pcIP;                 // learned from the first FIRE
bool havePC = false;
unsigned long lastFireMs  = 0;
unsigned long lastHelloMs = 0;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);         // WiFi power-save adds big random delays to FIRE -> keep it off
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  // WiFi.setTxPower(WIFI_POWER_11dBm);   // uncomment if a board browns out on batteries
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.print("\nConnected. This board's IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("Sensor: ");
  Serial.println(SENSOR_ID);
  Serial.print("Announcing to: ");
  Serial.println(WiFi.broadcastIP());
  udp.begin(POLL_PORT);
}

void sendTo(IPAddress ip, const char* msg) {
  udp.beginPacket(ip, PC_PORT);
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
    havePC = false;
    connectWiFi();
  }

  int size = udp.parsePacket();
  if (size > 0) {
    IPAddress sender = udp.remoteIP();      // whoever sent FIRE is the PC
    char buf[16];
    int n = udp.read(buf, sizeof(buf) - 1);
    buf[n > 0 ? n : 0] = '\0';

    // Throw away any extra queued FIREs - a stale one would make us ping
    // outside our turn. The PC just retries on its next round.
    while (udp.parsePacket() > 0) { udp.flush(); }

    if (strncmp(buf, "FIRE", 4) == 0) {
      if (!havePC || !(sender == pcIP)) {
        pcIP = sender;
        havePC = true;
        Serial.print("PC found at ");
        Serial.println(pcIP);
      }
      float d = readDistanceCm();
      char msg[32];
      snprintf(msg, sizeof(msg), "%s %.2f", SENSOR_ID, d);
      sendTo(pcIP, msg);
      lastFireMs = millis();
      Serial.println(msg);   // USB debugging
    }
  }

  // Not being polled? Shout HELLO to the whole network so any PC can find us.
  unsigned long now = millis();
  if (now - lastFireMs > POLL_LOST_MS && now - lastHelloMs > HELLO_EVERY_MS) {
    char hello[24];
    snprintf(hello, sizeof(hello), "HELLO %s", SENSOR_ID);
    sendTo(WiFi.broadcastIP(), hello);
    lastHelloMs = now;
  }
}
