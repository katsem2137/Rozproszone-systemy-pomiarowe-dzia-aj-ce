# Firmware ESP32

## Co robi

Cyklicznie (co 5 s) odczytuje z BMP280 temperaturę i ciśnienie, opakowuje je
w JSON i publikuje do brokera MQTT na osobnych topicach. Obsługuje
reconnect Wi-Fi i MQTT, synchronizuje czas przez NTP.

## Stos

- **Płytka**: ESP32 Dev Module (PlatformIO `board = esp32dev`).
- **Framework**: Arduino.
- **Biblioteki** (`platformio.ini`):
  - `knolleary/PubSubClient` — klient MQTT.
  - `bblanchon/ArduinoJson` — serializacja JSON.
  - `adafruit/Adafruit BMP280 Library` — sterownik czujnika.

## Sprzęt

### BMP280 → ESP32 (I2C)

```
   BMP280              ESP32
   ┌──────┐           ┌──────────┐
   │ VCC  ├───────────┤ 3.3V     │
   │ GND  ├───────────┤ GND      │
   │ SCL  ├───────────┤ GPIO 22  │
   │ SDA  ├───────────┤ GPIO 21  │
   │ CSB  ├───────────┤ GPIO 23  │  (HIGH w setup → I2C zamiast SPI)
   │ SDO  ├───────────┤ GND      │  (adres I2C 0x76)
   └──────┘           └──────────┘
```

CSB i SDO są kluczowe:
- `CSB = HIGH` → BMP280 pracuje w trybie I2C (nie SPI).
- `SDO = GND` → adres I2C = `0x76` (przy `SDO = VCC` byłby `0x77`).

## Główne funkcje

### `generateDeviceIdFromEfuse()`

Czyta MAC z eFuse (`ESP.getEfuseMac()`) i formatuje na string
`esp32-XXXXXXXXXXXX`. Stabilny między restartami, unikalny per egzemplarz —
ten sam firmware na różnych płytkach generuje różne `device_id`.

```cpp
String generateDeviceIdFromEfuse() {
    uint64_t chipId = ESP.getEfuseMac();
    char id[32];
    snprintf(id, sizeof(id), "esp32-%04X%08X",
        (uint16_t)(chipId >> 32),
        (uint32_t)chipId);
    return String(id);
}
```

Alternatywa wg Lab 3 — UUIDv4 zapisany w NVS przy pierwszym starcie. Tu
celowo wariant prostszy, bo MAC-based ID wystarcza do unikalności.

### `connectWiFi()`

Łączy z siecią z `secrets.h`. Blokuje aż `WL_CONNECTED`. Po połączeniu
wypisuje IP.

### `syncNTP()`

`configTime(3600, 3600, "time.cloudflare.com", "time.google.com")` — UTC+1
z DST (CET/CEST). Blokuje aż `getLocalTime()` zwróci sukces. Bez tego
`ts_ms` byłby względny do startu układu, nie do epoki Unix.

**Uwaga**: w przykładowym `main.txt` (wzór z instrukcji) NTP używa
`configTime(0, 0, "pool.ntp.org", "time.nist.gov")` — UTC bez offsetu.
Wersja w `main.cpp` używa CET/CEST. Konsekwencja: `ts_ms` w bazie zawiera
czas lokalny, nie UTC. Jeśli planujesz wiele stref czasowych — przejść na
UTC i konwertować przy prezentacji.

### `getTimestampMs()`

Zwraca aktualny czas jako Unix epoch w ms:
```cpp
long long getTimestampMs() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return ((long long)tv.tv_sec * 1000LL) + (tv.tv_usec / 1000);
}
```

### `connectMQTT()`

Pętla retry z `delay(2000)` — łączy do `MQTT_HOST:MQTT_PORT` używając
`deviceId` jako Client ID. Jako Client ID użycie `deviceId` zapewnia
unikalność klientów na brokerze (broker rozłącza poprzedniego z tym samym
ID).

### `publishMeasurement()`

Wysyła **dwie wiadomości** za każdym wywołaniem (jedna na temperaturę,
druga na ciśnienie), z dwoma kolejnymi `seq` (inkrementowany po każdej
publikacji). Każda na własny topic:

- `lab/<MQTT_GROUP>/<deviceId>/temperature`
- `lab/<MQTT_GROUP>/<deviceId>/pressure`

Topiki obliczane raz w `setup()` jako globalne `topicTemp` i `topicPressure`
— nie ma alokacji w pętli.

### `loop()`

```cpp
void loop() {
    if (WiFi.status() != WL_CONNECTED) { connectWiFi(); syncNTP(); }
    if (!mqttClient.connected())        { connectMQTT(); }
    mqttClient.loop();
    publishMeasurement();
    delay(5000);
}
```

Co iterację: sprawdza Wi-Fi, sprawdza MQTT, obsługuje pętlę MQTT, publikuje,
czeka 5 s. `mqttClient.loop()` jest wymagane przez PubSubClient do obsługi
keep-alive i ewentualnych callbacków.

## Format wiadomości

Pełny opis: [`message_contract.md`](message_contract.md).

```json
{
  "schema_version": 1,
  "group_id": "g03",
  "device_id": "esp32-F88DAB004F8C",
  "sensor": "temperature",
  "value": 24.5,
  "unit": "C",
  "ts_ms": 1774285098907,
  "seq": 0
}
```

## Konfiguracja — secrets.h

Plik **NIE jest w repo** (`.gitignore`: `esp32/include/secrets.h`).
Skopiuj wzorzec i uzupełnij:

```bash
cp esp32/secrets.h.example esp32/include/secrets.h
```

**Uwaga na ścieżkę** — w repo wzorzec leży w `esp32/secrets.h.example`, ale
sam `secrets.h` musi być w `esp32/include/secrets.h` (PlatformIO szuka
nagłówków w `include/`).

```cpp
#define WIFI_SSID     "..."
#define WIFI_PASSWORD "..."
#define MQTT_HOST     "192.168.X.Y"  // IP HOSTA Z DOCKEREM, nie localhost!
#define MQTT_PORT     8883          // TLS (lab 10)
#define MQTT_GROUP    "g03"
```

## Build i flash

```bash
# Z PlatformIO CLI
pio run                                # build
pio run --target upload                # flash
pio device monitor                     # serial monitor (115200 baud)

# Lub w VS Code: paskek PlatformIO → Build / Upload / Monitor
```

`upload_port = COM3` w `platformio.ini` — jeśli ESP32 jest na innym COM,
zmień lub usuń (auto-detect).

## Co można dodać

- **Last Will Testament** — zarejestrować retained message na
  `lab/<grp>/<dev>/status` z payloadem `{"status":"offline"}`. Broker
  opublikuje to automatycznie gdy ESP32 zerwie połączenie (Lab 9 —
  niezawodność).
- **Buforowanie offline** — bufor w RAM (kilka pomiarów) na wypadek utraty
  połączenia, wysyłka po reconnect.
- **QoS 1** — obecnie domyślne QoS 0 (fire-and-forget). QoS 1 daje
  gwarancję dostarczenia (ale kosztuje pamięć i przepustowość).
- **Sygnalizacja LED** — diody jako wskaźnik stanu (Wi-Fi / MQTT / sensor).
- **NVS dla device_id** — wariant z Lab 3 (UUIDv4 zapisywany przy pierwszym
  starcie). Obecnie ID jest deterministyczne z MAC, więc nie ma realnej
  potrzeby.
