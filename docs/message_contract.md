# Kontrakt danych — MQTT message v1

> Pełna kopia kontraktu, który jest też w `esp32/docs/message_contract.md`.
> Tutaj dla wygody — w docs/ projektu zgodnie z konwencją z laboratoriów.

## Struktura topicu

```
lab/<group_id>/<device_id>/<sensor>
```

Cztery segmenty rozdzielone `/`. Każde urządzenie publikuje **osobną
wiadomość na każdy typ sensora** (nie jedną wiadomość ze wszystkimi
wartościami).

**Przykład**:
```
lab/g03/esp32-F88DAB004F8C/temperature
lab/g03/esp32-F88DAB004F8C/pressure
```

### Zasady nazewnictwa segmentów

- Małe litery, bez spacji, bez polskich znaków.
- `group_id` — `g` + 2 cyfry (`g01`, `g03`...).
- `device_id` — `esp32-` + 12 znaków hex z MAC.
- `sensor` — krótki tekst (`temperature`, `pressure`, `humidity`, ...).

## Payload — wiadomość pomiarowa JSON

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

## Pola

### Wymagane

| Pole         | Typ      | Opis                                              |
|--------------|----------|---------------------------------------------------|
| `device_id`  | string   | Unikalny identyfikator urządzenia (niepusty)      |
| `sensor`     | string   | Typ sensora (niepusty)                            |
| `value`      | number   | Wartość pomiaru (int lub float)                   |
| `ts_ms`      | integer  | Czas pomiaru — Unix epoch w **milisekundach**     |

### Opcjonalne (zalecane)

| Pole             | Typ      | Opis                                            |
|------------------|----------|--------------------------------------------------|
| `schema_version` | integer  | Wersja kontraktu (obecnie `1`)                  |
| `group_id`       | string   | Identyfikator grupy laboratoryjnej              |
| `unit`           | string   | Jednostka fizyczna (`"C"`, `"hPa"`, `"%"`)      |
| `seq`            | integer  | Numer sekwencyjny wiadomości z urządzenia       |

## Reguły walidacji

W ingestorze (`ingestor/ingestor.py`):

```python
REQUIRED_FIELDS = ["device_id", "sensor", "value", "ts_ms"]

def is_valid(data):
    return all(field in data for field in REQUIRED_FIELDS)
```

Walidowana jest **tylko obecność** pól. Typy nie są sprawdzane — błąd typu
(`value` jako string) wyleci w `INSERT` do PostgreSQL i trafi do `[ERR]`,
nie do `[SKIP]`.

**Pełniejsza walidacja, której można się trzymać przy ręcznych testach**:
- `device_id` — niepusty string.
- `sensor` — niepusty string.
- `value` — liczba (int lub float), nie string.
- `ts_ms` — dodatnia liczba całkowita (Unix epoch ms — po roku 2001).
- `unit` — jeśli podany, spójny z `sensor` (`temperature` → `"C"`,
  `pressure` → `"hPa"`).
- `seq` — jeśli podany, nieujemna liczba całkowita.

## Mapowanie na schemat bazy

| Pole JSON        | Kolumna w `measurements` | Uwagi                              |
|------------------|--------------------------|-------------------------------------|
| `device_id`      | `device_id`              | NOT NULL                            |
| `sensor`         | `sensor`                 | NOT NULL                            |
| `value`          | `value`                  | NOT NULL, DOUBLE PRECISION          |
| `ts_ms`          | `ts_ms`                  | NOT NULL, BIGINT                    |
| `schema_version` | — (ignorowane)           | Pole walidacyjne klienta            |
| `group_id`       | `group_id`               | NULL jeśli brak                     |
| `unit`           | `unit`                   | NULL jeśli brak                     |
| `seq`            | `seq`                    | NULL jeśli brak                     |
| (topic MQTT)     | `topic`                  | Pełna ścieżka topicu                |
| (czas serwera)   | `received_at`            | DEFAULT CURRENT_TIMESTAMP           |

## Przykłady

### Poprawna wiadomość

```json
{
  "schema_version": 1,
  "group_id": "g03",
  "device_id": "esp32-F88DAB004F8C",
  "sensor": "temperature",
  "value": 24.5,
  "unit": "C",
  "ts_ms": 1774285098907,
  "seq": 1
}
```

Topic: `lab/g03/esp32-F88DAB004F8C/temperature` → zapis OK.

### Wiadomość błędna — brak `ts_ms`

```json
{
  "device_id": "esp32-F88DAB004F8C",
  "sensor": "temperature",
  "value": 24.5,
  "unit": "C"
}
```

Ingestor: `[SKIP] Brak wymaganych pol`. Nie zapisuje.

### Wiadomość błędna — `value` jako string

```json
{
  "device_id": "esp32-F88DAB004F8C",
  "sensor": "temperature",
  "value": "24.5",
  "unit": "C",
  "ts_ms": 1774285098907
}
```

Ingestor: `is_valid()` → True, ale `INSERT` zawiedzie (PostgreSQL nie
sparsuje stringa do `DOUBLE PRECISION`). Trafi do `[ERR]`.

### Wiadomość błędna — niepoprawny JSON

```
{ device_id: "esp32-...", value: 24.5 }
```

(brak cudzysłowów wokół kluczy)

Ingestor: `[ERR] Expecting property name enclosed in double quotes`.

## Wersjonowanie

Pole `schema_version` pozwala na ewolucję kontraktu bez łamania starych
klientów:
- v1 (obecna) — opisana wyżej.
- v2 (potencjalna) — np. `ts` jako ISO 8601 zamiast `ts_ms`, lub
  `meta: {...}` na dodatkowe pola.

Ingestor obecnie **nie patrzy** na `schema_version` — przyjmuje wszystko co
ma cztery wymagane pola. Pole jest tylko informacyjne.

## Topiki specjalne (proponowane, nie zaimplementowane)

Lab 4 dodatkowo sugeruje rozdzielenie wiadomości statusowych:

```
lab/<group_id>/<device_id>/status
```

Payload:
```json
{
  "schema_version": 1,
  "device_id": "esp32-F88DAB004F8C",
  "status": "online",
  "ts_ms": 1742030400000
}
```

Naturalne miejsce do podłączenia **Last Will Testament** w MQTT — broker
opublikuje retained `{"status":"offline"}` gdy urządzenie zerwie połączenie.
Wymaga rozszerzenia ingestora (rozróżnienie sensora pomiarowego od
statusu).
