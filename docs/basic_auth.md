# Basic Auth dla REST API (lab 11)

Warstwa Flask REST API jest zabezpieczona mechanizmem **HTTP Basic Authentication**.
Endpoint diagnostyczny `/health` pozostaje publiczny; wszystkie endpointy zwracające
dane wymagają poprawnego loginu i hasła.

## Chronione endpointy

| Endpoint | Dostęp | Uwagi |
|----------|--------|-------|
| `GET /health` | publiczny | healthcheck |
| `GET /` | publiczny | "Hello World", brak danych |
| `GET /devices` | chroniony | lista urządzeń |
| `GET /latest` | chroniony | najnowsze odczyty (filtr świeżości) |
| `GET /latest/temperature` | chroniony | najnowsza temperatura |
| `GET /latest/pressure` | chroniony | najnowsze ciśnienie |
| `GET /history` | chroniony | historia pomiarów |

Brak nagłówka `Authorization` lub błędne dane → `401 Unauthorized` + nagłówek
`WWW-Authenticate: Basic realm="RSP API"`.

## Konfiguracja loginu i hasła

Dane logowania pochodzą ze **zmiennych środowiskowych** (nie z kodu). Plik `.env`
jest w `.gitignore`:

```
API_USERNAME=student
API_PASSWORD=student
```

Usługa `flask` w `docker-compose.yml` wczytuje je przez `env_file: .env`.
Zmiana hasła: edytuj `.env`, a następnie `docker compose up -d --build flask`.

Implementacja: `api/auth.py` — dekorator `@auth_required` nałożony pod `@app.route(...)`;
porównanie poświadczeń przez `secrets.compare_digest` (odporność na timing attack).
Hasło nie jest wypisywane w logach.

## Testy curl

```bash
# publiczny — 200 bez logowania
curl -i http://localhost:5001/health

# chroniony bez danych — 401 + WWW-Authenticate
curl -i http://localhost:5001/devices

# chroniony z błędnym hasłem — 401
curl -i -u student:zle http://localhost:5001/devices

# chroniony z poprawnym hasłem — 200 + JSON
curl -i -u student:student http://localhost:5001/devices

# historia z Basic Auth (Windows: adres w cudzysłowie)
curl -i -u student:student "http://localhost:5001/history?device_id=esp32-EC0EAD004F8C&sensor=temperature&limit=5"
```

## Klient (dashboard Streamlit) — odpowiednik „Części D / LabVIEW"

W tym projekcie warstwą prezentacji jest dashboard **Streamlit** (`wykresy_python/`),
a nie LabVIEW (zarchiwizowany w `ui/`). Część D instrukcji zrealizowano w dashboardzie:

- panel boczny: checkbox **Użyj Basic Auth**, pola **Login** i **Hasło**
  (hasło maskowane, `type="password"`),
- klient `api_client.py` wysyła `Authorization: Basic ...` (parametr `auth=` w `requests`),
- obsługa `401`: czytelny komunikat „błędny login lub hasło", bez nadpisywania
  wykresu pustymi danymi; w panelu bocznym wskaźnik statusu autoryzacji
  (`Autoryzacja: OK ✓` / `401`).

Uruchomienie dashboardu:

```
streamlit run wykresy_python/app.py
```

## Ograniczenia Basic Auth

- login i hasło są wysyłane przy **każdym** żądaniu; Base64 to kodowanie, nie szyfrowanie,
- mechanizm jest bezpieczny tylko po **TLS/HTTPS** — bez tego dane logowania można podsłuchać,
- brak ról, wygasania sesji i rotacji haseł — wymagałyby osobnej logiki,
- kierunek docelowy: tokeny Bearer/JWT, OAuth2/OIDC, mTLS albo API Gateway (poza zakresem lab).
