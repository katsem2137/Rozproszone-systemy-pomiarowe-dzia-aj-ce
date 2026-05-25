# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Distributed measurement system (IoT → MQTT → Python → PostgreSQL → REST API → LabVIEW). A university lab project built incrementally across labs 0–13 (labs 0–8 completed).

## Running the System

```bash
# Build and start all backend services (broker, database, ingestor, api)
docker compose up --build

# Run in background
docker compose up -d --build

# Stop (use -v to also drop the database volume)
docker compose down
```

ESP32 firmware is built and uploaded via **PlatformIO** in VS Code (not Docker). Serial monitor at 115200 baud. Upload port is COM3 at 460800 baud (`esp32/platformio.ini`).

## API Endpoints (port 5001)

```
GET /health
GET /devices
GET /latest                        # latest reading per device/sensor
GET /latest?device_id=<id>
GET /latest/temperature
GET /latest/pressure
GET /history?device_id=...&sensor=...&limit=...
```

## Architecture & Data Flow

```
ESP32 + BMP280 (I2C GPIO 21/22)
  → MQTT/TLS publish → Mosquitto broker (8883 TLS, 1883 internal-only)
  → Ingestor subscribes to lab/+/+/+ → INSERT into PostgreSQL (port 5432)
  → Flask REST API (port 5001) SELECT → LabVIEW desktop client
```

**MQTT topic pattern:** `lab/<group_id>/<device_id>/<sensor>`

**Required JSON fields in payload:** `device_id`, `sensor`, `value`, `ts_ms`

**ESP32 device ID** is derived from the MAC address. Publishes one topic per sensor (temperature, pressure) every 5 seconds.

## Key Components

| Directory | Language | Role |
|-----------|----------|------|
| `api/` | Python/Flask | REST API; GET-only; uses `DISTINCT ON` for latest-per-device queries |
| `ingestor/` | Python/paho-mqtt | MQTT subscriber; validates required fields; writes to `measurements` table |
| `broker/` | Mosquitto | Anonymous MQTT broker; TLS on 8883 (own CA, lab 10) + plaintext 1883 internal-only; persistence enabled |
| `database/` | PostgreSQL 18 | Schema in `database/01-init_database.sql`; tables: `sensor`, `measurements` |
| `esp32/` | C++/Arduino | Firmware; `esp32/src/main.cpp`; credentials in `esp32/secrets.h` (from `secrets.h.example`) |

## Configuration

Copy `.env.example` to `.env` before running Docker services. The `.env` file sets `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and is consumed by all Python services via Docker Compose.

ESP32 WiFi and MQTT credentials go in `esp32/secrets.h` (copy from `esp32/secrets.h.example`).

## Database

```bash
# Connect to running PostgreSQL container
docker exec -it postgres psql -U admin -d abcd_db

# Quick checks
SELECT COUNT(*) FROM measurements;
SELECT * FROM measurements ORDER BY received_at DESC LIMIT 5;
```

No external volumes are configured — data is lost on `docker compose down -v`.

## Documentation

Modular docs are in `docs/`. `DOKUMENTACJA.md` is the consolidated single-file version. Both are in Polish.
