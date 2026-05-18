# Rozproszone systemy pomiarowe

Rozproszony system pomiarowy: ESP32 z czujnikami BMP280 publikuje dane przez
MQTT, ingestor zapisuje je do PostgreSQL, Flask REST API udostępnia odczyt
dla klienta (planowany LabVIEW UI).

## Architektura

```
ESP32 + BMP280  ──MQTT──►  Mosquitto  ──MQTT──►  Ingestor  ──SQL──►  PostgreSQL
                                                                          │
                                                                          ▼
                                              LabVIEW UI  ◄──HTTP──  Flask API
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

### Weryfikacja

| Serwis     | Adres                          | Test                                       |
|------------|--------------------------------|--------------------------------------------|
| REST API   | http://localhost:5001          | `curl http://localhost:5001/health`        |
| MQTT       | localhost:1883                 | MQTT Explorer, bez auth                    |
| PostgreSQL | localhost:5432                 | `docker exec -it postgres psql -U admin -d abcd_db` |

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
├── broker/            # Eclipse Mosquitto config (port 1883)
├── database/          # PostgreSQL 18 + init SQL (port 5432)
├── docs/              # Dokumentacja modułowa
├── esp32/             # Firmware PlatformIO + BMP280
├── ingestor/          # Subskrypcja MQTT → INSERT do bazy
├── ui/                # LabVIEW UI
├── utils/             # Skrypty pomocnicze (TODO)
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
| 7-8 | LabVIEW UI — Zrobione                    |

Lab 2 (dummy sensor) pominięty — od razu wdrożone BMP280.

## Licencja

Patrz plik [LICENSE](LICENSE).
