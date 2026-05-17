# Rozproszone Systemy Pomiarowe — Dokumentacja projektu

Zbiorcza dokumentacja systemu. Wersja modułowa: katalog [`docs/`](docs/).

---

## 1. Architektura

Rozproszony system pomiarowy zbierający dane z czujników BMP280 podłączonych
do ESP32 i prezentujący je przez REST API.

### Przepływ danych

```
ESP32 + BMP280  ──MQTT──►  Mosquitto  ──MQTT──►  Ingestor  ──SQL──►  PostgreSQL
                                                                          │
                                                                          │ SQL
                                                                          ▼
                                              LabVIEW UI  ◄──HTTP──  Flask API
```

### Warstwy

1. **ESP32 + BMP280** — pomiar temperatury i ciśnienia co 5 s, publikacja JSON
   do MQTT.
2. **MQTT (Eclipse Mosquitto)** — broker na porcie 1883, bez uwierzytelniania
   (etap rozwojowy).
3. **Ingestor (Python + paho-mqtt)** — subskrypcja `lab/+/+/+`, walidacja
   kontraktu, zapis do PostgreSQL.
4. **PostgreSQL 18** — tabela `measurements` przechowuje wszystkie pomiary +
   metadane (topic, czas odebrania).
5. **REST API (Python + Flask)** — udostępnia dane przez endpointy GET
   zwracające JSON.
6. **LabVIEW UI** — klient REST z dashboardem.

### Konteneryzacja

Cztery serwisy w Docker Compose: `broker`, `database`, `ingestor`, `flask` (api).
ESP32 i LabVIEW poza Dockerem (sprzęt fizyczny / aplikacja desktop).

### Decyzje architektoniczne

- **ESP nie pisze do bazy bezpośrednio** — rozdzielenie warstw, walidacja
  centralna w ingestorze, kontrakt MQTT stabilnym interfejsem.
- **LabVIEW przez REST, nie SQL** — REST ukrywa schemat bazy, daje stabilny
  kontrakt, pozwala filtrować po stronie backendu.
- **Osobne topiki na sensor** — pozwala selektywnie subskrybować (np. tylko
  temperatury z wszystkich urządzeń przez `lab/+/+/temperature`).

---

## 2. Uruchomienie

### Wymagania

- Docker Desktop + Docker Compose (WSL2 backend na Windows).
- PlatformIO (rozszerzenie VS Code) do firmware ESP32.
- Wolne porty: `1883`, `5001`, `5432`.

### Start backendu

```bash
# Skonfiguruj
cp .env.example .env
# uzupełnij DB_NAME, DB_USER, DB_PASSWORD w .env

# Uruchom (z logami)
docker compose up --build

# W tle
docker compose up -d --build
docker compose ps
docker compose logs -f
```

### Stop

```bash
docker compose down       # zatrzymaj
docker compose down -v    # + usuń wolumeny (kasuje bazę)
```

### Firmware ESP32

```bash
cp esp32/secrets.h.example esp32/include/secrets.h
# uzupełnij WIFI_SSID, WIFI_PASSWORD, MQTT_HOST (IP hosta z Dockerem!), MQTT_GROUP
```

Build i flash z PlatformIO (VS Code: paskek na dole). Monitor 115200 baud.

### Sprzęt BMP280 → ESP32

| BMP280 | ESP32                                  |
|--------|-----------------------------------------|
| VCC    | 3.3V                                    |
| GND    | GND                                     |
| SCL    | GPIO 22                                 |
| SDA    | GPIO 21                                 |
| CSB    | GPIO 23 (HIGH w setup → I2C)            |
| SDO    | GND (adres I2C: 0x76)                   |

### Weryfikacja

```bash
# Broker
# w MQTT Explorer: localhost:1883, bez auth — powinno połączyć

# Baza
docker exec -it postgres psql -U admin -d abcd_db -c "SELECT * FROM measurements LIMIT 5;"

# API
curl http://localhost:5001/health
curl http://localhost:5001/devices
curl http://localhost:5001/latest
```

