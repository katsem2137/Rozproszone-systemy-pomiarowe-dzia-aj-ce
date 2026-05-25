# Bezpieczeństwo komunikacji — TLS na MQTT (lab 10)

Opis wdrożenia szyfrowanej i uwierzytelnionej komunikacji MQTT (TLS) między
ESP32 a brokerem Mosquitto, wraz z izolacją usług w Dockerze.

## Cel

Punktem wyjścia był broker MQTT bez zabezpieczeń: nasłuch na porcie `1883`,
ruch w postaci jawnej (plaintext), `allow_anonymous true`, brak weryfikacji
tożsamości stron. W takiej konfiguracji:

- dane pomiarowe można podsłuchać (sniffing w sieci Wi-Fi),
- można je zmodyfikować w locie (brak integralności),
- klient nie ma pewności, że łączy się z właściwym brokerem (ryzyko
  man-in-the-middle).

TLS (Transport Layer Security) usuwa te problemy: szyfruje kanał, gwarantuje
integralność i — dzięki certyfikatowi CA — pozwala klientowi **zweryfikować
tożsamość brokera**.

## Model bezpieczeństwa — TLS na granicy zaufania

Zamiast wymuszać TLS na całej komunikacji, szyfrowanie zastosowano **na granicy
zaufania**: tam, gdzie ruch realnie opuszcza maszynę i wchodzi do sieci Wi-Fi.

```
                      granica zaufania (LAN)
                              │
   ESP32  ──── MQTT/TLS ──────┼──────►  broker (Mosquitto)
          (port 8883, szyfr.) │            │
                              │            │  MQTT plaintext 1883
                              │            │  (tylko w sieci 'backend')
                              │            ▼
                              │         ingestor ──SQL──► postgres
                              │                              │
                              │                              ▼
                              │                       Flask API (5001)
            sieć Docker 'backend' (bridge, izolowana)
```

| Połączenie | Port | Szyfrowanie | Uzasadnienie |
|------------|------|-------------|--------------|
| ESP32 → broker | 8883 | **TLS** | ruch idzie przez sieć Wi-Fi LAN — realne ryzyko podsłuchu |
| ingestor → broker | 1883 | brak | ruch nie opuszcza izolowanej sieci kontenerów Docker |
| api → postgres | 5432 | brak | jw. — wewnątrz sieci `backend`, port nieeksponowany na hosta |

Dzięki temu ingestor (klient w Pythonie) działa bez zmian, a mimo to cała
komunikacja przekraczająca granicę maszyny jest zaszyfrowana. Rozwiązanie jest
spójne z izolacją usług opisaną niżej.

