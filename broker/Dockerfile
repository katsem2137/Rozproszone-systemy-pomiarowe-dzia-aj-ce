# Krok 1: Wybierz obraz bazowy.
FROM eclipse-mosquitto:latest

# Krok 2: Skopiuj nasz plik konfiguracyjny.
COPY mosquitto.conf /mosquitto/config/mosquitto.conf

# Twórcy obrazu eclipse-mosquitto 
# już zdefiniowali w swoim Dockerfile komende startowa: 
# CMD ["/usr/sbin/mosquitto", "-c", "/mosquitto/config/mosquitto.conf"] 
# (To jest komenda, która fizycznie uruchamia serwer brokera).

EXPOSE 1883 8883
