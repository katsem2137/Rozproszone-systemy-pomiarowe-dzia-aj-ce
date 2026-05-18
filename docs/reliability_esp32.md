# Niezawodność po stronie ESP32

Opis mechanizmów zwiększających niezawodność firmware ESP32 dodanych
w ramach laboratorium 9: reconnect Wi-Fi, reconnect MQTT, topic statusowy,
Last Will and Testament.

## Cel

W poprzedniej wersji firmware funkcje `connectWiFi()` i `connectMQTT()`
zawierały blokujące pętle `while`, które zatrzymywały `loop()` na czas
nawiązywania połączenia. Skutki:

- Utrata Wi-Fi w runtime → urządzenie zawisa w `connectWiFi()` bez
  feedbacku.
- Utrata MQTT → `delay(2000)` w pętli reconnect blokował publikację.
- Brak informacji o stanie urządzenia z punktu widzenia brokera — gdy
  ESP zniknie (reset, odłączone zasilanie), broker nie wie o tym.

Nowa wersja jest **non-blocking**: `loop()` wykonuje wszystkie sprawdzenia
i próby reconnect przez harmonogram na bazie `millis()`, bez blokujących
oczekiwań.

## Topic statusowy

```
lab/<group_id>/<device_id>/status
```

Przykład: `lab/g01/esp32-F88DAB004F8C/status`

Topic jest **techniczny**, oddzielony od topiców pomiarowych
(`temperature`, `pressure`). Dzięki rozdzieleniu warstwa pomiarowa
i diagnostyczna nie mieszają się — łatwiej filtrować w MQTT Explorer
i łatwiej dodać po stronie backendu osobnego subskrybenta dla statusu.

### Payload `online`

Publikowany **z flagą retained** natychmiast po udanym `mqttClient.connect()`:

```json
{
  "device_id": "esp32-F88DAB004F8C",
  "status": "online",
  "ts_ms": 1742030400000
}
```

Retained ⇒ nowy subskrybent (MQTT Explorer, kolejny backend) od razu
widzi ostatni znany stan urządzenia bez czekania na kolejny komunikat.

### Payload `offline` (Last Will)

Deklarowany przez klienta podczas `mqttClient.connect()` i publikowany
**przez brokera** w imieniu klienta wtedy, gdy klient zniknie niepoprawnie
(reset, odłączone zasilanie, zerwana sesja TCP):

```json
{
  "device_id": "esp32-F88DAB004F8C",
  "status": "offline"
}
```

Brak `ts_ms` — broker publikuje LWT po wykryciu rozłączenia, więc znacznik
czasu z momentu connect byłby mylący.

LWT również retained ⇒ nowy subskrybent zobaczy `offline`, jeśli urządzenie
jest aktualnie odłączone.

## Mechanizm reconnect Wi-Fi

```c
const unsigned long WIFI_RETRY_MS = 5000;
unsigned long lastWifiAttemptMs   = 0;

void connectWiFiIfNeeded() {
    if (WiFi.status() == WL_CONNECTED) return;
    if (millis() - lastWifiAttemptMs < WIFI_RETRY_MS) return;
    lastWifiAttemptMs = millis();

    WiFi.disconnect();
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}
```

- Sprawdza `WiFi.status()` w każdej iteracji `loop()`.
- Ponowna próba `WiFi.begin(...)` **maks. raz na 5 s** (chroni przed
  spamowaniem stack-a sieciowego).
- Brak blokującego `while` — `loop()` natychmiast wraca i może obsłużyć
  inne rzeczy (np. ponowny test stanu MQTT w następnej iteracji).

## Mechanizm reconnect MQTT

```c
const unsigned long MQTT_RETRY_MS = 3000;
unsigned long lastMqttAttemptMs   = 0;

bool connectMqttIfNeeded() {
    if (WiFi.status() != WL_CONNECTED) return false;
    if (mqttClient.connected()) return true;
    if (millis() - lastMqttAttemptMs < MQTT_RETRY_MS) return false;
    lastMqttAttemptMs = millis();

    String willPayload =
        "{\"device_id\":\"" + deviceId + "\",\"status\":\"offline\"}";

    bool ok = mqttClient.connect(
        deviceId.c_str(),
        topicStatus.c_str(),    // willTopic
        0,                      // willQos
        true,                   // willRetain
        willPayload.c_str()     // willMessage
    );

    if (ok) {
        publishStatus("online");
    }
    return ok;
}
```

- Pre-warunek: Wi-Fi UP. Bez sieci nie ma sensu próbować łączyć MQTT.
- Retry maks. raz na 3 s.
- `connect()` z LWT — broker zarejestruje wiadomość offline.
- Po sukcesie natychmiastowa publikacja statusu `online`.

## Pętla główna

