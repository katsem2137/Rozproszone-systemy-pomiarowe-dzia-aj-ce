#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_BMP280.h>
#include <time.h>
#include <sys/time.h>
#include "secrets.h"

/*
 * Podlaczenie BMP280 -> ESP32
 * VCC  -> 3.3V
 * GND  -> GND
 * SCL  -> GPIO 22
 * SDA  -> GPIO 21
 */

WiFiClient espClient;
PubSubClient mqttClient(espClient);
Adafruit_BMP280 bmp;

String deviceId;
String topicTemp;
String topicPressure;
String topicStatus;
uint32_t seq = 0;
bool sensorReady = false;

// Non-blocking scheduler: znaczniki ostatnich prob / publikacji
unsigned long lastWifiAttemptMs   = 0;
unsigned long lastMqttAttemptMs   = 0;
unsigned long lastMeasurementMs   = 0;

const unsigned long WIFI_RETRY_MS         = 5000;
const unsigned long MQTT_RETRY_MS         = 3000;
const unsigned long MEASUREMENT_PERIOD_MS = 5000;

String generateDeviceIdFromEfuse() {
    uint64_t chipId = ESP.getEfuseMac();
    char id[32];
    snprintf(id, sizeof(id), "esp32-%04X%08X",
        (uint16_t)(chipId >> 32),
        (uint32_t)chipId);
    return String(id);
}

long long getTimestampMs() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return ((long long)tv.tv_sec * 1000LL) + (tv.tv_usec / 1000);
}

void syncNTP() {
    configTime(3600, 3600, "time.cloudflare.com", "time.google.com");
    struct tm timeinfo;
    Serial.print("Synchronizacja NTP");
    int tries = 0;
    while (!getLocalTime(&timeinfo) && tries < 20) {
        delay(500);
        Serial.print(".");
        tries++;
    }
    if (tries >= 20) {
        Serial.println("\nNTP timeout - kontynuuje bez synchronizacji.");
    } else {
        Serial.println("\nCzas zsynchronizowany.");
    }
}

// Non-blocking reconnect Wi-Fi: probuje raz na WIFI_RETRY_MS, bez blokowania petli.
void connectWiFiIfNeeded() {
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    if (millis() - lastWifiAttemptMs < WIFI_RETRY_MS) {
        return;
    }
    lastWifiAttemptMs = millis();

    Serial.println("[WiFi] Brak polaczenia - probuje reconnect...");
    WiFi.disconnect();
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// Publikuje status urzadzenia (retained) na topic statusowy.
// state: "online" / "offline" / inny.
void publishStatus(const char* state) {
    if (!mqttClient.connected()) {
        return;
    }
    StaticJsonDocument<128> doc;
    doc["device_id"] = deviceId;
    doc["status"]    = state;
    doc["ts_ms"]     = getTimestampMs();

    char payload[128];
    serializeJson(doc, payload, sizeof(payload));
    mqttClient.publish(topicStatus.c_str(), payload, true);  // retained
    Serial.print("[STATUS] ");
    Serial.println(payload);
}

// Non-blocking reconnect MQTT: dziala tylko gdy Wi-Fi UP, probuje raz na MQTT_RETRY_MS.
// Konfiguruje Last Will (offline retained) + publikuje "online" po sukcesie.
bool connectMqttIfNeeded() {
    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }
    if (mqttClient.connected()) {
        return true;
    }
    if (millis() - lastMqttAttemptMs < MQTT_RETRY_MS) {
        return false;
    }
    lastMqttAttemptMs = millis();

    Serial.print("[MQTT] Probuje polaczyc...");

    String willPayload =
        "{\"device_id\":\"" + deviceId + "\",\"status\":\"offline\"}";

    bool ok = mqttClient.connect(
        deviceId.c_str(),
        topicStatus.c_str(),    // willTopic
        0,                      // willQos
        true,                   // willRetain
        willPayload.c_str()     // willMessage
    );

    if (ok) {
        Serial.println(" OK");
        publishStatus("online");
    } else {
        Serial.print(" blad, rc=");
        Serial.println(mqttClient.state());
    }
    return ok;
}