**Rozważona alternatywa — pełny TLS** (broker nasłuchuje tylko na 8883, ingestor
też przez TLS): bliższa dosłownej treści instrukcji, ale wymaga przerobienia
ingestora i wprowadza więcej punktów awarii. Pozostawiona jako możliwy kierunek
rozwoju (patrz [Ograniczenia i co dalej](#ograniczenia-i-co-dalej)).

## Własny urząd certyfikacji (CA) i certyfikat serwera

W projekcie użyto **własnego CA** do podpisania certyfikatu brokera. Daje to
pełną kontrolę nad zaufaniem i symuluje infrastrukturę PKI bez zewnętrznego
dostawcy certyfikatów.

### Wygenerowane pliki (`certs/`)

| Plik | Rola | Tajny? |
|------|------|--------|
| `ca.key` | klucz prywatny CA | **tak** — nigdy nie udostępniać |
| `ca.crt` | certyfikat CA (publiczny) | nie — trafia do klientów |
| `server.key` | klucz prywatny brokera | **tak** |
| `server.csr` | żądanie podpisania certyfikatu | — |
| `server.crt` | certyfikat brokera podpisany przez CA | nie |
| `openssl.cnf` | konfiguracja (subject + SAN) | nie |

Katalog `certs/` jest w `.gitignore` — **klucze prywatne nie trafiają do
repozytorium**. Publiczny `ca.crt` jest dodatkowo wkompilowany w firmware ESP32.

### Komendy generujące

> Uwaga (Windows / Git Bash): leading `/` w `-subj` bywa zamieniany na ścieżkę
> Windows. Jeśli `openssl req` zgłasza błąd subjectu, ustaw `export
> MSYS_NO_PATHCONV=1` przed komendami.

```bash
cd certs

# 1. CA — klucz + samopodpisany certyfikat (10 lat)
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "/C=PL/O=PWr Lab RSP/CN=RSP Lab Root CA" \
  -config openssl.cnf -extensions v3_ca

# 2. Serwer (broker) — klucz + CSR
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
  -subj "/C=PL/O=PWr Lab RSP/CN=156.17.45.51" \
  -config openssl.cnf

# 3. Podpisanie certyfikatu serwera przez CA (z rozszerzeniem SAN)
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 3650 -extfile openssl.cnf -extensions v3_req
```

### Subject Alternative Name (SAN)

Certyfikat serwera obejmuje nazwy, pod którymi broker bywa adresowany:

```
DNS:localhost, DNS:broker, DNS:156.17.45.51, IP Address:127.0.0.1, IP Address:156.17.45.51
```

`156.17.45.51` to adres IP komputera z Dockerem w sieci Wi-Fi laboratorium —
po nim łączy się ESP32. **IP jest wpisane zarówno jako `IP`, jak i jako `DNS`** —
to celowe obejście ograniczenia mbedTLS na ESP32 (szczegóły w sekcji
[Napotkane problemy](#napotkane-problemy-i-rozwiązania)).

## Konfiguracja brokera (Mosquitto)

`broker/mosquitto.conf` — dwa listenery:

```conf
persistence true
persistence_location /mosquitto/data/
log_dest stdout

# Ustawione PRZED listenerami => globalne dla obu
allow_anonymous true

# Listener wewnętrzny (plaintext) — tylko dla usług w sieci Docker (ingestor)
listener 1883

# Listener TLS — dla ESP32 i klientów zewnętrznych
listener 8883
cafile   /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile  /mosquitto/certs/server.key
```

Certyfikaty są **montowane** do kontenera (wolumen `:ro`), a nie kopiowane do
obrazu — dzięki temu klucz prywatny serwera nie ląduje w warstwach obrazu
Dockera. `require_certificate` pozostaje domyślnie `false`: klient weryfikuje
brokera, ale broker nie wymaga certyfikatu klienta (uwierzytelnianie
jednostronne).

## Izolacja usług (docker-compose)

W ramach lab 10 wzmocniono też izolację środowiska Docker:

```yaml
services:
  flask:
    ports: ["5001:5001"]      # API publiczne — jedyny port aplikacyjny na hoście
    networks: [backend]
  broker:
    ports: ["8883:8883"]      # tylko TLS wystawiony na hosta (1883 zostaje wewnątrz)
    volumes: ["./certs:/mosquitto/certs:ro"]
    networks: [backend]
  database:
    # brak mapowania portu 5432 — baza nieosiągalna z hosta
    networks: [backend]
  ingestor:
    networks: [backend]
networks:
  backend:
    driver: bridge
```

Efekty bezpieczeństwa:

- **baza danych nie jest dostępna z hosta** (usunięto `5432:5432`),
- **broker przyjmuje połączenia z zewnątrz wyłącznie po TLS** (`8883`); port
  `1883` istnieje tylko wewnątrz sieci `backend`,
- usługi komunikują się w dedykowanej sieci bridge, odseparowane od sieci
  zewnętrznej.

## Klient ESP32 (TLS)

Zmiany w `esp32/src/main.cpp` (reszta logiki z lab 9 — reconnect, status, LWT —
bez zmian; szyfrowany jest jedynie transport):

```cpp
#include <WiFiClientSecure.h>

// Certyfikat CA (publiczny) — odpowiada certs/ca.crt
static const char* CA_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
... (treść ca.crt) ...
-----END CERTIFICATE-----
)EOF";

WiFiClientSecure espClient;          // zamiast WiFiClient
PubSubClient mqttClient(espClient);

void setup() {
    // ...
    espClient.setCACert(CA_CERT);              // weryfikacja tożsamości brokera
    mqttClient.setServer(MQTT_HOST, MQTT_PORT); // MQTT_PORT = 8883 (secrets.h)
}
```

**Zależność od zegara:** TLS sprawdza daty ważności certyfikatu, więc ESP musi
mieć ustawiony czas. Realizuje to `syncNTP()` w `setup()` (z lab wcześniejszych).
Bez synchronizacji NTP weryfikacja certyfikatu może się nie powieść.

## Testy i weryfikacja

Wszystkie testy wykonane na działającym systemie; wyniki rzeczywiste.

### T1 — handshake TLS z weryfikacją CA (pozytywny)

```bash
openssl s_client -connect 156.17.45.51:8883 -CAfile certs/ca.crt -verify_ip 156.17.45.51
# subject=C=PL, O=PWr Lab RSP, CN=156.17.45.51
# issuer=C=PL, O=PWr Lab RSP, CN=RSP Lab Root CA
# Verify return code: 0 (ok)
```

### T2 — handshake bez CA (kontrola negatywna)

```bash
openssl s_client -connect 156.17.45.51:8883       # bez -CAfile
# Verify return code: 19 (self-signed certificate in certificate chain)
```

Bez certyfikatu CA klient **nie ufa** certyfikatowi brokera — dowód, że
weryfikacja faktycznie działa (nie akceptuje dowolnego certyfikatu).

### T3 — publikacja po TLS

```bash
docker exec broker mosquitto_pub -h localhost -p 8883 \
  --cafile /mosquitto/certs/ca.crt -t test/tls -m "TLS dziala poprawnie"
# exit 0  → publikacja po zaszyfrowanym kanale powiodła się
```

### T4 — plaintext na porcie TLS (kontrola negatywna)

Próba połączenia bez TLS na port `8883` jest odrzucana przez brokera:

```
OpenSSL Error ... error:0A00010B:SSL routines::wrong version number
Client ... disconnected: Protocol error. (First packet not CONNECT)
```

Potwierdza, że listener `8883` wymusza TLS i odrzuca ruch jawny.

### T5 — ESP32 łączy się po TLS

Log brokera po wgraniu firmware:

```
New client connected from 172.20.0.1 as esp32-EC0EAD004F8C (p4, c1, k15) on port 8883
```

Połączenie na **porcie 8883** = urządzenie używa TLS.

### T6 — test end-to-end (ESP → TLS → broker → ingestor → baza → API)

```bash
curl http://localhost:5001/latest/temperature
# {"device_id":"esp32-EC0EAD004F8C","sensor":"temperature","value":24.9,"unit":"C", ...}
curl http://localhost:5001/latest/pressure
# {"device_id":"esp32-EC0EAD004F8C","sensor":"pressure","value":1015.25,"unit":"hPa", ...}
```

Świeże dane w API = cały łańcuch działa po wdrożeniu TLS.

## Napotkane problemy i rozwiązania

### mbedTLS na ESP32 nie dopasowuje IP w SAN

**Objaw:** po pierwszym wgraniu firmware (`setCACert` + cert z SAN `IP:156.17.45.51`)
ESP łączył się po TCP/TLS, ale handshake kończył się błędem:

```
(-9984) X509 - Certificate verification failed
```

mimo że z hosta `openssl s_client -verify_ip` weryfikował ten sam certyfikat
poprawnie (`Verify return code: 0`).

**Przyczyna:** ESP łączy się po **adresie IP**. Biblioteka mbedTLS (stos TLS na
ESP32) porównuje string hosta podany do połączenia wyłącznie z wpisami SAN typu
**DNS**, a nie z wpisami typu **IP**. OpenSSL (inna implementacja) potrafi
dopasować IP-SAN, dlatego test z hosta przechodził, a ESP — nie.

**Rozwiązanie:** dopisanie adresu IP **również jako wpisu SAN typu DNS**
(`DNS:156.17.45.51` obok `IP:156.17.45.51`). Wtedy porównanie po stringu
przechodzi i pełna weryfikacja certyfikatu zostaje zachowana.

Co istotne — wymaga to jedynie **przepisania certyfikatu serwera** (tym samym
CA) i restartu brokera. CA się nie zmienia, więc **firmware ESP32 nie wymaga
ponownego wgrania**:

```bash
# po edycji certs/openssl.cnf (dodanie DNS.3 = <IP>):
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 3650 -extfile openssl.cnf -extensions v3_req
docker compose restart broker
# weryfikacja jak po stronie mbedTLS (dopasowanie po stringu/DNS):
openssl s_client -connect 156.17.45.51:8883 -CAfile certs/ca.crt -verify_hostname 156.17.45.51
# Verify return code: 0 (ok)
```

**Odrzucone alternatywy:**
- `espClient.setInsecure()` — wyłącza weryfikację (szyfrowanie bez
  uwierzytelnienia brokera). Sprzeczne z celem lab.
- Łączenie po nazwie DNS zamiast IP — w sieci laboratorium brak DNS
  rozwiązującego nazwę brokera.

## Ograniczenia i co dalej

- **Self-signed CA** — zaufanie lokalne (nie globalny urząd certyfikacji). Dla
  systemu laboratoryjnego / przemysłowego zamkniętego jest to akceptowalne.
- **IP w certyfikacie** — zmiana adresu IP hosta wymaga przepisania
  `server.crt` (CA pozostaje). Patrz procedura wyżej.
- **Broker anonimowy** — uwierzytelnianie jest jednostronne (klient weryfikuje
  brokera, broker nie weryfikuje klienta). Naturalny następny krok:
  - **mutual TLS** — certyfikat klienta po stronie ESP32 (`require_certificate true`),
  - lub **login/hasło + ACL** (`password_file`, `acl_file`).
- **Plaintext 1883 wewnątrz sieci Docker** — do pełnego TLS należałoby przerobić
  również ingestor na połączenie szyfrowane.

## Powiązania z innymi dokumentami

- [architektura.md](architektura.md) — miejsce TLS w przepływie danych.
- [esp32.md](esp32.md) — ogólny opis firmware.
- [reliability_esp32.md](reliability_esp32.md) — niezawodność (lab 9); logika
  reconnect/LWT działa pod TLS bez zmian.
- [uruchomienie.md](uruchomienie.md) — start środowiska (port `8883`).
