# Baza danych — PostgreSQL

## Konfiguracja

- **Obraz**: `postgres:18-alpine` (Dockerfile w `database/`).
- **Port**: `5432` (mapowany na host).
- **Dane logowania**: z `.env` (`DB_USER`, `DB_PASSWORD`, `DB_NAME`).
- **Inicjalizacja**: `database/01-init_database.sql` uruchamia się
  automatycznie przy pierwszym starcie kontenera (mechanizm
  `/docker-entrypoint-initdb.d/`).

## Schemat

### Tabela `measurements` — pomiary

Główna tabela systemu. Każdy poprawny pomiar z MQTT trafia jako jeden rekord.

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

| Kolumna       | Typ                | Opis                                                |
|---------------|--------------------|------------------------------------------------------|
| `id`          | SERIAL PK          | Sztuczny klucz, auto-inkrement                       |
| `group_id`    | TEXT               | Grupa laboratoryjna (np. `g03`)                      |
| `device_id`   | TEXT NOT NULL      | Identyfikator urządzenia (`esp32-XXXX...`)           |
| `sensor`      | TEXT NOT NULL      | Typ czujnika (`temperature`, `pressure`)             |
| `value`       | DOUBLE PRECISION   | Wartość pomiaru                                      |
| `unit`        | TEXT               | Jednostka (`C`, `hPa`)                               |
| `ts_ms`       | BIGINT NOT NULL    | Czas pomiaru z urządzenia (Unix epoch, ms)           |
| `seq`         | INTEGER            | Numer sekwencyjny wiadomości z urządzenia            |
| `topic`       | TEXT               | Pełny topic MQTT, z którego przyszła wiadomość       |
| `received_at` | TIMESTAMP DEFAULT  | Czas odebrania przez ingestor (czas serwera)         |

**Dwa znaczniki czasu**:
- `ts_ms` — czas pomiaru na urządzeniu (po synchronizacji NTP).
- `received_at` — czas odebrania na backendzie.

Różnica między nimi to **opóźnienie sieciowe + przetwarzanie**. Pozwala
diagnozować problemy (urządzenie z rozjechanym zegarem, gubione wiadomości,
opóźniony reconnect).

### Tabela `sensor` — metadane urządzeń

```sql
CREATE TABLE sensor (
    uuid        UUID PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT,
    sensor      TEXT,
    apidetails  TEXT,
    is_online   BOOLEAN DEFAULT FALSE
);
```

**Status**: tabela zdefiniowana, ale obecnie **nieużywana** przez ingestor
ani API. Przewidziana do przyszłej rozbudowy (rejestracja urządzeń, status
online/offline z Last Will Testament).

## Przykładowe zapytania

### Lista wszystkich urządzeń
```sql
SELECT DISTINCT device_id FROM measurements ORDER BY device_id;
```

### Ostatni pomiar każdego (urządzenie, sensor)
```sql
SELECT DISTINCT ON (device_id, sensor)
    device_id, sensor, value, unit, ts_ms, received_at
FROM measurements
ORDER BY device_id, sensor, received_at DESC;
```

### Historia ostatnich 50 pomiarów temperatury
```sql
SELECT device_id, value, unit, ts_ms, received_at
FROM measurements
WHERE sensor = 'temperature'
ORDER BY received_at DESC
LIMIT 50;
```

### Statystyki per urządzenie
```sql
SELECT device_id, sensor,
       COUNT(*) as n,
       MIN(value) as min, MAX(value) as max, AVG(value) as avg,
       MAX(received_at) as last_seen
FROM measurements
GROUP BY device_id, sensor
ORDER BY device_id, sensor;
```

### Opóźnienie urządzenie → serwer (s)
```sql
SELECT device_id,
       AVG(EXTRACT(EPOCH FROM received_at) - ts_ms/1000.0) as avg_delay_s
FROM measurements
WHERE ts_ms > 1700000000000   -- po synchronizacji NTP
GROUP BY device_id;
```

## Dostęp z hosta

```bash
# Przez kontener (najprostsze)
docker exec -it postgres psql -U admin -d abcd_db

# Z hosta (np. DBeaver, pgAdmin, VS Code SQLTools)
# Host: localhost, Port: 5432, User: admin, DB: abcd_db
```

## Persystencja

Compose **nie definiuje** wolumenu dla danych Postgresa — przy `docker
compose down -v` lub przebudowie obrazu dane znikają. Do zachowania danych
między restartami dodaj wolumen w `docker-compose.yml`:

```yaml
database:
  ...
  volumes:
    - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Co warto dodać (znane luki)

- **Indeks** na `(device_id, sensor, received_at DESC)` — przyspieszy zapytania
  o historię i ostatni pomiar (obecnie tylko PK na `id`).
- **Indeks** na `received_at DESC` — przyspieszy `/history`.
- **UNIQUE** na `(device_id, sensor, ts_ms, seq)` — odporność na duplikaty
  (re-publikacja po reconnect MQTT może wysłać tę samą wiadomość dwa razy).
- **Wolumen** dla persystencji.
- **Wykorzystanie tabeli `sensor`** lub jej usunięcie.