void publishMeasurement() {
    if (!mqttClient.connected() || !sensorReady) {
        return;
    }

    long long ts = getTimestampMs();
    float temperature = bmp.readTemperature();
    float pressure    = bmp.readPressure() / 100.0; // Pa -> hPa

    // temperatura
    StaticJsonDocument<256> doc;
    doc["schema_version"] = 1;
    doc["group_id"]       = MQTT_GROUP;
    doc["device_id"]      = deviceId;
    doc["sensor"]         = "temperature";
    doc["value"]          = temperature;
    doc["unit"]           = "C";
    doc["ts_ms"]          = ts;
    doc["seq"]            = seq++;

    char payload[256];
    serializeJson(doc, payload);
    mqttClient.publish(topicTemp.c_str(), payload);
    Serial.print("[PUB] ");
    Serial.println(payload);

    // cisnienie
    doc.clear();
    doc["schema_version"] = 1;
    doc["group_id"]       = MQTT_GROUP;
    doc["device_id"]      = deviceId;
    doc["sensor"]         = "pressure";
    doc["value"]          = pressure;
    doc["unit"]           = "hPa";
    doc["ts_ms"]          = ts;
    doc["seq"]            = seq++;

    serializeJson(doc, payload);
    mqttClient.publish(topicPressure.c_str(), payload);
    Serial.print("[PUB] ");
    Serial.println(payload);
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    // CSB na HIGH - wymagane dla trybu I2C
    pinMode(23, OUTPUT);
    digitalWrite(23, HIGH);
    delay(100);

    // Probujemy znalezc BMP280: 10 prob co 1 sekunde
    Serial.println("Inicjalizacja BMP280...");
    for (int i = 1; i <= 10; i++) {
        if (bmp.begin(0x76)) {
            sensorReady = true;
            Serial.println("BMP280 gotowy.");
            break;
        }
        Serial.print("Proba ");
        Serial.print(i);
        Serial.println("/10 - nie znaleziono BMP280");
        delay(1000);
    }
    if (!sensorReady) {
        Serial.println("BMP280 niedostepny po 10 probach. Kontynuuje bez czujnika - publikacja wstrzymana.");
    }

    deviceId      = generateDeviceIdFromEfuse();
    topicTemp     = "lab/" + String(MQTT_GROUP) + "/" + deviceId + "/temperature";
    topicPressure = "lab/" + String(MQTT_GROUP) + "/" + deviceId + "/pressure";
    topicStatus   = "lab/" + String(MQTT_GROUP) + "/" + deviceId + "/status";

    Serial.print("Device ID: ");
    Serial.println(deviceId);
    Serial.print("Status topic: ");
    Serial.println(topicStatus);

    // Inicjalne polaczenie - non-blocking (loop dokonczy reconnect jesli teraz nie wyjdzie)
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.println("[WiFi] Inicjuje polaczenie...");

    // Krotkie blokujace oczekiwanie na pierwszy connect (do 10 s) - dla NTP
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("[WiFi] OK, IP: ");
        Serial.println(WiFi.localIP());
        syncNTP();
    } else {
        Serial.println("[WiFi] Pierwsze polaczenie nie powiodlo sie - loop bedzie probowal dalej.");
    }

    mqttClient.setServer(MQTT_HOST, MQTT_PORT);
}

void loop() {
    connectWiFiIfNeeded();
    connectMqttIfNeeded();
    mqttClient.loop();  // keepalive + obsluga LWT po stronie klienta

    // Runtime retry BMP280 jezeli niedostepny
    if (!sensorReady) {
        static unsigned long lastSensorAttemptMs = 0;
        if (millis() - lastSensorAttemptMs >= 5000) {
            lastSensorAttemptMs = millis();
            if (bmp.begin(0x76)) {
                sensorReady = true;
                Serial.println("BMP280 znaleziony - rozpoczynam publikacje.");
            } else {
                Serial.println("BMP280 nadal niedostepny.");
            }
        }
    }

    // Publikacja pomiaru co MEASUREMENT_PERIOD_MS (non-blocking)
    if (millis() - lastMeasurementMs >= MEASUREMENT_PERIOD_MS) {
        lastMeasurementMs = millis();
        publishMeasurement();
    }

    delay(10);  // oddaj czas WiFi/MQTT stackom, nie blokuje logiki
}
