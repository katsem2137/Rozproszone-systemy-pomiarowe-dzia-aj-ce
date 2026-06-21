# Dokumentacja projektu

Rozproszony system pomiarowy: ESP32 + BMP280 → MQTT → ingestor →
PostgreSQL → Flask REST API → dashboard webowy (Streamlit).

## Spis treści

| Plik                                           | Opis                                                          |
|------------------------------------------------|---------------------------------------------------------------|
| [architektura.md](architektura.md)             | Przegląd warstw, przepływ danych, decyzje architektoniczne    |
| [uruchomienie.md](uruchomienie.md)             | Wymagania, start Docker Compose, konfiguracja, problemy       |
| [esp32.md](esp32.md)                           | Firmware ESP32 — sprzęt, kod, build, flash                    |
| [message_contract.md](message_contract.md)     | Kontrakt MQTT — topiki, payload JSON, walidacja               |
| [ingestor.md](ingestor.md)                     | Serwis MQTT → PostgreSQL                                      |
| [baza.md](baza.md)                             | Schemat PostgreSQL, przykładowe zapytania                     |
| [api.md](api.md)                               | REST API — endpointy, parametry, przykłady                    |
| [wykresy.md](wykresy.md)                       | Dashboard webowy (Streamlit) — aktualna warstwa prezentacji   |
| [labview.md](labview.md)                       | LabVIEW UI — **archiwum** (zastąpione przez Streamlit)        |
| [reliability_esp32.md](reliability_esp32.md)   | Niezawodność ESP32 — reconnect Wi-Fi/MQTT, status, LWT        |
| [security_tls.md](security_tls.md)             | Bezpieczeństwo — TLS na MQTT (8883), własne CA, izolacja usług |
| [basic_auth.md](basic_auth.md)             | Uwierzytelnianie REST API — HTTP Basic Auth (lab 11)          |

## Wersja do druku

Cała dokumentacja zlepiona w jeden plik: [`DOKUMENTACJA.md`](../DOKUMENTACJA.md)
(w katalogu głównym repo).

## Status implementacji

| Lab | Temat                          | Status                                  |
|-----|--------------------------------|----------------------------------------|
| 0   | Architektura, narzędzia        | Gotowe                                  |
| 1   | Onboarding, Docker, WSL        | Gotowe                                  |
| 2   | ESP32 dummy + Wi-Fi            | Pominięte — od razu BMP280              |
| 3   | ESP32 + MQTT publish           | Gotowe                                  |
| 4   | Kontrakt danych                | Gotowe                                  |
| 5   | Ingestor MQTT → DB             | Gotowe                                  |
| 6   | REST API                       | Gotowe                                  |
| 7-8 | Prezentacja danych             | Streamlit (`wykresy_python/`); LabVIEW w archiwum |
| 9   | Niezawodność ESP32 (reconnect, LWT) | Zrobione (`docs/reliability_esp32.md`) |
| 10  | Security MQTT — TLS, izolacja usług | Zrobione (`docs/security_tls.md`)   |
| 11  | Bezpieczeństwo API — HTTP Basic Auth | Zrobione (`api/auth.py`, `docs/basic_auth.md`) |