---

## 3. Kontrakt MQTT

### Topic

```
lab/<group_id>/<device_id>/<sensor>
```

Przykład: `lab/g03/esp32-F88DAB004F8C/temperature`

### Payload JSON

```json
{
  "schema_version": 1,
  "group_id": "g03",
  "device_id": "esp32-F88DAB004F8C",
  "sensor": "temperature",
  "value": 24.5,
  "unit": "C",
  "ts_ms": 1742030400000,
  "seq": 15
}
```

### Pola wymagane

`device_id` (string), `sensor` (string), `value` (number), `ts_ms` (integer —
Unix epoch w **ms**).

### Pola opcjonalne

`schema_version`, `group_id`, `unit`, `seq`.

### Walidacja

Ingestor sprawdza tylko **obecność** czterech wymaganych pól. Wiadomość bez
któregoś z nich trafia do logu `[SKIP]` i nie jest zapisywana.

---

## 4. Firmware ESP32

### Kluczowe funkcje (`esp32/src/main.cpp`)

- `generateDeviceIdFromEfuse()` — `esp32-XXXXXXXXXXXX` z MAC eFuse. Stabilny,
  unikalny per płytka.
- `connectWiFi()` — łączenie z siecią z `secrets.h`.
- `syncNTP()` — synchronizacja czasu (CET/CEST przez Cloudflare + Google).
- `getTimestampMs()` — Unix epoch w ms (`gettimeofday`).
- `connectMQTT()` — retry co 2 s, Client ID = `deviceId`.
- `publishMeasurement()` — **dwie publikacje** per wywołanie: temperatura na
  `lab/<grp>/<dev>/temperature`, ciśnienie na `lab/<grp>/<dev>/pressure`.
- `loop()` — co 5 s sprawdza Wi-Fi + MQTT, publikuje.

### Konwencje

- Topiki obliczone raz w `setup()` jako stringi globalne — bez alokacji
  w pętli.
- Wspólny payload przez `StaticJsonDocument<256>` — clear + serialize per
  sensor.
- `seq` inkrementowany po każdej publikacji (osobno dla T i P).

---

## 5. Ingestor

### Plik: `ingestor/ingestor.py`

```python
MQTT_HOST = "broker"          # nazwa kontenera Compose
MQTT_PORT = 1883
MQTT_TOPIC = "lab/+/+/+"      # subskrypcja wildcard

REQUIRED_FIELDS = ["device_id", "sensor", "value", "ts_ms"]
```

### Pętla

- `on_connect` → `client.subscribe("lab/+/+/+")`.
- `on_message` → `json.loads` → walidacja → `INSERT` lub `[SKIP]` / `[ERR]`.
- `client.loop_forever()` — blokuje, obsługuje reconnect.

### Zapis

```sql
INSERT INTO measurements
    (group_id, device_id, sensor, value, unit, ts_ms, seq, topic)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
```

Nowe połączenie z DB **per wiadomość** (proste, ale do optymalizacji przy
dużym ruchu — pool połączeń).

### Logi

```
[MQTT] Polaczono z brokerem, rc=0
[MQTT] Subskrypcja: lab/+/+/+
[OK]   Zapisano z topicu: lab/g03/esp32-XXXX/temperature
[SKIP] Brak wymaganych pol: {...}
[ERR]  Expecting value: line 1 column 1 (char 0)
```

---

## 6. Baza danych

### Tabela `measurements`

