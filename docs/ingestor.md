# Ingestor MQTT → PostgreSQL

## Opis

Serwis backendowy w Pythonie, który subskrybuje wszystkie pomiary z brokera
MQTT, waliduje strukturę wiadomości i zapisuje poprawne dane do PostgreSQL.
Odpowiedzialny za **walidację kontraktu** — wiadomości bez wymaganych pól
są odrzucane z logiem `[SKIP]`.

## Stos

- **Python 3.10-slim** (Dockerfile).
- **paho-mqtt 1.6.1** — klient MQTT.
- **psycopg2-binary 2.9.9** — sterownik PostgreSQL.

## Struktura

```
ingestor/
├── ingestor.py     # główna logika: MQTT + walidacja + zapis
├── db.py           # połączenie z PostgreSQL
├── requirements.txt
└── Dockerfile
```

## Konfiguracja

Połączenia są skonfigurowane przez **zmienne środowiskowe** (z `.env` w
Compose) z fallbackami w `db.py`:

| Zmienna       | Domyślnie (fallback)  |
|---------------|------------------------|
| `DB_HOST`     | `postgres`             |
| `DB_NAME`     | `abcd_db`              |
| `DB_USER`     | `admin`                |
| `DB_PASSWORD` | `admin_pass1234`       |

Adres brokera jest **na sztywno** w `ingestor.py`:
```python
MQTT_HOST = "broker"   # nazwa kontenera w Compose
MQTT_PORT = 1883
MQTT_TOPIC = "lab/+/+/+"
```

## Działanie

### Subskrybowany wzorzec topiców

```
lab/+/+/+
```

Pasuje do każdego `lab/<grupa>/<urządzenie>/<sensor>` — np.:
- `lab/g03/esp32-F88DAB004F8C/temperature` ✓
- `lab/g03/esp32-F88DAB004F8C/pressure` ✓
- `lab/g03/esp32-F88DAB004F8C/status/online` ✗ (5 segmentów)
- `lab/g03/esp32-F88DAB004F8C` ✗ (3 segmenty)

### Pola wymagane (walidacja)

```python
REQUIRED_FIELDS = ["device_id", "sensor", "value", "ts_ms"]
```

Wszystkie muszą być obecne. Wartości nie są walidowane typowo (string vs
liczba) — to obowiązek nadawcy.

### Pola opcjonalne (zapisywane jeśli są)

`schema_version`, `group_id`, `unit`, `seq`. Pobierane przez `data.get(...)`
— jeśli brak, do bazy trafi `NULL`.

### Pętla zdarzeniowa

Wzorzec callbacków paho-mqtt:

```python
def on_connect(client, userdata, flags, rc):
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        if not is_valid(data):
            print(f"[SKIP] Brak wymaganych pol: ...")
            return
        save_measurement(msg.topic, data)
        print(f"[OK] Zapisano z topicu: {msg.topic}")
    except Exception as e:
        print(f"[ERR] {e}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_forever()
```

`loop_forever()` blokuje główny wątek i obsługuje połączenie + reconnect.

### Zapis do bazy

```sql
INSERT INTO measurements
    (group_id, device_id, sensor, value, unit, ts_ms, seq, topic)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
```

Każda wiadomość = jeden `INSERT` z commit. **Nie ma batchowania** — przy
dużym ruchu można optymalizować przez `executemany` lub buforowanie.

Topic jest zapisywany jako dodatkowa kolumna — pozwala śledzić skąd
wiadomość przyszła, nawet jeśli `group_id` w payloadzie był pomylony lub
brakujący.

## Uruchomienie

Razem z Compose:
```bash
docker compose up -d --build ingestor
docker compose logs -f ingestor
```

Sam (do debugowania, wymaga lokalnej bazy i brokera):
```bash
cd ingestor
pip install -r requirements.txt
python ingestor.py
```

## Test

### Publikacja testowa przez mosquitto_pub

```bash
mosquitto_pub -h localhost -p 1883 \
  -t "lab/g03/esp32-test/temperature" \
  -m '{"device_id":"esp32-test","sensor":"temperature","value":24.5,"unit":"C","ts_ms":1742030400000}'
```

Oczekiwane:
- Log ingestora: `[OK] Zapisano z topicu: lab/g03/esp32-test/temperature`.
- W bazie nowy rekord (`SELECT * FROM measurements ORDER BY id DESC LIMIT 1`).

### Test wiadomości błędnej

```bash
mosquitto_pub -h localhost -p 1883 \
  -t "lab/g03/esp32-test/temperature" \
  -m '{"device_id":"esp32-test","sensor":"temperature","value":24.5}'
```

(brak `ts_ms`)

Oczekiwane:
- Log ingestora: `[SKIP] Brak wymaganych pol: ...`.
- Brak rekordu w bazie.

### Test złamanego JSON-a

```bash
mosquitto_pub -h localhost -p 1883 \
  -t "lab/g03/esp32-test/temperature" \
  -m 'not a json'
```

Oczekiwane:
- Log ingestora: `[ERR] Expecting value: line 1 column 1 (char 0)`.

## Znane ograniczenia

- **Nowe połączenie z DB per wiadomość** — `save_measurement` otwiera i
  zamyka połączenie za każdym razem. Przy dużym ruchu to wąskie gardło. Do
  poprawy: pool połączeń (`psycopg2.pool.SimpleConnectionPool`) albo jedno
  długie połączenie z reconnect przy błędzie.
- **Brak walidacji typów** — `value` jako string przejdzie walidację
  `is_valid` ale zawiedzie w `INSERT` (`DOUBLE PRECISION`). Trafi do
  `[ERR]`, nie do `[SKIP]`.
- **Brak idempotencji** — duplikaty wiadomości (np. po reconnect MQTT przy
  QoS 1) tworzą duplikat rekordów. Możliwe rozwiązanie: `UNIQUE
  (device_id, sensor, ts_ms, seq)` + `ON CONFLICT DO NOTHING`.
- **Brak `keep-alive` długiego** — domyślne 60 s. Przy bardzo
  niestabilnej sieci może to być za długo do wykrycia rozłączenia.
- **Hardkodowany `MQTT_HOST = "broker"`** — działa tylko w Compose. Do
  uruchomienia poza Compose: refaktor na `os.getenv("MQTT_HOST", "broker")`.
