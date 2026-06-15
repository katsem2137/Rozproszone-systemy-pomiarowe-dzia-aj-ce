# Rozproszone Systemy Pomiarowe

Projekt laboratoryjny z przedmiotu **Systemy Rozproszone**. Pełny stos IoT: czujniki BMP280 na mikrokontrolerach ESP32 zbierają temperaturę i ciśnienie, przesyłają dane przez MQTT, backend zapisuje je do bazy PostgreSQL, a Flask REST API udostępnia je dashboardowi webowemu w Streamlit.

## Architektura

```
┌─────────┐  MQTT/TLS  ┌──────────┐  MQTT   ┌──────────┐  SQL    ┌────────────┐
│  ESP32  │ ─────────► │Mosquitto │ ──────► │ Ingestor │ ──────► │ PostgreSQL │
│ BMP280  │  port 8883 │ (broker) │ port    │ (Python) │ INSERT  │            │
└─────────┘            └──────────┘  1883   └──────────┘         └─────┬──────┘
                                    (wewn.)                            │ SELECT
                                                                       ▼
                                           ┌─────────────┐  HTTP  ┌──────────┐
                                           │  Dashboard  │ ◄───── │Flask API │
                                           │  Streamlit  │  JSON  │ port 5001│
                                           └─────────────┘        └──────────┘
```

**Stos technologiczny:** ESP32 (C++/Arduino) · Eclipse Mosquitto · Python (paho-mqtt, Flask, Streamlit) · PostgreSQL 18 · Docker Compose · PlatformIO

**Dokumentacja pełna:** [`docs/`](docs/) (osobne pliki per moduł) lub [`DOKUMENTACJA.md`](DOKUMENTACJA.md) (wersja zbiorcza).

---

## Uruchomienie

### 1. Backend (Docker)

```bash
# Skopiuj i uzupełnij zmienne środowiskowe
cp .env.example .env

# Uruchom wszystkie serwisy (broker, baza, ingestor, api)
docker compose up -d --build

# Sprawdź status
docker compose ps
```

Weryfikacja:

| Serwis | Adres | Test |
|--------|-------|------|
| REST API | `http://localhost:5001` | `curl http://localhost:5001/health` → `{"status":"ok"}` |
| MQTT/TLS | `localhost:8883` | MQTT Explorer + `certs/ca.crt` |
| PostgreSQL | wewn. Docker (5432) | `docker exec -it postgres psql -U login -d haslo` |

### 2. Dashboard webowy

Dashboard działa **poza Dockerem** — uruchom osobno:

```bash
cd wykresy_python
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Otwiera się automatycznie pod `http://localhost:8501`. Status **Backend: online ✓** w pasku bocznym potwierdza połączenie z API.

Szczegóły: [`docs/wykresy.md`](docs/wykresy.md)

### 3. Firmware ESP32

```bash
# Skopiuj i uzupełnij dane WiFi oraz IP hosta z Dockerem
cp esp32/secrets.h.example esp32/include/secrets.h
```

Build i flash z PlatformIO (VS Code). Monitor szeregowy: 115200 baud.

Szczegóły i schemat podłączenia BMP280: [`docs/esp32.md`](docs/esp32.md)

---

## Struktura repo

```
.
├── api/               # Flask REST API (port 5001)
├── broker/            # Eclipse Mosquitto — 8883 TLS + 1883 wewn.
├── certs/             # Certyfikaty TLS (własne CA, poza repo)
├── database/          # PostgreSQL 18 + schemat SQL
├── docs/              # Dokumentacja modułowa
├── esp32/             # Firmware C++/Arduino (PlatformIO)
├── ingestor/          # Subskrypcja MQTT → zapis do bazy
├── wykresy_python/    # Dashboard webowy (Streamlit)
├── ui/                # LabVIEW UI (archiwum)
├── docker-compose.yml
├── .env.example
└── DOKUMENTACJA.md    # Pełna dokumentacja (wersja zbiorcza)
```

---

## REST API — endpointy

Base URL: `http://localhost:5001`

| Endpoint | Opis |
|----------|------|
| `GET /health` | Health check |
| `GET /devices` | Lista urządzeń (`device_id`) |
| `GET /latest` | Ostatni pomiar per `(device, sensor)` |
| `GET /latest/temperature` | Ostatnia temperatura per urządzenie |
| `GET /history?limit=N` | Historia pomiarów (DESC) |
| `GET /history?device_id=...&sensor=...&limit=...` | Filtrowana historia |

Szczegóły: [`docs/api.md`](docs/api.md)

---

## Format wiadomości MQTT

Topic: `lab/<group_id>/<device_id>/<sensor>`

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

Pola wymagane: `device_id`, `sensor`, `value`, `ts_ms`. Pełny kontrakt: [`docs/message_contract.md`](docs/message_contract.md)

---

## Status laboratoriów

| Lab | Temat | Status |
|-----|-------|--------|
| 0–1 | Architektura, Docker, WSL | OK |
| 2 | ESP32 dummy sensor | Pominięte — od razu BMP280 |
| 3 | ESP32 + MQTT publish | OK |
| 4 | Kontrakt danych | OK |
| 5 | Ingestor MQTT → DB | OK |
| 6 | REST API | OK |
| 7–8 | Prezentacja danych | OK — Streamlit; LabVIEW w archiwum |
| 9 | Niezawodność ESP32 (reconnect, LWT) | OK |
| 10 | Security — MQTT/TLS, izolacja usług | OK |
