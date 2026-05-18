from flask import Flask, jsonify, request
import db

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/devices")
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
            ORDER BY device_id, sensor, received_at DESC
        """, (device_id,))
    else:
        cur.execute("""
            SELECT DISTINCT ON (device_id, sensor)
                device_id, sensor, value, unit, ts_ms, received_at
            FROM measurements
            ORDER BY device_id, sensor, received_at DESC
        """)

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
            ORDER BY device_id, received_at DESC
        """, (sensor_name, device_id))
    else:
        cur.execute("""
            SELECT DISTINCT ON (device_id)
                device_id, sensor, value, unit, ts_ms, received_at
            FROM measurements
            WHERE sensor = %s
            ORDER BY device_id, received_at DESC
        """, (sensor_name,))

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
def get_latest_temperature():
    return jsonify(_get_latest_by_sensor("temperature", request.args.get("device_id")))


@app.route("/latest/pressure")
def get_latest_pressure():
    return jsonify(_get_latest_by_sensor("pressure", request.args.get("device_id")))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)