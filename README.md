# Rozproszone systemy pomiarowe

Rozproszony system pomiarowy: ESP32 z czujnikami BMP280 publikuje dane przez
MQTT, ingestor zapisuje je do PostgreSQL, Flask REST API udostępnia odczyt
dla klienta — dashboard webowy w Streamlit (`wykresy_python/`).

## Architektura

```
ESP32 + BMP280  ──MQTT──►  Mosquitto  ──MQTT──►  Ingestor  ──SQL──►  PostgreSQL
                                                                          │
                                                                          ▼
                                              Dashboard   ◄──HTTP──  Flask API
```

Pełna dokumentacja: [`docs/`](docs/) (moduły) lub
[`DOKUMENTACJA.md`](DOKUMENTACJA.md) (wersja zbiorcza do druku).

## Quick start

### Wymagania

- Docker + Docker Compose (Windows: WSL2 backend).
- PlatformIO (VS Code) do firmware ESP32.

### Konfiguracja

```bash
cp .env.example .env
# uzupełnij DB_NAME, DB_USER, DB_PASSWORD
```

### Uruchomienie

```bash
# Pierwszy raz — z logami
docker compose up --build

# W tle
docker compose up -d --build

# Stop
docker compose down
```

### Dashboard webowy (Streamlit)

Dashboard działa **poza Dockerem** — uruchom go osobno po starcie backendu:

```bash
cd wykresy_python

# Pierwsze uruchomienie — utwórz środowisko wirtualne i zainstaluj zależności
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
# source .venv/bin/activate

pip install -r requirements.txt

# Uruchom
streamlit run app.py
```

Dashboard otworzy się w przeglądarce pod `http://localhost:8501`.
W pasku bocznym powinien być widoczny status **Backend: online ✓**.

Szczegóły i rozwiązywanie problemów: [`docs/wykresy.md`](docs/wykresy.md).

### Weryfikacja

| Serwis     | Adres                          | Test                                       |
|------------|--------------------------------|--------------------------------------------|
| REST API   | http://localhost:5001          | `curl http://localhost:5001/health`        |
| MQTT/TLS   | localhost:8883                 | MQTT Explorer z TLS + `certs/ca.crt` (zob. docs/security_tls.md) |
| PostgreSQL | wewn. sieci Docker (5432)      | `docker exec -it postgres psql -U admin -d abcd_db` |

### Firmware ESP32

```bash
cp esp32/secrets.h.example esp32/include/secrets.h
# uzupełnij WIFI_SSID, WIFI_PASSWORD, MQTT_HOST (IP hosta!), MQTT_GROUP
```

Build i flash z PlatformIO. Szczegóły: [`docs/esp32.md`](docs/esp32.md).

## Struktura repo

```
.
├── api/               # Flask REST API (port 5001)
├── broker/            # Eclipse Mosquitto — 8883 TLS + 1883 wewn.
├── certs/             # Certyfikaty TLS (generowane lokalnie, w .gitignore)
├── database/          # PostgreSQL 18 + init SQL (5432 wewn.)
├── docs/              # Dokumentacja modułowa
├── esp32/             # Firmware PlatformIO + BMP280
├── ingestor/          # Subskrypcja MQTT → INSERT do bazy
├── ui/                # LabVIEW UI (archiwum — zastąpione przez wykresy_python/)
├── utils/             # Skrypty pomocnicze (TODO)
├── wykresy_python/    # Dashboard webowy (Streamlit) — warstwa prezentacji
├── docker-compose.yml
├── .env.example
├── DOKUMENTACJA.md    # Wersja zbiorcza dokumentacji
└── README.md
```

## Endpointy REST API

| Endpoint                                                       | Opis                                  |
|----------------------------------------------------------------|---------------------------------------|
| `GET /health`                                                  | Health check                          |
| `GET /devices`                                                 | Lista unikalnych `device_id`          |
| `GET /latest`                                                  | Ostatni pomiar per `(device, sensor)` |
| `GET /latest?device_id=...`                                    | Filtruje po urządzeniu                |
| `GET /latest/temperature`                                      | Ostatnia temperatura per urządzenie   |
| `GET /history?limit=N`                                         | Historia, DESC                        |
| `GET /history?device_id=...&sensor=...&limit=...`              | Filtrowana historia                   |

Szczegóły: [`docs/api.md`](docs/api.md).

## Format wiadomości MQTT

Topic: `lab/<group_id>/<device_id>/<sensor>`

Payload (JSON):
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

Pełny kontrakt: [`docs/message_contract.md`](docs/message_contract.md).

## Status laboratoriów

| Lab | Status                                  |
|-----|------------------------------------------|
| 0-1 | Architektura + uruchomienie środowiska — OK |
| 3   | ESP32 + MQTT — OK                        |
| 4   | Kontrakt danych — OK                     |
| 5   | Ingestor → DB — OK                       |
| 6   | REST API — OK                            |
| 7-8 | Prezentacja danych — Streamlit (`wykresy_python/`); LabVIEW w archiwum |
| 9   | Niezawodność ESP32 (reconnect, LWT) — OK |
| 10  | Security MQTT — TLS, izolacja usług — OK  |

Lab 2 (dummy sensor) pominięty — od razu wdrożone BMP280.

## Licencja

Patrz plik [LICENSE](LICENSE).
