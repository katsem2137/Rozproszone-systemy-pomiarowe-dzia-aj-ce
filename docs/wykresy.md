# Dashboard webowy (Streamlit)

Warstwa prezentacji danych w przeglądarce — katalog `wykresy_python/`. Konsumuje
REST API (Flask) i pokazuje aktualne pomiary, wykresy trendu oraz historię.

**Zastępuje LabVIEW jako główną warstwę prezentacji.** LabVIEW pozostaje w
repozytorium jako archiwum — patrz [labview.md](labview.md).

## Dlaczego Streamlit zamiast LabVIEW

- lekki dashboard w przeglądarce, bez licencji i ciężkiego IDE,
- ten sam kontrakt co LabVIEW: czyta **wyłącznie przez REST API**
  (`http://localhost:5001`), nie zna schematu bazy,
- auto-odświeżanie, filtr dat, eksport CSV „z pudełka",
- łatwo uruchomić na dowolnym komputerze (`pip install` + `streamlit run`).

## Struktura

```
wykresy_python/
├── app.py            # aplikacja Streamlit (UI, wykresy, tabela)
├── api_client.py     # klient REST API (APIClient + APIError)
├── config.py         # ustawienia domyślne (URL, limity, timeouty)
└── requirements.txt  # streamlit, pandas, plotly, requests, streamlit-autorefresh
```

## Komponenty

### `config.py` — ustawienia domyślne

| Stała | Wartość | Znaczenie |
|-------|---------|-----------|
| `DEFAULT_BASE_URL` | `http://localhost:5001` | adres backendu (API) |
| `DEFAULT_HISTORY_LIMIT` | `50` | domyślny limit historii |
| `DEFAULT_REFRESH_INTERVAL` | `10` s | interwał auto-odświeżania |
| `REQUEST_TIMEOUT` | `5` s | timeout żądań HTTP |

### `api_client.py` — `APIClient`

Owija REST API w metody: `health()`, `devices()`, `latest()`,
`latest_temperature()`, `latest_pressure()`, `history(device_id, sensor, limit)`.
Korzysta z `requests.Session`. Błędy sieci (brak połączenia, timeout, HTTP)
zamienia na wyjątek `APIError` z czytelnym komunikatem — dzięki temu UI pokazuje
sensowny błąd zamiast crashować.

### `app.py` — aplikacja Streamlit

Pasek boczny + trzy sekcje:

- **Pasek boczny** (`sidebar`): pole Base URL backendu, wskaźnik **online/offline**
  (z `/health`), suwak interwału odświeżania (5–60 s), suwak limitu historii
  (10–500), wybór urządzenia (`Wszystkie` / konkretne), **zakres dat** (domyślnie
  ostatnia doba), przycisk „Odśwież teraz".
- **Aktualne pomiary** (`section_current`): kafelki `st.metric` z ostatnią
  temperaturą i ciśnieniem per urządzenie.
- **Wykresy trendu** (`section_charts`): dwa wykresy Plotly (temperatura,
  ciśnienie) — linie **spline** z markerami, oś czasu, oś Y ze **stałym krokiem**
  (`dtick` = 0.5 °C / 1.0 hPa) i dopasowanym zakresem, z filtrem po dacie.
- **Historia pomiarów** (`section_history`): tabela `st.dataframe` + przycisk
  **eksportu CSV**.

Całość odświeża się automatycznie co wybrany interwał (`st_autorefresh`).

## Uruchomienie

Dashboard działa **poza Dockerem** — jest klientem REST API i nie wchodzi
do sieci kontenerów. Wystarczy dostęp do portu `5001`.

### Wymagania

- Python 3.10 lub nowszy (`python --version`)
- Działający backend: `docker compose up -d` w głównym katalogu repo

### Krok po kroku

**1. Uruchom backend (jeśli jeszcze nie działa)**

```bash
# w głównym katalogu repo
docker compose up -d
```

Sprawdź, czy API odpowiada:

```bash
curl http://localhost:5001/health
# oczekiwana odpowiedź: {"status": "ok"}
```

**2. Przejdź do katalogu dashboardu**

```bash
cd wykresy_python
```

**3. (Zalecane) Utwórz wirtualne środowisko**

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

**4. Zainstaluj zależności** (tylko przy pierwszym uruchomieniu)

```bash
pip install -r requirements.txt
```

**5. Uruchom dashboard**

```bash
python -m streamlit run app.py
```

> Na niektórych systemach komenda `streamlit` może nie być w PATH — `python -m streamlit` działa zawsze.

Przeglądarka otworzy się automatycznie pod adresem `http://localhost:8501`.
W pasku bocznym powinien być widoczny komunikat **Backend: online ✓**.

### Zmiana adresu backendu

Jeśli API działa pod innym adresem (np. zdalny serwer), wpisz go w polu
**Base URL backendu** w pasku bocznym — bez restartu aplikacji.

### Wyłączenie dashboardu

W terminalu, w którym działa Streamlit: `Ctrl+C`.

### Typowe problemy

| Objaw | Przyczyna | Rozwiązanie |
|-------|-----------|-------------|
| Backend: offline ✗ | Docker nie działa | `docker compose up -d` |
| `ModuleNotFoundError` | Brak zależności | `pip install -r requirements.txt` |
| Port 8501 zajęty | Inna instancja Streamlit | `streamlit run app.py --server.port 8502` |
| Brak danych na wykresach | ESP32 nie nadaje / baza pusta | Sprawdź `docker logs ingestor` |

## Mapowanie widoków na endpointy API

| Widok | Endpoint |
|-------|----------|
| status backendu (online/offline) | `GET /health` |
| lista urządzeń (dropdown) | `GET /devices` |
| aktualne pomiary (kafelki) | `GET /latest/temperature`, `GET /latest/pressure` |
| wykresy trendu | `GET /history?sensor=...&limit=...` |
| historia + eksport CSV | `GET /history?limit=...` |

## Powiązania z innymi dokumentami

- [api.md](api.md) — endpointy REST konsumowane przez dashboard.
- [architektura.md](architektura.md) — miejsce warstwy prezentacji w przepływie.
- [labview.md](labview.md) — poprzednia warstwa prezentacji (archiwum).
