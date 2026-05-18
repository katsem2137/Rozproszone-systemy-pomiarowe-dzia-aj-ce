# REST API

## Opis

Serwer Flask udostępniający dane pomiarowe z PostgreSQL przez HTTP/JSON.
Klient (LabVIEW, przeglądarka, curl) wykonuje żądania GET, otrzymuje JSON.

## Stos

- **Flask** (najnowsza z pip, bez pin).
- **psycopg2-binary** — dostęp do PostgreSQL.
- **Python 3.10-slim** (Dockerfile).

## Konfiguracja

- Port: `5001` (w `app.run(..., port=5001)` i mapowanie w Compose).
- Bind: `0.0.0.0` (dostępne z hosta).
- Tryb: `debug=True` (dev — w produkcji wyłączyć!).
- Połączenie z bazą: jak w ingestorze, przez zmienne `DB_*` z `.env`.

## Endpointy

Wszystkie odpowiadają na **GET**, wszystkie zwracają **JSON**.
Base URL: `http://localhost:5001`.

---

### `GET /`

Sanity check (HTML).

**Odpowiedź**: `<p>Hello, World!</p>`

---

### `GET /health`

Health check do monitoringu / orkiestracji.

**Odpowiedź**:
```json
{"status": "ok"}
```

---

### `GET /devices`

Lista unikalnych `device_id` (alfabetycznie).

**Zapytanie SQL**:
```sql
SELECT DISTINCT device_id FROM measurements ORDER BY device_id
```

**Odpowiedź**:
```json
["esp32-A1B2C3D4E5F6", "esp32-F88DAB004F8C"]
```

Pusta lista `[]` jeśli baza pusta.

---

### `GET /latest`

Ostatni pomiar dla każdej pary `(device_id, sensor)`. Wykorzystuje
PostgreSQL-specific `DISTINCT ON`.

**Parametry**:
- `device_id` (opcjonalny) — ogranicza wynik do jednego urządzenia.

**Przykłady**:
```bash
curl http://localhost:5001/latest
curl "http://localhost:5001/latest?device_id=esp32-F88DAB004F8C"
```

**Zapytanie SQL** (bez filtra):
```sql
SELECT DISTINCT ON (device_id, sensor)
    device_id, sensor, value, unit, ts_ms, received_at
FROM measurements
ORDER BY device_id, sensor, received_at DESC
```

**Odpowiedź**:
```json
[
  {
    "device_id": "esp32-F88DAB004F8C",
    "sensor": "pressure",
    "value": 1013.25,
    "unit": "hPa",
    "ts_ms": 1742030400000,
    "received_at": "2026-05-17T19:30:15.123456"
  },
  {
    "device_id": "esp32-F88DAB004F8C",
    "sensor": "temperature",
    "value": 24.5,
    "unit": "C",
    "ts_ms": 1742030400000,
    "received_at": "2026-05-17T19:30:15.123456"
  }
]
```

---

### `GET /latest/temperature`

Skrót: ostatnia temperatura dla każdego urządzenia (tylko `sensor = 'temperature'`).

**Parametry**:
- `device_id` (opcjonalny).

**Przykład**:
```bash
curl http://localhost:5001/latest/temperature
```

**Odpowiedź**: jak `/latest`, ale tylko temperatury.

---

### `GET /history`

Historia pomiarów z filtrowaniem i paginacją.

**Parametry**:
- `device_id` (opcjonalny) — filtruje po urządzeniu.
- `sensor` (opcjonalny) — filtruje po typie sensora.
- `limit` (opcjonalny, domyślnie `50`) — maks. liczba rekordów.

**Przykłady**:
```bash
curl "http://localhost:5001/history?limit=10"
curl "http://localhost:5001/history?device_id=esp32-F88DAB004F8C&sensor=temperature&limit=100"
```

**Zapytanie SQL** (z wszystkimi filtrami):
```sql
SELECT device_id, sensor, value, unit, ts_ms, received_at
FROM measurements
WHERE TRUE
  AND device_id = %s
  AND sensor = %s
ORDER BY received_at DESC
LIMIT %s
```

**Odpowiedź**: lista rekordów (DESC po `received_at`):
```json
[
  {
    "device_id": "esp32-F88DAB004F8C",
    "sensor": "temperature",
    "value": 24.7,
    "unit": "C",
    "ts_ms": 1742030410000,
    "received_at": "2026-05-17 19:30:25.123456"
  },
  {
    "device_id": "esp32-F88DAB004F8C",
    "sensor": "temperature",
    "value": 24.6,
    "unit": "C",
    "ts_ms": 1742030405000,
    "received_at": "2026-05-17 19:30:20.234567"
  }
]
```

**Uwaga** — `received_at` w `/history` jest zwracane przez `str(...)`, a w
`/latest` przez `.isoformat()`. Format minimalnie różny (`" "` vs `"T"`).
Klient powinien akceptować oba.

## Test w przeglądarce

Wszystkie endpointy są GET, więc otwierasz w przeglądarce:
- http://localhost:5001/health
- http://localhost:5001/devices
- http://localhost:5001/latest
- http://localhost:5001/latest/temperature
- http://localhost:5001/history?limit=10

## Kody HTTP

Aktualna implementacja **zawsze zwraca 200** (nawet gdy lista pusta).
Nie ma `404` dla nieznanego urządzenia ani `400` dla błędnych parametrów.

Jeśli serwer się wywróci (np. baza niedostępna) — Flask zwróci 500 z HTML-em
debugowym (bo `debug=True`).

## Bezpieczeństwo

- **Brak uwierzytelniania** — etap rozwojowy.
- **CORS niezdefiniowany** — przeglądarka z innego origin (np. file://)
  zablokuje. Do dodania: `flask-cors` jeśli klient webowy.
- **SQL Injection** — zabezpieczony przez parametryzację `%s` w psycopg2
  (nie ma sklejania stringów).
- **`debug=True`** — w produkcji wyłączyć (ujawnia stack trace + pozwala
  na zdalny exec przez Werkzeug debugger).

## Co warto dodać (znane luki)

- **`/devices/<device_id>/sensors`** — lista sensorów per urządzenie.
- **Zakres czasowy** — parametr `from` / `to` w `/history` (epoch ms lub
  ISO 8601).
- **Paginacja właściwa** — `offset` + `limit` lub kursor.
- **Agregacje** — np. `/history/aggregated?window=1m` (średnie na okno).
- **Obsługa błędów** — własne handlery 404 / 400 / 500 zwracające JSON
  zamiast HTML-a.
- **Strukturalne logowanie** — obecnie tylko stdout Flask.
- **Healthcheck głębszy** — `/health` powinien sprawdzać też połączenie
  z bazą (`SELECT 1`), nie tylko że aplikacja żyje.
- **Modularyzacja** — `models.py` jest pusty (`# TODO`), całe API to jeden
  plik `app.py`. Przy rozroście rozsądnie rozbić na blueprints.