```c
void loop() {
    connectWiFiIfNeeded();
    connectMqttIfNeeded();
    mqttClient.loop();          // keepalive klienta MQTT

    // (runtime retry BMP280 jezeli niedostepny)

    if (millis() - lastMeasurementMs >= MEASUREMENT_PERIOD_MS) {
        lastMeasurementMs = millis();
        publishMeasurement();
    }

    delay(10);  // oddaj czas stackom sieciowym
}
```

`delay(10)` to nie blokada logiki — to standardowa pauza FreeRTOS dla
oddania czasu CPU stackom Wi-Fi/MQTT. Cała logika reconnect i publikacja
nadal działa bez czekania na cokolwiek.

## Scenariusze testowe

### Test 1: Utrata Wi-Fi w runtime

**Kroki**:
1. ESP uruchomione, publikuje pomiary, status `online` widoczny w MQTT Explorer.
2. Wyłącz Wi-Fi w punkcie dostępowym (lub przenieś ESP poza zasięg).
3. Obserwuj UART (115200 baud).

**Oczekiwane**:
- Po chwili na UART: `[WiFi] Brak polaczenia - probuje reconnect...` co 5 s.
- Brak nowych pomiarów na topicu `temperature` / `pressure`.
- Broker wykrywa rozłączenie i publikuje LWT `offline` na `lab/.../status`
  (czas wykrycia zależy od keepalive MQTT, domyślnie ~15 s w PubSubClient).
- Po przywróceniu Wi-Fi: log `[WiFi] OK`, potem `[MQTT] Probuje polaczyc... OK`,
  potem `[STATUS] {"device_id":..., "status":"online", ...}`.
- Pomiary wracają.

### Test 2: Niedostępny broker MQTT

**Kroki**:
1. ESP uruchomione, publikacja działa.
2. Zatrzymaj kontener brokera: `docker stop broker`.
3. Obserwuj UART.

**Oczekiwane**:
- Na UART: `[MQTT] Probuje polaczyc... blad, rc=-2` co 3 s
  (rc=-2 = connection failed).
- Wi-Fi nadal UP (urządzenie nie reagaby się rozłączać tylko dlatego, że
  broker padł).
- Brak nowych pomiarów (publikacja sprawdza `mqttClient.connected()`).
- Po `docker start broker`: udane reconnect, status `online`, pomiary
  wracają.

### Test 3: Last Will (nieczyste rozłączenie)

**Kroki**:
1. W MQTT Explorer subskrybuj `lab/+/+/status` (lub konkretny topic).
2. ESP połączone, widoczny `online` (retained).
3. Odłącz zasilanie ESP **bez** czystego `disconnect`.
4. Czekaj na keepalive MQTT (~15 s przy domyślnych ustawieniach PubSubClient).

**Oczekiwane**:
- Po wygaśnięciu keepalive na topicu statusowym pojawia się
  `{"device_id":..., "status":"offline"}` opublikowany przez brokera.
- Komunikat jest retained — pozostaje na topicu do czasu kolejnego
  `online` lub ręcznego wyczyszczenia.

### Test 4: Powrót do publikacji po awarii

**Kroki**:
1. Wykonaj Test 1 lub Test 2.
2. Przywróć warunki pracy (Wi-Fi / broker).
3. Sprawdź w MQTT Explorer topici `temperature`, `pressure`, `status`.

**Oczekiwane**:
- Status: `online`.
- Pomiary lecą co 5 s.
- `seq` w pomiarach kontynuuje (nie resetuje się do 0 — bo nie było
  restartu ESP).

## Co dalej (opcjonalne rozszerzenia z instrukcji)

- **Status `reconnecting`** — publikowany przed kolejną próbą reconnect
  MQTT, daje precyzyjniejszy obraz stanu.
- **Rozróżnienie błędów** — payload statusowy z polem `reason`
  (`wifi_down`, `mqtt_down`, `broker_unreachable`).
- **Backoff** — rosnące opóźnienia między próbami (5s → 10s → 20s...)
  zamiast stałych 5s/3s, redukuje obciążenie sieci przy długiej awarii.
- **Licznik nieudanych prób** — dodać do payloadu, można obserwować
  stabilność z poziomu UI.
- **Pole `status` w bazie / API** — backend rejestruje historię stanów
  (osobna tabela `device_status`), API endpoint `/devices/status`,
  LabVIEW UI pokazuje status każdego urządzenia.

## Powiązania z innymi dokumentami

- [esp32.md](esp32.md) — ogólny opis firmware i hardware.
- [message_contract.md](message_contract.md) — kontrakt pomiarów MQTT
  (status to topic techniczny, ma uproszczony payload).
- [architektura.md](architektura.md) — miejsce ESP32 w przepływie.
