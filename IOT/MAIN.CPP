#include <Arduino.h>
#include <Wire.h>
#include <VL53L1X.h>

// =====================================================
// ESP32-S3 + VL53L1X + 2 VIBRATION MOTORS
// + PASSIVE BUZZER + 1 PUSH BUTTON
//
// VL53L1X: SDA GPIO 8, SCL GPIO 9
// Motor 1: GPIO 4
// Motor 2: GPIO 6
// Passive buzzer: GPIO 5
// Push button: GPIO 7 <-> GND
//
// Nhan nut 1 lan: BAT he thong
// Nhan nut lan nua: TAT he thong
//
// >= 200 cm : tat motor, tat loa
// 150-<200  : chi keu, bip cham
// 100-<150  : chi keu, bip nhanh dan
// 50-<100   : keu nhanh + rung tang dan
// <= 50     : keu lien tuc + rung toi da
// =====================================================

#define SDA_PIN       8
#define SCL_PIN       9
#define MOTOR1_PIN    4
#define MOTOR2_PIN    6
#define BUZZER_PIN    5
#define BUTTON_PIN    7

const float FAR_CM        = 200.0f;
const float MID_CM        = 150.0f;
const float NEAR_CM       = 50.0f;
const float VIBE_START_CM = 100.0f;  // tu khoang nay tro lai moi rung

const uint8_t MOTOR_MIN_POWER = 140; // luc rung thap nhat (de motor chac chan quay)

const uint32_t MOTOR_FREQ = 20000;
const uint8_t  PWM_BITS   = 8;

// Core 2.x: kenh 0/1 chung timer, 2/3 chung timer, 4/5 chung timer
const uint8_t MOTOR1_CHANNEL = 0;
const uint8_t MOTOR2_CHANNEL = 2;
const uint8_t BUZZER_CHANNEL = 4;

const uint32_t SENSOR_PERIOD_MS = 60;
const uint32_t SERIAL_PERIOD_MS = 250;
const uint32_t DEBOUNCE_MS      = 40;
const uint32_t SENSOR_TIMEOUT_MS = 500;
const uint8_t  MAX_BAD_READS    = 4;  // loi lien tiep bao nhieu lan moi coi la mat vat

VL53L1X sensor;

bool sensorReady = false;
bool motor1Ready = false;
bool motor2Ready = false;
bool buzzerReady = false;

// He thong mac dinh TAT, nhan nut de BAT
bool systemEnabled = false;

float distanceCm = -1.0f;
uint8_t badReads = 0;

uint32_t lastSensorMs = 0;
uint32_t lastDataMs = 0;
uint32_t lastSerialMs = 0;
uint32_t lastBeepMs = 0;
uint32_t beepStartedMs = 0;
uint32_t lastButtonChangeMs = 0;

bool beepOn = false;
bool buttonLastReading = HIGH;
bool buttonStableState = HIGH;

int currentZone = -99;

// -----------------------------------------------------
// PWM compatibility: Arduino ESP32 Core 2.x / 3.x
// -----------------------------------------------------
bool setupMotorPWM(uint8_t pin, uint8_t channel) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && \
    ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)channel;
  return ledcAttach(pin, MOTOR_FREQ, PWM_BITS);
#else
  if (ledcSetup(channel, MOTOR_FREQ, PWM_BITS) <= 0) {
    return false;
  }
  ledcAttachPin(pin, channel);
  return true;
#endif
}

void writeMotorPWM(uint8_t pin, uint8_t channel, uint8_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && \
    ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)channel;
  ledcWrite(pin, duty);
#else
  (void)pin;
  ledcWrite(channel, duty);
#endif
}

bool setupBuzzerPWM() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && \
    ESP_ARDUINO_VERSION_MAJOR >= 3
  return ledcAttach(BUZZER_PIN, 2000, 8);
#else
  if (ledcSetup(BUZZER_CHANNEL, 2000, 8) <= 0) {
    return false;
  }
  ledcAttachPin(BUZZER_PIN, BUZZER_CHANNEL);
  return true;
#endif
}

void buzzerTone(uint32_t frequency) {
  if (!buzzerReady) return;

#if defined(ESP_ARDUINO_VERSION_MAJOR) && \
    ESP_ARDUINO_VERSION_MAJOR >= 3
  if (frequency == 0) {
    ledcWrite(BUZZER_PIN, 0);
  } else {
    ledcWriteTone(BUZZER_PIN, frequency);
  }
#else
  if (frequency == 0) {
    ledcWrite(BUZZER_CHANNEL, 0);
  } else {
    ledcWriteTone(BUZZER_CHANNEL, frequency);
  }
#endif
}

void buzzerOff() {
  buzzerTone(0);
}

