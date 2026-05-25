# Uruchomienie systemu

## Wymagania

- **Docker Desktop** + **Docker Compose** (Windows: WSL2 backend).
- **PlatformIO** (VS Code extension) do firmware ESP32.
- **MQTT Explorer** (opcjonalnie, do podglądu wiadomości — po lab 10 z TLS).
- Porty `8883` (MQTT/TLS) i `5001` (API) wolne na hoście. Porty `1883` i `5432`
  działają tylko wewnątrz sieci Docker (nie są mapowane na host).

## Backend — Docker Compose

### Konfiguracja

W katalogu głównym skopiuj `.env.example` jako `.env` i uzupełnij:

```dotenv
DB_HOST=postgres
DB_NAME=abcd_db
DB_USER=admin
DB_PASSWORD=admin_pass1234
```

**Uwaga**: `DB_HOST=postgres` to nazwa kontenera w sieci Compose — nie
zmieniaj. Hasło można zmienić, ale musi być spójne z `.env`.

### Start

```bash
# Pierwszy raz — z logami w foreground (widać błędy startu)
docker compose up --build

# Później — w tle
docker compose up -d --build

# Status
docker compose ps

# Logi
docker compose logs -f
docker compose logs -f ingestor
docker compose logs -f api
docker compose logs -f broker
docker compose logs -f database
```

### Stop

```bash
docker compose down              # zatrzymaj
docker compose down -v           # zatrzymaj + usuń wolumeny (kasuje bazę!)
```

## Weryfikacja działania

### Broker MQTT

W MQTT Explorer:
- Host: `localhost`, Port: `8883`, włącz **Encryption (TLS)** i wczytaj
  `certs/ca.crt` (po lab 10 broker wymaga TLS — patrz [security_tls.md](security_tls.md)).
- Powinno połączyć się i pokazać drzewo topiców `$SYS`.

### Baza PostgreSQL

```bash
docker exec -it postgres psql -U admin -d abcd_db
```

W psql:
```sql
\dt                          -- lista tabel
SELECT COUNT(*) FROM measurements;
SELECT * FROM measurements ORDER BY received_at DESC LIMIT 5;
\q
```

### REST API

W przeglądarce lub przez `curl`:

```bash
curl http://localhost:5001/                   # "Hello, World!"
curl http://localhost:5001/health             # {"status":"ok"}
curl http://localhost:5001/devices            # lista device_id
curl http://localhost:5001/latest             # ostatni pomiar per (device,sensor)
curl http://localhost:5001/latest/temperature # ostatnia temperatura per urządzenie
curl "http://localhost:5001/history?limit=10" # historia (DESC)
```

### Ingestor

Powinien w logach pisać:
```
[MQTT] Polaczono z brokerem, rc=0
[MQTT] Subskrypcja: lab/+/+/+
[OK] Zapisano z topicu: lab/g03/esp32-XXXX/temperature   # po każdej wiadomości
```

## Firmware ESP32

### Konfiguracja

W `esp32/` skopiuj `secrets.h.example` jako `include/secrets.h` (UWAGA — plik
musi trafić do `include/`, nie obok `secrets.h.example`):

```cpp
#define WIFI_SSID     "NAZWA_WIFI_LAB"
#define WIFI_PASSWORD "HASLO_WIFI"
#define MQTT_HOST     "192.168.X.Y"   // IP hosta z Dockerem (sprawdź ipconfig)
#define MQTT_PORT     8883          // TLS (lab 10)
#define MQTT_GROUP    "g03"           // numer grupy laboratoryjnej
```

**Klucz**: `MQTT_HOST` to IP komputera z Dockerem w sieci laboratoryjnej, NIE
`localhost` (ESP32 nie jest na tym samym hoście co broker). Na Windows
sprawdzasz przez `ipconfig` w sekcji "Wireless LAN adapter Wi-Fi → IPv4
Address".

### Sprzęt — BMP280 → ESP32

| BMP280 | ESP32        |
|--------|--------------|
| VCC    | 3.3V         |
| GND    | GND          |
| SCL    | GPIO 22      |
| SDA    | GPIO 21      |
| CSB    | GPIO 23 (HIGH w `setup()` — wymusza I2C) |
| SDO    | GND (adres I2C: 0x76) |

### Build i upload

W VS Code z PlatformIO:
1. **Build** (ikona ✓ na pasku PlatformIO).
2. Podłącz ESP32 przez USB (powinien się wykryć na COM3 — sprawdź
   `platformio.ini`, w razie potrzeby zmień `upload_port` i `monitor_port`).
3. **Upload** (ikona →).
4. **Serial Monitor** — powinno się pojawić:
   ```
   BMP280 gotowy.
   Device ID: esp32-A1B2C3D4E5F6
   Laczenie z Wi-Fi: NAZWA_WIFI
   ...
   Polaczono z Wi-Fi
   Adres IP: 192.168.X.Z
   Synchronizacja NTP...
   Czas zsynchronizowany.
   Laczenie z MQTT...OK
   Publikacja: {"schema_version":1,"group_id":"g03",...,"sensor":"temperature","value":24.3,...}
   ```

## Test end-to-end

1. Uruchom Docker Compose.
2. Wgraj firmware na ESP32.
3. ESP32 publikuje → broker → ingestor → baza.
4. Sprawdź logi ingestora (`[OK] Zapisano...`).
5. Sprawdź bazę (`SELECT ... FROM measurements`).
6. Sprawdź API (`curl http://localhost:5001/latest`).

## Typowe problemy

**`Cannot connect to the Docker daemon`** — Docker Desktop nie działa lub WSL
nie zintegrowany. W Docker Desktop: Settings → Resources → WSL Integration.

**`port is already allocated`** — port 8883/5001 zajęty. Sprawdź
`netstat -ano | findstr :8883` i zabij proces albo zmień mapowanie portów
w `docker-compose.yml`.

**Ingestor restartuje się w pętli** — baza jeszcze się nie zainicjalizowała,
ingestor próbuje połączyć się za wcześnie. `restart: on-failure` to obsłuży,
poczekaj 10-20 s.

**ESP32 nie łączy się z MQTT** — sprawdź `MQTT_HOST` (musi być IP hosta
widoczne z sieci ESP, nie `localhost`). Sprawdź firewall Windows — port 8883
musi być otwarty dla sieci lokalnej.

**`Nie znaleziono BMP280!`** — sprawdź połączenia I2C (SDA/SCL), zasilanie
3.3V, czy CSB jest na HIGH (wymusza I2C zamiast SPI), czy SDO na GND
(adres 0x76 zamiast 0x77).

**Wiadomości publikują się, ale ingestor nic nie zapisuje** — sprawdź czy
topic pasuje do wzorca `lab/+/+/+` (musi mieć dokładnie 4 segmenty). Sprawdź
czy payload ma wszystkie 4 wymagane pola.