```sql
CREATE TABLE IF NOT EXISTS measurements (
    id           SERIAL PRIMARY KEY,
    group_id     TEXT,
    device_id    TEXT NOT NULL,
    sensor       TEXT NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    unit         TEXT,
    ts_ms        BIGINT NOT NULL,
    seq          INTEGER,
    topic        TEXT,
    received_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Dwa znaczniki czasu: `ts_ms` (z urządzenia, po NTP) i `received_at` (z
serwera). Różnica = opóźnienie sieciowe + przetwarzanie.

### Tabela `sensor`

Zdefiniowana w `01-init_database.sql`, ale **nieużywana** przez obecny kod.
Przewidziana do rejestracji metadanych urządzeń (status online/offline z LWT).

### Inicjalizacja

`database/01-init_database.sql` uruchamia się automatycznie przez
`/docker-entrypoint-initdb.d/` przy pierwszym starcie kontenera.

### Persystencja

**Brak wolumenu** w obecnej konfiguracji — `docker compose down -v` lub
rebuild obrazu kasuje dane. Do zachowania danych między restartami: dodać
wolumen w `docker-compose.yml`.

---

## 7. REST API

Wszystkie endpointy: **GET**, zwracają JSON. Base URL:
`http://localhost:5001`.

| Endpoint                          | Opis                                                    |
|-----------------------------------|---------------------------------------------------------|
| `/`                               | `Hello, World!` (sanity)                                |
| `/health`                         | `{"status":"ok"}`                                       |
| `/devices`                        | Lista unikalnych `device_id`                            |
| `/latest`                         | Ostatni pomiar per `(device_id, sensor)`                |
| `/latest?device_id=...`           | Filtruje po urządzeniu                                  |
| `/latest/temperature`             | Ostatnia temperatura per urządzenie                     |
| `/history?limit=N`                | Historia (DESC po `received_at`, domyślnie 50)          |
| `/history?device_id=...&sensor=...&limit=...` | Filtrowane                                  |

### Przykłady

```bash
curl http://localhost:5001/devices
# ["esp32-F88DAB004F8C"]

curl http://localhost:5001/latest
# [{"device_id":"esp32-F88...","sensor":"temperature","value":24.5,...}, ...]

curl "http://localhost:5001/history?device_id=esp32-F88DAB004F8C&sensor=temperature&limit=10"
# [10 ostatnich temperatur tego urządzenia, DESC]
```

### Bezpieczeństwo

- Brak uwierzytelniania (etap rozwojowy).
- SQL Injection — zabezpieczony przez parametryzację `%s` w psycopg2.
- `debug=True` — w produkcji wyłączyć.

---

## 8. Test end-to-end

1. Uruchom Compose: `docker compose up -d --build`.
2. Wgraj firmware na ESP32 (skonfigurowany `secrets.h`).
3. ESP32 publikuje co 5 s na dwa topici (temperature, pressure).
4. Sprawdź logi ingestora: powinno lecieć `[OK] Zapisano...`.
5. Sprawdź bazę:
   ```bash
   docker exec -it postgres psql -U admin -d abcd_db \
     -c "SELECT device_id, sensor, value, unit, received_at FROM measurements ORDER BY id DESC LIMIT 10;"
   ```
6. Sprawdź API: `curl http://localhost:5001/latest` powinno zwrócić ostatnie
   pomiary.

---

## 9. Status vs laboratoria

| Lab  | Temat                                | Status                              |
|------|--------------------------------------|--------------------------------------|
| 0    | Architektura, narzędzia              | OK                                   |
| 1    | Onboarding, Docker, WSL              | OK                                   |
| 2    | ESP32 dummy + Wi-Fi                  | Pominięte (od razu BMP280)           |
| 3    | ESP32 + MQTT publish                 | OK (`esp32/src/main.cpp`)            |
| 4    | Kontrakt danych                      | OK (`docs/message_contract.md`)      |
| 5    | Ingestor MQTT → DB                   | OK (`ingestor/`)                     |
| 6    | REST API                             | OK (`api/`)                          |
| 7-8  | LabVIEW UI                           | Zrobione                             |
| 9    | Niezawodność (reconnect, LWT, QoS)   | Częściowo (reconnect Wi-Fi/MQTT na ESP) |
| 10   | Security MQTT (auth, ACL)            | Nie                                  |
| 11   | TLS                                  | Nie                                  |
| 12   | Obserwowalność (healthchecks, logi)  | Częściowo (`/health` jest)           |
| 13   | Skalowanie / load test               | Nie                                  |

