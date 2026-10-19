/*
  ENGG3000 Whack-a-Mole - ESP32 sensor box firmware

  ONE sketch for all three boxes.  Before uploading to each board, change
  SENSOR_ID (1 = left box, 2 = middle box, 3 = right box).

  What it does:
    - Connects to Wi-Fi
    - Measures the RCWL-1601 ultrasonic distance ~15 times a second
    - Sends "<SENSOR_ID>,<distance_mm>" to the PC over UDP (port 5005)
      e.g. "2,1050".  Sends "<SENSOR_ID>,-1" when there is no echo.
    - On the buzzer box only: listens on UDP port 5006 for "BUZZ 1" / "BUZZ 0"
      from the PC.  Safety failsafe: if it stops hearing "BUZZ 1" for 1 s
      it turns the buzzer off by itself.
    - Reconnects automatically if Wi-Fi drops.

  Matches sensor_link.py on the PC side.
*/

#include <WiFi.h>
#include <WiFiUdp.h>

// ------------------------------------------------------------------
// CHANGE PER BOARD
// ------------------------------------------------------------------
const int SENSOR_ID = 1;                 // 1, 2 or 3

// ------------------------------------------------------------------
// CHANGE FOR YOUR NETWORK (same on all three boards)
// ------------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
IPAddress   PC_IP(192, 168, 1, 100);     // Windows: run `ipconfig`, use the Wi-Fi IPv4 address
const uint16_t PC_PORT       = 5005;     // sensor_link.LISTEN_PORT
const uint16_t BUZZER_PORT   = 5006;     // sensor_link.BUZZER_PORT
const int   BUZZER_BOX_ID    = 2;        // sensor_link.BUZZER_SENSOR_ID

// ------------------------------------------------------------------
// Pins - taken from the team's tested buzzer sketch (TRIG 25, ECHO 26,
// BUZZER 19).  CHECK these against the final schematic before soldering.
// ------------------------------------------------------------------
#define TRIG_PIN   25
#define ECHO_PIN   26
#define BUZZER_PIN 19

const unsigned long MEASURE_PERIOD_MS  = 66;     // ~15 readings per second
const unsigned long ECHO_TIMEOUT_US    = 25000;  // ~4.3 m max; stops pulseIn blocking for 1 s
const unsigned long BUZZER_FAILSAFE_MS = 1000;
const int           BUZZER_FREQ_HZ     = 4000;

WiFiUDP udp;
unsigned long lastMeasure   = 0;
unsigned long lastBuzzOnCmd = 0;
bool buzzerOn = false;
const bool HAS_BUZZER = (SENSOR_ID == BUZZER_BOX_ID);

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("Box %d connecting to %s", SENSOR_ID, WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                  // lower latency; uses a bit more battery
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(250);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nConnected, my IP = %s\n", WiFi.localIP().toString().c_str());
    if (HAS_BUZZER) udp.begin(BUZZER_PORT);
  } else {
    Serial.println("\nWi-Fi failed, will retry");
  }
}

long readDistanceMm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) return -1;          // no echo
  return (long)(duration * 0.343 / 2.0); // speed of sound 343 m/s -> mm
}

void setBuzzer(bool on) {
  if (on == buzzerOn) return;
  buzzerOn = on;
  if (on) tone(BUZZER_PIN, BUZZER_FREQ_HZ);
  else    noTone(BUZZER_PIN);
}

void checkBuzzerCommands() {
  int size = udp.parsePacket();
  while (size > 0) {
    char buf[16] = {0};
    udp.read(buf, sizeof(buf) - 1);
    if (strncmp(buf, "BUZZ 1", 6) == 0) {
      lastBuzzOnCmd = millis();
      setBuzzer(true);
    } else if (strncmp(buf, "BUZZ 0", 6) == 0) {
      setBuzzer(false);
    }
    size = udp.parsePacket();
  }
  // Failsafe: PC crashed or Wi-Fi dropped -> don't beep forever.
  if (buzzerOn && millis() - lastBuzzOnCmd > BUZZER_FAILSAFE_MS) setBuzzer(false);
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  if (HAS_BUZZER) {
    pinMode(BUZZER_PIN, OUTPUT);
    noTone(BUZZER_PIN);
  }
  // Stagger start-up so the three boxes don't all ping at the same moment
  // (reduces ultrasonic cross-talk between neighbouring sensors).
  delay(SENSOR_ID * 22);
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    setBuzzer(false);
    connectWiFi();
    return;
  }

  if (HAS_BUZZER) checkBuzzerCommands();

  if (millis() - lastMeasure >= MEASURE_PERIOD_MS) {
    lastMeasure = millis();
    long mm = readDistanceMm();

    char msg[24];
    snprintf(msg, sizeof(msg), "%d,%ld", SENSOR_ID, mm);
    udp.beginPacket(PC_IP, PC_PORT);
    udp.print(msg);
    udp.endPacket();

    Serial.println(msg);                 // handy for checking on the Serial Monitor
  }
}
