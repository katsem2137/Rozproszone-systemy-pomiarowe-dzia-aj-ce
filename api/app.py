from flask import Flask, jsonify, request
import os
import db
from auth import auth_required

app = Flask(__name__)

# Maksymalny wiek (w sekundach) najnowszego odczytu, by urzadzenie bylo uznane
# za "zywe" i pokazane w /latest. Starsze odczyty (np. martwe urzadzenia sprzed
# dni/tygodni) sa pomijane. Konfigurowalne przez zmienna srodowiskowa
# LATEST_MAX_AGE_SECONDS; domyslnie 300 s (5 min). /history i /devices NIE sa filtrowane.
LATEST_MAX_AGE_SECONDS = int(os.environ.get("LATEST_MAX_AGE_SECONDS", "300"))

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/devices")
@auth_required
def get_devices():
    conn = db.get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT device_id
        FROM measurements
        ORDER BY device_id
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    devices = [row[0] for row in rows]
    return jsonify(devices)

@app.route("/latest")
@auth_required
def get_latest():
    device_id = request.args.get("device_id")

    conn = db.get_connection()
    cur = conn.cursor()

    if device_id:
        cur.execute("""
            SELECT DISTINCT ON (device_id, sensor)
                device_id, sensor, value, unit, ts_ms, received_at
            FROM measurements
            WHERE device_id = %s
              AND received_at > CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
            ORDER BY device_id, sensor, received_at DESC
        """, (device_id, LATEST_MAX_AGE_SECONDS))
    else:
        cur.execute("""
            SELECT DISTINCT ON (device_id, sensor)
                device_id, sensor, value, unit, ts_ms, received_at
            FROM measurements
            WHERE received_at > CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
            ORDER BY device_id, sensor, received_at DESC
        """, (LATEST_MAX_AGE_SECONDS,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "device_id":   row[0],
            "sensor":      row[1],
            "value":       row[2],
            "unit":        row[3],
            "ts_ms":       row[4],
            "received_at": row[5].isoformat()
        })

    return jsonify(result)


@app.route("/history")
@auth_required
def get_history():
    device_id = request.args.get("device_id")
    sensor    = request.args.get("sensor")
    limit     = request.args.get("limit", 50)

    conn = db.get_connection()
    cur  = conn.cursor()

    query  = """
        SELECT device_id, sensor, value, unit, ts_ms, received_at
        FROM measurements
        WHERE TRUE
    """
    params = []

    if device_id:
        query += " AND device_id = %s"
        params.append(device_id)

    if sensor:
        query += " AND sensor = %s"
        params.append(sensor)

    query += " ORDER BY received_at DESC LIMIT %s"
    params.append(int(limit))

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "device_id":   row[0],
            "sensor":      row[1],
            "value":       row[2],
            "unit":        row[3],
            "ts_ms":       row[4],
            "received_at": str(row[5])
        })

    return jsonify(results)

def _get_latest_by_sensor(sensor_name, device_id):
    conn = db.get_connection()
    cur = conn.cursor()

    if device_id:
        cur.execute("""
            SELECT DISTINCT ON (device_id)
                device_id, sensor, value, unit, ts_ms, received_at
            FROM measurements
            WHERE sensor = %s
            AND device_id = %s
            AND received_at > CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
            ORDER BY device_id, received_at DESC
        """, (sensor_name, device_id, LATEST_MAX_AGE_SECONDS))
    else:
        cur.execute("""
            SELECT DISTINCT ON (device_id)
                device_id, sensor, value, unit, ts_ms, received_at
            FROM measurements
            WHERE sensor = %s
            AND received_at > CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
            ORDER BY device_id, received_at DESC
        """, (sensor_name, LATEST_MAX_AGE_SECONDS))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [{
        "device_id":   row[0],
        "sensor":      row[1],
        "value":       row[2],
        "unit":        row[3],
        "ts_ms":       row[4],
        "received_at": row[5].isoformat()
    } for row in rows]


@app.route("/latest/temperature")
@auth_required
def get_latest_temperature():
    return jsonify(_get_latest_by_sensor("temperature", request.args.get("device_id")))


@app.route("/latest/pressure")
@auth_required
def get_latest_pressure():
    return jsonify(_get_latest_by_sensor("pressure", request.args.get("device_id")))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
