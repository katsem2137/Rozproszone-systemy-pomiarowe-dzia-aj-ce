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
                                              Dashboard   ◄──HTTP──  Flask API
```

### Warstwy

1. **ESP32 + BMP280** — pomiar temperatury i ciśnienia co 5 s, publikacja JSON
   do MQTT.
2. **MQTT (Eclipse Mosquitto)** — dwa listenery: `8883` TLS (ESP32, wystawiony
   na hosta) oraz `1883` plaintext (tylko wewnątrz sieci Docker, dla ingestora).
   Szczegóły: sekcja 10 (Bezpieczeństwo — TLS).
3. **Ingestor (Python + paho-mqtt)** — subskrypcja `lab/+/+/+`, walidacja
   kontraktu, zapis do PostgreSQL.
4. **PostgreSQL 18** — tabela `measurements` przechowuje wszystkie pomiary +
   metadane (topic, czas odebrania).
5. **REST API (Python + Flask)** — udostępnia dane przez endpointy GET
   zwracające JSON.
6. **Dashboard webowy (Streamlit)** — klient REST z dashboardem (kafelki,
   wykresy Plotly, historia, CSV). LabVIEW (`ui/`) w archiwum.

### Konteneryzacja

Cztery serwisy w Docker Compose: `broker`, `database`, `ingestor`, `flask` (api).
ESP32 i dashboard (Streamlit) poza Dockerem (sprzęt fizyczny / klient REST w przeglądarce).

### Decyzje architektoniczne

- **ESP nie pisze do bazy bezpośrednio** — rozdzielenie warstw, walidacja
  centralna w ingestorze, kontrakt MQTT stabilnym interfejsem.
- **Prezentacja przez REST, nie SQL** — REST ukrywa schemat bazy, daje stabilny
  kontrakt, pozwala filtrować po stronie backendu.
- **Osobne topiki na sensor** — pozwala selektywnie subskrybować (np. tylko
  temperatury z wszystkich urządzeń przez `lab/+/+/temperature`).

---

## 2. Uruchomienie

### Wymagania

- Docker Desktop + Docker Compose (WSL2 backend na Windows).
- PlatformIO (rozszerzenie VS Code) do firmware ESP32.
- Wolne porty: `8883` (MQTT/TLS), `5001` (API). Po lab 10 `1883` i `5432` nie są
  wystawiane na hosta — działają tylko wewnątrz sieci Docker `backend`.

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

### Dashboard webowy (Streamlit)

Dashboard działa **poza Dockerem** — uruchom po starcie backendu:

```bash
cd wykresy_python

# Pierwsze uruchomienie — zainstaluj zależności
python -m pip install -r requirements.txt

# Uruchom
python -m streamlit run app.py
```

Przeglądarka otworzy się automatycznie pod `http://localhost:8501`.
W pasku bocznym powinien być widoczny status **Backend: online ✓**.

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
# w MQTT Explorer: localhost:8883, włącz Encryption (TLS), wczytaj certs/ca.crt

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

## 8. Prezentacja danych — Dashboard webowy (Streamlit)

Warstwą prezentacji jest **dashboard w Streamlit** (`wykresy_python/`): kafelki
aktualnych pomiarów, wykresy trendu (Plotly, linie spline, stały krok osi Y),
historia z eksportem CSV, filtr dat i auto-odświeżanie. Czyta wyłącznie przez
REST API (`localhost:5001`), działa **poza Dockerem**.

```bash
cd wykresy_python
python -m pip install -r requirements.txt
python -m streamlit run app.py        # http://localhost:8501
```

Pełna dokumentacja: [`docs/wykresy.md`](docs/wykresy.md).

> **LabVIEW — archiwum.** Poniższy opis dotyczy poprzedniej warstwy prezentacji
> (LabVIEW), z której zrezygnowano. Zostaje w repo (`ui/`,
> [`docs/labview.md`](docs/labview.md)) jako archiwum.

### (Archiwum) LabVIEW UI

Aplikacja desktopowa w LabVIEW — warstwa prezentacji. Komunikuje się
z backendem przez REST (Flask, `localhost:5001`), działa **poza Dockerem**.

### Wymagania

- LabVIEW 2024 Q3 lub nowszy (`*.vi` w 24.3.1, `*.ctl` w 24.1.1).
- **JKI REST Client** (instalacja przez VI Package Manager) —
  używane: `Create REST Client.vi`, `HTTP GET.vi`,
  `Destroy REST Client.vi`.