// -----------------------------------------------------
// Control both vibration motors
// -----------------------------------------------------
void setMotors(uint8_t power) {
  if (motor1Ready) {
    writeMotorPWM(MOTOR1_PIN, MOTOR1_CHANNEL, power);
  }

  if (motor2Ready) {
    writeMotorPWM(MOTOR2_PIN, MOTOR2_CHANNEL, power);
  }
}

void stopAlarm() {
  setMotors(0);
  buzzerOff();
  beepOn = false;
}

// -----------------------------------------------------
// Button: GPIO 7 to GND
// INPUT_PULLUP: pressed = LOW
// Debounce, non-blocking
// -----------------------------------------------------
void handleButton() {
  uint32_t now = millis();
  bool reading = digitalRead(BUTTON_PIN);

  if (reading != buttonLastReading) {
    lastButtonChangeMs = now;
    buttonLastReading = reading;
  }

  if (now - lastButtonChangeMs >= DEBOUNCE_MS) {
    if (reading != buttonStableState) {
      buttonStableState = reading;

      // Chi xu ly luc vua nhan nut
      if (buttonStableState == LOW) {
        systemEnabled = !systemEnabled;

        if (systemEnabled) {
          currentZone = -99;
          Serial.println("SYSTEM ON");
        } else {
          stopAlarm();
          currentZone = -99;
          Serial.println("SYSTEM OFF");
        }
      }
    }
  }
}

// -----------------------------------------------------
// Alarm zone
// 0 = far, 1 = mild, 2 = increasing, 3 = very near
// -----------------------------------------------------
int getZone(float cm) {
  if (cm < 0) return -1;
  if (cm >= FAR_CM) return 0;
  if (cm <= NEAR_CM) return 3;
  if (cm >= MID_CM) return 1;
  return 2;
}

// -----------------------------------------------------
// Motor power: chi rung khi cm <= VIBE_START_CM
// -----------------------------------------------------
uint8_t getMotorPower(float cm) {
  if (cm < 0 || cm > VIBE_START_CM) return 0;
  if (cm <= NEAR_CM) return 255;

  float r = (VIBE_START_CM - cm) / (VIBE_START_CM - NEAR_CM);
  r = constrain(r, 0.0f, 1.0f);
  return (uint8_t)(MOTOR_MIN_POWER + r * (255 - MOTOR_MIN_POWER));
}

// -----------------------------------------------------
// Apply distance-dependent buzzer + vibration
// Goi moi vong loop() de nhip bip chinh xac
// -----------------------------------------------------
void updateAlarm(float cm) {
  uint32_t now = millis();
  int zone = getZone(cm);

  if (!systemEnabled || zone <= 0) {
    stopAlarm();
    currentZone = zone;
    return;
  }

  uint32_t beepInterval = 0;
  uint32_t beepDuration = 0;
  uint32_t beepFrequency = 2000;

  if (zone == 1) {
    // 150 den duoi 200 cm
    beepInterval = 900;
    beepDuration = 100;
    beepFrequency = 1800;
  } else if (zone == 2) {
    // 50 den duoi 150 cm
    float ratio = (MID_CM - cm) / (MID_CM - NEAR_CM);
    ratio = constrain(ratio, 0.0f, 1.0f);

    beepInterval = (uint32_t)(600.0f - ratio * 450.0f);
    beepDuration = 80;
    beepFrequency = (uint32_t)(1800.0f + ratio * 700.0f);
  } else {
    // 50 cm tro lai: keu lien tuc + rung max
    setMotors(255);
    if (zone != currentZone) buzzerTone(2500);  // chi goi 1 lan
    beepOn = true;
    currentZone = zone;
    return;
  }

  setMotors(getMotorPower(cm));

  if (zone != currentZone) {
    buzzerOff();
    beepOn = false;
    lastBeepMs = now - beepInterval;
    currentZone = zone;
  }

  // Non-blocking beep
  if (beepOn) {
    if (now - beepStartedMs >= beepDuration) {
      buzzerOff();
      beepOn = false;
    }
  } else {
    if (now - lastBeepMs >= beepInterval) {
      buzzerTone(beepFrequency);
      beepOn = true;
      beepStartedMs = now;
      lastBeepMs = now;
    }
  }
}

// -----------------------------------------------------
// Read sensor (non-blocking)
// -----------------------------------------------------
void readDistance() {
  uint32_t now = millis();

  if (now - lastSensorMs < SENSOR_PERIOD_MS) return;

  if (sensor.dataReady()) {
    lastSensorMs = now;
    lastDataMs = now;

    uint16_t distanceMm = sensor.read(false);

    if (sensor.ranging_data.range_status != 0) {
      if (badReads < 255) badReads++;
    } else {
      badReads = 0;
      distanceCm = distanceMm / 10.0f;
    }
  } else if (now - lastDataMs > SENSOR_TIMEOUT_MS) {
    // Qua lau khong co du lieu moi
    lastDataMs = now;
    if (badReads < 255) badReads++;
  }

  // Loi nhieu lan lien tiep -> coi nhu khong co vat
  if (badReads >= MAX_BAD_READS) {
    distanceCm = -1.0f;
  }
}

