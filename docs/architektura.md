# Architektura systemu

## Przegląd

Rozproszony system pomiarowy, w którym urządzenia ESP32 z czujnikami BMP280
zbierają dane (temperatura, ciśnienie), publikują je przez MQTT, a warstwa
backendowa odbiera, waliduje, zapisuje do bazy i udostępnia przez REST API.

## Przepływ danych end-to-end

```
┌─────────┐  MQTT    ┌────────┐  MQTT    ┌──────────┐  SQL    ┌────────────┐
│  ESP32  │ ───────► │ Broker │ ───────► │ Ingestor │ ──────► │ PostgreSQL │
│ BMP280  │ publish  │Mosquitto│ subscr.  │  paho    │ INSERT  │            │
└─────────┘          └────────┘          └──────────┘         └─────┬──────┘
                                                                    │ SELECT
                                                                    ▼
                                  ┌────────────────┐  HTTP    ┌─────────────┐
                                  │   LabVIEW UI   │ ◄─────── │ Flask REST  │
                                  │                │   JSON   │     API     │
                                  └────────────────┘          └─────────────┘
```

## Warstwy systemu

### 1. Warstwa urządzeń brzegowych — ESP32

- Mikrokontroler ESP32 z czujnikiem **BMP280** (I2C, adres 0x76).
- Mierzy temperaturę (°C) i ciśnienie (hPa) co 5 sekund.
- Generuje stabilny `device_id` z eFuse MAC: `esp32-XXXXXXXXXXXX`.
- Synchronizuje czas przez NTP (`time.cloudflare.com`, `time.google.com`).
- Publikuje do dwóch topiców MQTT (osobny dla każdego sensora).
- Auto-reconnect Wi-Fi/MQTT z backoff 2 s.

### 2. Warstwa komunikacji — MQTT (Mosquitto)

- Broker Eclipse Mosquitto — dwa listenery: `1883` (plaintext, tylko wewnątrz
  sieci Docker) oraz `8883` (TLS, dla ESP32 i klientów zewnętrznych).
- Konfiguracja: `allow_anonymous true`; TLS z własnym CA (lab 10 — patrz
  [security_tls.md](security_tls.md)).
- Persystencja włączona (`/mosquitto/data/`).
- Topic pattern: `lab/<group_id>/<device_id>/<sensor>`.

### 3. Warstwa zbierania danych — Ingestor

- Serwis w Pythonie (`paho-mqtt`).
- Subskrybuje wildcard `lab/+/+/+`.
- Waliduje obecność wymaganych pól (`device_id`, `sensor`, `value`, `ts_ms`).
- Zapisuje poprawne wiadomości do PostgreSQL przez `psycopg2`.
- Odrzuca i loguje wiadomości niezgodne z kontraktem.

### 4. Warstwa przechowywania — PostgreSQL 18

- Dwie tabele: `sensor` (metadane urządzeń) i `measurements` (pomiary).
- Inicjalizacja przez `database/01-init_database.sql` przy pierwszym starcie.
- Port `5432` — tylko wewnątrz sieci Docker (po lab 10 nie mapowany na host).

### 5. Warstwa dostępu — Flask REST API

- Serwer Flask (port `5001`).
- Endpointy odczytowe (GET): `/health`, `/devices`, `/latest`, `/history`,
  `/latest/temperature`.
- Zwraca JSON.
- Filtrowanie po `device_id`, `sensor`, `limit`.

### 6. Warstwa prezentacji — LabVIEW

- Klient REST z dashboardem (latest + trend historyczny + filtry).
- Działa **poza Dockerem** — komunikuje się z Flask przez HTTP.

## Konteneryzacja

Wszystkie serwisy backendowe uruchamiane przez Docker Compose. Cztery kontenery:

| Kontener   | Obraz                  | Port  | Zależności          |
|------------|------------------------|-------|---------------------|
| `broker`   | `eclipse-mosquitto`    | 8883 TLS (+1883 wewn.) | —      |
| `postgres` | `postgres:18-alpine`   | 5432 (wewn.)           | —      |
| `ingestor` | `python:3.10-slim`     | —     | broker, database    |
| `api`      | `python:3.10-slim`     | 5001  | database            |

Każdy kontener buduje się z własnego `Dockerfile` w odpowiednim katalogu.
ESP32 i LabVIEW NIE są w Dockerze (urządzenie fizyczne / aplikacja desktopowa).

## Decyzje architektoniczne

**Dlaczego ESP nie pisze bezpośrednio do bazy?**
Rozdzielenie warstw — urządzenie nie zna struktury bazy, ingestor centralizuje
walidację, kontrakt MQTT jest stabilnym interfejsem. Łatwiej dołożyć kolejne
urządzenia lub kolejnego subskrybenta (np. drugi ingestor do innej bazy).

**Dlaczego LabVIEW przez REST, a nie przez SQL?**
REST ukrywa schemat bazy, daje stabilny kontrakt, pozwala filtrować
po stronie backendu. Zmiana schematu bazy nie wymaga zmian w UI.

**Dlaczego osobne topiki dla `temperature` i `pressure`?**
Pozwala subskrybować selektywnie (np. tylko temperatury z wszystkich urządzeń:
`lab/+/+/temperature`). Spójne z kontraktem `lab/<grp>/<dev>/<sensor>`.

## Mapowanie na laboratoria

| Lab | Temat                          | Status w repo                          |
|-----|--------------------------------|----------------------------------------|
| 0   | Architektura, narzędzia        | OK                                     |
| 1   | Onboarding, Docker, WSL        | OK (uruchamia się)                     |
| 2   | ESP32 dummy + Wi-Fi            | Pominięte — od razu BMP280             |
| 3   | ESP32 + MQTT publish           | OK (`esp32/src/main.cpp`)              |
| 4   | Kontrakt danych                | OK (`esp32/docs/message_contract.md`)  |
| 5   | Ingestor MQTT → DB             | OK (`ingestor/ingestor.py`)            |
| 6   | REST API                       | OK (`api/app.py`)                      |
| 7-8 | LabVIEW UI                     | Zrobione                               |
| 9   | Niezawodność ESP32 (reconnect, LWT) | OK (`esp32/src/main.cpp`, `docs/reliability_esp32.md`) |
| 10  | Security MQTT — TLS, izolacja usług | OK (`docs/security_tls.md`)            |