### Struktura

```
labview/
├── epoch to cluster.vi      # ts_ms (epoch ms) → LabVIEW timestamp
└── template/
    ├── main.vi              # Główny VI: UI + logika REST
    ├── kontrakt.ctl         # Typedef cluster z parametrami żądania
    │                        # (device_id, sensor, limit)
    └── measure_data.ctl     # Typedef cluster pojedynczego pomiaru
                             # (device_id, sensor, value, unit, ts_ms,
                             #  received_at)
```

### Cykl działania (`main.vi`)

1. `Create REST Client.vi` z `base URL = http://localhost:5001`.
2. `HTTP GET.vi` → endpoint API (`/latest`, `/history`, …) z filtrami
   z `kontrakt.ctl`.
3. Parsowanie JSON → tablica clustrów `measure_data.ctl`.
4. `epoch to cluster.vi` konwertuje `ts_ms` (I64) na timestamp.
5. Wyświetlenie: wskaźniki + tabela + wykres trendu (XY Graph).
6. `Destroy REST Client.vi` przy zamknięciu.

### Mapowanie widoków na endpointy

| Widok                                | Endpoint                                          |
|--------------------------------------|---------------------------------------------------|
| Lista urządzeń (dropdown)            | `GET /devices`                                    |
| Aktualne pomiary                     | `GET /latest`                                     |
| Aktualne dla urządzenia              | `GET /latest?device_id=...`                       |
| Trend temperatury                    | `GET /history?sensor=temperature&limit=N`         |

### Uruchomienie

1. Backend działa: `docker compose up -d`, `curl :5001/health`.
2. Otwórz `labview/template/main.vi` w LabVIEW.
3. Jeśli brakuje JKI REST Client — doinstaluj przez VIPM.
4. *Run* (biała strzałka).

Pełna dokumentacja: [`docs/labview.md`](docs/labview.md).

---

## 9. Niezawodność ESP32 (lab 9)

Firmware został przepisany na **non-blocking** scheduler oparty o `millis()`.
Wszystkie operacje sieciowe (reconnect Wi-Fi, reconnect MQTT, publikacja)
działają bez blokujących pętli `while`.

### Topic statusowy

```
lab/<group_id>/<device_id>/status
```

Topic techniczny oddzielony od pomiarowych. Payload `online` (retained)
po reconnect, `offline` (LWT, retained) — broker publikuje sam przy
niepoprawnym rozłączeniu klienta.

```json
{"device_id": "esp32-...", "status": "online", "ts_ms": 1742030400000}
{"device_id": "esp32-...", "status": "offline"}
```

### Mechanizmy reconnect

| Mechanizm        | Retry | Pre-warunek          |
|------------------|-------|----------------------|
| `connectWiFiIfNeeded()` | 5 s | —                |
| `connectMqttIfNeeded()` | 3 s | Wi-Fi UP         |

Każdy z nich w `loop()` sprawdza stan i pomija próbę jeśli ostatnia
była zbyt świeża — żadnego `while`, żadnego `delay()` w ścieżce
reconnect.

### Last Will and Testament

`mqttClient.connect()` rejestruje LWT przy każdym (re)connect:

```c
mqttClient.connect(
    deviceId.c_str(),
    topicStatus.c_str(),      // willTopic
    0,                         // willQos
    true,                      // willRetain
    willPayload.c_str()        // {"device_id":..., "status":"offline"}
);
```

Broker publikuje LWT gdy wykryje brak keepalive (~15 s w PubSubClient).

### Scenariusze testowe (skrót)

1. **Utrata Wi-Fi** — wyłącz AP / przenieś poza zasięg. Obserwuj UART
   (`[WiFi] Brak polaczenia` co 5 s) i topic statusowy (`offline` po
   wygaśnięciu keepalive).
2. **Niedostępny broker** — `docker stop broker`. Obserwuj UART
   (`[MQTT] Probuje polaczyc... blad`). Po `docker start broker` —
   reconnect i `online`.
3. **LWT** — odłącz zasilanie ESP. W MQTT Explorer na topicu statusowym
   pojawi się `offline` po ~15 s.
4. **Powrót do publikacji** — przywróć warunki, pomiary lecą dalej.

Pełna dokumentacja: [`docs/reliability_esp32.md`](docs/reliability_esp32.md).

---

## 10. Bezpieczeństwo — TLS na MQTT (lab 10)