// -----------------------------------------------------
// Setup
// -----------------------------------------------------
void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 2000) {
    delay(10);
  }

  Serial.println();
  Serial.println("=== ESP32-S3 DISTANCE ALERT ===");

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  motor1Ready = setupMotorPWM(MOTOR1_PIN, MOTOR1_CHANNEL);
  motor2Ready = setupMotorPWM(MOTOR2_PIN, MOTOR2_CHANNEL);
  buzzerReady = setupBuzzerPWM();

  stopAlarm();

  Serial.printf("Motor 1: %s\n", motor1Ready ? "OK" : "FAIL");
  Serial.printf("Motor 2: %s\n", motor2Ready ? "OK" : "FAIL");
  Serial.printf("Buzzer : %s\n", buzzerReady ? "OK" : "FAIL");
  Serial.println("Button: GPIO 7");
  Serial.println("System initially OFF. Press button to start.");

  sensor.setTimeout(500);

  if (!sensor.init()) {
    Serial.println("ERROR: VL53L1X not detected!");
    Serial.println("Check VIN, GND, SDA GPIO8, SCL GPIO9.");
    sensorReady = false;
    stopAlarm();
    return;
  }

  sensor.setDistanceMode(VL53L1X::Long);
  sensor.setMeasurementTimingBudget(50000);
  sensor.startContinuous(60);

  lastDataMs = millis();
  sensorReady = true;
  Serial.println("VL53L1X: OK");
  Serial.println("System ready.");
}

// -----------------------------------------------------
// Main loop
// -----------------------------------------------------
void loop() {
  handleButton();

  if (!sensorReady) {
    stopAlarm();
    delay(10);
    return;
  }

  readDistance();

  if (systemEnabled && distanceCm >= 0) {
    updateAlarm(distanceCm);
  } else {
    stopAlarm();
    currentZone = (distanceCm < 0) ? -1 : currentZone;
  }

  uint32_t now = millis();

  if (now - lastSerialMs >= SERIAL_PERIOD_MS) {
    lastSerialMs = now;

    Serial.printf("System: %s | ", systemEnabled ? "ON" : "OFF");

    if (distanceCm < 0) {
      Serial.println("Distance invalid / no target");
    } else {
      int zone = getZone(distanceCm);
      uint8_t power = systemEnabled ? getMotorPower(distanceCm) : 0;

      Serial.printf(
          "Distance: %.1f cm | Zone: %d | Motor PWM: %u\n",
          distanceCm, zone, power
      );
    }
  }
}

===================================================================
1. KHỐI NGUỒN CẤP (PIN -> BOOST -> CÔNG TẮC -> ESP32-S3)
===================================================================

[PIN 3.7V]
   (+) Cực Dương ----------------------> [IN+] DC-DC BOOST
   (-) Cực Âm -------------------------> [IN-] DC-DC BOOST

[MẠCH DC-DC BOOST 5V]
   (OUT+) --------------------------------> [Chân 1] CÔNG TẮC ON/OFF
   (OUT-) --------------------------------> [GND] ESP32-S3 (GND CHUNG)

[CÔNG TẮC ON/OFF (Gạt 2 hoặc 3 chân)]
   (Chân 2) --------------------------------> [5V / VIN] ESP32-S3


===================================================================
2. KHỐI CẢM BIẾN VL53L1X
===================================================================

[CẢM BIẾN VL53L1X]
   (VIN)   ------------------------------> [3V3]    ESP32-S3
   (GND)   ------------------------------> [GND]    ESP32-S3
   (SDA)   ------------------------------> [GPIO 8] ESP32-S3
   (SCL)   ------------------------------> [GPIO 9] ESP32-S3


===================================================================
3. KHỐI THIẾT BỊ PHẢN HỒI (CÒI & 2 ĐỘNG CƠ RUNG)
===================================================================

[MODULE CÒI / LOA (BUZZER MODULE)]
   (VCC)  --------------------------------> [5V / VIN] ESP32-S3
   (GND)  --------------------------------> [GND]      ESP32-S3
   (SIG)  --------------------------------> [GPIO 5]   ESP32-S3

[MODULE ĐỘNG CƠ RUNG 1]
   (VCC)  --------------------------------> [5V / VIN] ESP32-S3
   (GND)  --------------------------------> [GND]      ESP32-S3
   (SIG)  --------------------------------> [GPIO 4]   ESP32-S3

[MODULE ĐỘNG CƠ RUNG 2]
   (VCC)  --------------------------------> [5V / VIN] ESP32-S3
   (GND)  --------------------------------> [GND]      ESP32-S3
   (SIG)  --------------------------------> [GPIO 6]   ESP32-S3

