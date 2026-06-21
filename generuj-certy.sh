#!/usr/bin/env bash
# =============================================================================
# Regeneracja certyfikatow TLS dla brokera MQTT (lab 10).
# Tworzy katalog certs/ z: openssl.cnf, ca.key, ca.crt, server.key,
# server.csr, server.crt — certyfikat serwera podpisany WLASNYM CA.
#
# Cert serwera jest PRZYPIETY do IP hosta (wpis SAN), poniewaz ESP32 laczy
# sie z brokerem po adresie IP. IP labu dryfuje (DHCP) — przy zmianie IP
# wystarczy uruchomic skrypt ponownie (CA zostaje, ESP nie wymaga reflashu).
#
# UZYCIE:
#   bash generuj-certy.sh <IP_HOSTA>
#   np.  bash generuj-certy.sh 156.17.45.169
#
# IP hosta z uruchomionym Dockerem sprawdzisz:
#   Windows : ipconfig  ->  Karta sieci bezprzewodowej Wi-Fi  ->  Adres IPv4
#   Linux/WSL: hostname -I
# =============================================================================
set -euo pipefail

IP="${1:-}"
if [ -z "$IP" ]; then
  echo "BLAD: podaj IP hosta, np.:  bash generuj-certy.sh 156.17.45.169" >&2
  exit 1
fi

# Git Bash (Windows) zamienia leading '/' w -subj na sciezke -> wylacz konwersje.
export MSYS_NO_PATHCONV=1

DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$DIR"
cd "$DIR"

echo "==> Zapisuje openssl.cnf (CN/SAN dla IP=$IP)"
cat > openssl.cnf <<EOF
[req]
distinguished_name = dn
req_extensions = v3_req
prompt = no

[dn]
C = PL
O = PWr Lab RSP
CN = $IP

[v3_ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash

[v3_req]
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

# IP wpisane ROWNIEZ jako DNS — celowe obejscie mbedTLS na ESP32
# (mbedTLS dopasowuje string hosta tylko do wpisow SAN typu DNS, nie IP).
[alt_names]
DNS.1 = localhost
DNS.2 = broker
DNS.3 = $IP
IP.1 = 127.0.0.1
IP.2 = $IP
EOF

# 1. CA — reuzyj jesli juz istnieje (zeby ca.crt w firmware ESP pozostal wazny)
if [ -f ca.key ] && [ -f ca.crt ]; then
  echo "==> CA juz istnieje — reuzywam ca.key/ca.crt (ESP nie wymaga reflashu)"
else
  echo "==> Generuje nowe CA: ca.key + ca.crt (waznosc 10 lat)"
  openssl genrsa -out ca.key 2048
  openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
    -subj "/C=PL/O=PWr Lab RSP/CN=RSP Lab Root CA" \
    -config openssl.cnf -extensions v3_ca
fi

# 2. Klucz prywatny + CSR serwera (brokera)
echo "==> Generuje server.key + server.csr (CN=$IP)"
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
  -subj "/C=PL/O=PWr Lab RSP/CN=$IP" \
  -config openssl.cnf

# 3. Podpisanie certyfikatu serwera przez CA (z rozszerzeniem SAN)
echo "==> Podpisuje server.crt przez CA (SAN: IP=$IP oraz DNS:$IP)"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 3650 -extfile openssl.cnf -extensions v3_req

echo ""
echo "GOTOWE. Pliki w: $DIR"
ls -1 ca.crt ca.key server.crt server.key server.csr openssl.cnf 2>/dev/null
echo ""
echo "Dalej:"
echo "  1) docker compose up --build     # broker wczyta certs/ (wolumen :ro)"
echo "  2) Weryfikacja TLS z hosta:"
echo "     openssl s_client -connect $IP:8883 -CAfile certs/ca.crt -verify_hostname $IP"
echo "     (oczekiwane: 'Verify return code: 0 (ok)')"
echo ""
echo "UWAGA: ca.crt jest wkompilowany w firmware ESP (esp32/src/main.cpp, CA_CERT)."
echo "Jesli wygenerowano NOWE CA, wklej nowy ca.crt do CA_CERT i wgraj firmware ponownie."