Komunikacja ESP32 ↔ broker została zaszyfrowana (TLS), a usługi w Dockerze
odizolowane. Zastosowano **TLS na granicy zaufania**: ruch przez sieć Wi-Fi
(ESP32 → broker) idzie po TLS na porcie `8883`, a ruch wewnątrz sieci Docker
(ingestor → broker) pozostaje na `1883`, nieeksponowanym na hosta.

### Własne CA

Broker dostał certyfikat podpisany przez **własny urząd certyfikacji** (CA).
Klient (ESP32) weryfikuje tożsamość brokera tym CA. Klucze prywatne
(`certs/*.key`) są poza repozytorium (`.gitignore`); publiczny `ca.crt` jest
wkompilowany w firmware.

### Broker — dwa listenery (`broker/mosquitto.conf`)

```conf
listener 1883                         # tylko wewnątrz sieci Docker (ingestor)
listener 8883                         # TLS — ESP32 i klienci zewnętrzni
cafile   /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile  /mosquitto/certs/server.key
```

Certyfikaty montowane do kontenera wolumenem `:ro` (klucz poza obrazem).

### Izolacja (docker-compose)

- dedykowana sieć bridge `backend`,
- na hosta wystawione tylko `8883` (broker) i `5001` (API),
- baza bez mapowania `5432` — nieosiągalna z hosta.

### ESP32

`WiFiClientSecure` + `setCACert(ca.crt)`, port `8883`. Wymaga ustawionego czasu
(NTP) do weryfikacji dat ważności certyfikatu.

### Pułapka: mbedTLS i IP w SAN

ESP łączy się po IP, a mbedTLS dopasowuje nazwę hosta tylko do wpisów SAN typu
**DNS**, nie **IP** — stąd `-9984 X509 verification failed` mimo poprawnego
certyfikatu. Rozwiązanie: wpisać IP w SAN **także jako DNS** (`DNS:156.17.45.51`).
Wymaga tylko przepisania certyfikatu serwera (CA bez zmian → ESP bez ponownego
wgrywania).

### Weryfikacja

```bash
# handshake + weryfikacja CA (z hosta), dopasowanie po nazwie jak mbedTLS:
openssl s_client -connect 156.17.45.51:8883 -CAfile certs/ca.crt -verify_hostname 156.17.45.51
# Verify return code: 0 (ok)

# plaintext na 8883 jest odrzucany: "wrong version number / First packet not CONNECT"
```

Pełna dokumentacja: [`docs/security_tls.md`](docs/security_tls.md).

---

## 11. Test end-to-end

1. Uruchom Compose: `docker compose up -d --build`.
2. Wgraj firmware na ESP32 (skonfigurowany `secrets.h`).
3. ESP32 publikuje co 5 s na dwa topiki (temperature, pressure).
4. Sprawdź logi ingestora: powinno lecieć `[OK] Zapisano...`.
5. Sprawdź bazę:
   ```bash
   docker exec -it postgres psql -U admin -d abcd_db \
     -c "SELECT device_id, sensor, value, unit, received_at FROM measurements ORDER BY id DESC LIMIT 10;"
   ```
6. Sprawdź API: `curl http://localhost:5001/latest` powinno zwrócić ostatnie
   pomiary.
7. Uruchom dashboard: `cd wykresy_python && python -m streamlit run app.py`.
   Pod `http://localhost:8501` powinny być widoczne aktualne kafelki i wykresy
   z danymi z ESP32.

---

## 12. Status vs laboratoria

| Lab  | Temat                                | Status                              |
|------|--------------------------------------|--------------------------------------|
| 0    | Architektura, narzędzia              | OK                                   |
| 1    | Onboarding, Docker, WSL              | OK                                   |
| 2    | ESP32 dummy + Wi-Fi                  | Pominięte (od razu BMP280)           |
| 3    | ESP32 + MQTT publish                 | OK (`esp32/src/main.cpp`)            |
| 4    | Kontrakt danych                      | OK (`docs/message_contract.md`)      |
| 5    | Ingestor MQTT → DB                   | OK (`ingestor/`)                     |
| 6    | REST API                             | OK (`api/`)                          |
| 7-8  | Prezentacja danych                   | Streamlit (`wykresy_python/`, `docs/wykresy.md`); LabVIEW w archiwum |
| 9    | Niezawodność (reconnect, LWT, status)| OK (`esp32/src/main.cpp`, `docs/reliability_esp32.md`) |
| 10   | Security MQTT — TLS + izolacja usług | OK (`docs/security_tls.md`)          |

