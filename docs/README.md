# Dokumentacja projektu

Rozproszony system pomiarowy: ESP32 + BMP280 → MQTT → ingestor →
PostgreSQL → Flask REST API → (LabVIEW UI).

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
| [labview.md](labview.md)                       | LabVIEW UI — VI, typedefy, JKI REST Client, uruchomienie      |

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
| 7-8 | LabVIEW UI                     | Zrobione                                |
| 9+  | Niezawodność, security         | Nie zaczęte                             |
