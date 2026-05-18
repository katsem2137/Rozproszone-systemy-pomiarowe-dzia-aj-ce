# LabVIEW UI

## Opis

Aplikacja desktopowa w LabVIEW pełniąca rolę warstwy prezentacji. Konsumuje
REST API (Flask, `localhost:5001`), prezentuje aktualne pomiary i historię
w postaci dashboardu. Działa **poza Dockerem** — to natywna aplikacja
desktopowa łącząca się z backendem przez HTTP.

## Miejsce w architekturze

```
PostgreSQL ──SQL──► Flask REST API ──HTTP/JSON──► LabVIEW UI
                    (localhost:5001)
```

LabVIEW NIE łączy się bezpośrednio z bazą — komunikacja idzie przez REST.
Powód: stabilny kontrakt JSON, ukrycie schematu bazy, filtrowanie po stronie
backendu (patrz [`architektura.md`](architektura.md)).

## Wymagania

- **LabVIEW 2024 Q3** lub nowszy (pliki `*.vi` zapisane w 24.3.1, `*.ctl`
  w 24.1.1).
- **JKI REST Client** — biblioteka do obsługi HTTP/REST. Instalacja przez
  VI Package Manager (VIPM):
  ```
  Tools → VI Package Manager → search "JKI REST Client" → Install
  ```
  W VI używane są: `Create REST Client.vi`, `HTTP GET.vi`,
  `Destroy REST Client.vi`.
- **Działający backend** — uruchomione `docker compose up -d`,
  endpoint `http://localhost:5001/health` zwraca `{"status":"ok"}`.

## Struktura katalogu

```
labview/
├── epoch to cluster.vi      # Konwersja Unix epoch (ms) → timestamp/cluster
└── template/
    ├── main.vi              # Główny VI z UI (front panel + block diagram)
    ├── kontrakt.ctl         # Typedef cluster odwzorowujący kontrakt API
    └── measure_data.ctl     # Typedef cluster pojedynczego pomiaru
```

### `epoch to cluster.vi`

VI pomocniczy. Wejście: `ts_ms` z API (Unix epoch w **milisekundach**).
Wyjście: cluster z rozbiciem czasu (rok / miesiąc / dzień / godzina /
minuta / sekunda) lub natywny LabVIEW timestamp — gotowy do wyświetlenia
w UI / podpięcia pod oś czasu wykresu.

Powód osobnego VI: API zwraca czas jako liczbę w `ts_ms` (z urządzenia po
NTP) oraz `received_at` (ISO 8601). LabVIEW pracuje natywnie na typie
*Timestamp* — potrzebna konwersja.

### `template/measure_data.ctl`

Typedef cluster pojedynczego pomiaru — odpowiednik jednego rekordu JSON
z `/latest` lub `/history`. Pola odpowiadają polom z API:

| Pole LabVIEW (cluster)    | Pole JSON       | Typ                |
|---------------------------|-----------------|--------------------|
| `device_id`               | `device_id`     | String             |
| `sensor`                  | `sensor`        | String             |
| `value`                   | `value`         | Double             |
| `unit`                    | `unit`          | String             |
| `ts_ms`                   | `ts_ms`         | I64 (epoch ms)     |
| `received_at`             | `received_at`   | String / Timestamp |

Cluster jest *typedef* — zmiana definicji propaguje się do wszystkich VI
które go używają.

### `template/kontrakt.ctl`

Typedef cluster z **parametrami żądania** do API — agreguje filtry
przekazywane do endpointów `/latest`, `/latest/temperature`, `/history`:

- `device_id` (opcjonalny) — filtr na konkretne urządzenie,
- `sensor` (opcjonalny) — filtr na typ sensora (`temperature` / `pressure`),
- `limit` (opcjonalny, domyślnie 50) — maks. liczba rekordów w `/history`.

Powód osobnego typedefu: jeden punkt zmiany kontraktu — gdy API zyska
nowy parametr (np. `from` / `to`), edytuje się `kontrakt.ctl` i wszystkie
miejsca w `main.vi` automatycznie podchwytują pole.

### `template/main.vi`

Główny VI z front panelem (UI) i diagramem blokowym (logika). Cykl:

1. **Inicjalizacja** — `Create REST Client.vi` (JKI) tworzy obiekt
   klienta REST z `base URL = http://localhost:5001`.
2. **Pobieranie danych** — `HTTP GET.vi` woła endpoint (np. `/latest`
   lub `/history`) z parametrami z `kontrakt.ctl`. Odpowiedź to JSON.
3. **Parsowanie JSON** — JSON → tablica clustrów `measure_data.ctl`
   (przez `Unflatten From JSON` z natywnej biblioteki LabVIEW lub
   funkcję JKI).
4. **Konwersja czasu** — `ts_ms` (I64) → timestamp przez
   `epoch to cluster.vi`.
5. **Prezentacja** — wartości na wskaźnikach, tablica historii w
   *Table*, wykres trendu (XY Graph).
6. **Sprzątanie** — `Destroy REST Client.vi` przy zamykaniu VI.

## Uruchomienie

1. Backend musi działać:
   ```bash
   docker compose up -d
   curl http://localhost:5001/health        # {"status":"ok"}
   curl http://localhost:5001/latest        # niepusta tablica
   ```
2. Otwórz `labview/template/main.vi` w LabVIEW.
3. Jeśli pierwsze otwarcie po klonie repo — LabVIEW może zapytać
   o zależności (JKI REST Client). Jeśli brak, doinstaluj przez VIPM.
4. Uruchom (białą strzałką *Run*). Po kilku sekundach widoczne dane.

## Mapowanie endpointów na widoki

| Widok / akcja                       | Endpoint API                                |
|-------------------------------------|----------------------------------------------|
| Lista urządzeń (dropdown)           | `GET /devices`                               |
| Aktualne pomiary (kafelki)          | `GET /latest`                                |
| Aktualne pomiary danego urządzenia  | `GET /latest?device_id=...`                  |
| Tylko temperatura (ostatnia)        | `GET /latest/temperature`                    |
| Tylko ciśnienie (ostatnie)          | `GET /latest/pressure`                       |
| Wykres trendu temperatury           | `GET /history?sensor=temperature&limit=N`    |
| Filtr device + sensor + limit       | `GET /history?device_id=...&sensor=...&limit=...` |

## Format czasu — niuans

API zwraca `received_at` w dwóch wariantach:
- `/latest`: ISO 8601 z `T` jako separatorem (`2026-05-17T19:30:15.123456`),
- `/history`: format z separatorem spacji (`2026-05-17 19:30:15.123456`).

Parser w LabVIEW (`Scan From String`, format ISO 8601) powinien
akceptować oba — lub używać `ts_ms` (I64) jako głównego źródła czasu
i `received_at` tylko do wyświetlenia.

## Co warto dodać

- **Healthcheck przed wywołaniem** — wywołanie `/health` przy starcie VI,
  jasny komunikat błędu gdy backend nie działa.
- **Auto-refresh** — pętla *Timed Loop* z konfigurowalną częstotliwością
  (np. co 5 s), zatrzymywalna przyciskiem.
- **Obsługa pustej bazy** — `/latest` zwraca `[]` gdy brak pomiarów; UI
  powinien to pokazać sensownie zamiast pustego wykresu.
- **Wykres historii dla wybranego urządzenia** — kombinacja dropdownu
  z `/devices` i `/history?device_id=...`.
- **Eksport CSV** — zapis tabeli historii do pliku.
- **Konfigurowalny base URL** — kontrolka stringowa zamiast hardcoded
  `localhost:5001` (do podpięcia pod inny host w sieci lokalnej).
