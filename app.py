from datetime import datetime
import csv
from io import StringIO
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "crm.db"

app = Flask(__name__)


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                next_follow_up TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                action TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


@app.route("/")
def home():
    return render_template("index.html")


@app.get("/api/patients")
def list_patients():
    status_filter = request.args.get("status", "").strip()
    search_term = request.args.get("search", "").strip()

    conditions = []
    params = []
    if status_filter:
        conditions.append("status = ?")
        params.append(status_filter)
    if search_term:
        conditions.append("(full_name LIKE ? OR phone LIKE ? OR notes LIKE ?)")
        like_value = f"%{search_term}%"
        params.extend([like_value, like_value, like_value])

    where_clause = ""
    if conditions:
        where_clause = f"WHERE {' AND '.join(conditions)}"

    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM patients {where_clause} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/patients")
def create_patient():
    payload = request.get_json(force=True)
    required_fields = ["full_name", "phone", "status"]
    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO patients (full_name, phone, status, notes, next_follow_up, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload["full_name"],
                payload["phone"],
                payload["status"],
                payload.get("notes", ""),
                payload.get("next_follow_up", ""),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT INTO activity_logs (patient_id, action, description, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                cursor.lastrowid,
                "CREATE",
                f"Patient {payload['full_name']} added with status {payload['status']}",
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    return jsonify({"id": cursor.lastrowid, "message": "Patient added"}), 201


@app.patch("/api/patients/<int:patient_id>")
def update_patient(patient_id):
    payload = request.get_json(force=True)
    allowed_fields = {"status", "notes", "next_follow_up", "phone"}
    updates = {key: value for key, value in payload.items() if key in allowed_fields}
    if not updates:
        return jsonify({"error": "No updatable fields provided"}), 400

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, full_name FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        if not existing:
            return jsonify({"error": "Patient not found"}), 404

        set_clause = ", ".join([f"{field} = ?" for field in updates])
        values = list(updates.values()) + [patient_id]
        conn.execute(f"UPDATE patients SET {set_clause} WHERE id = ?", values)
        conn.execute(
            """
            INSERT INTO activity_logs (patient_id, action, description, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                patient_id,
                "UPDATE",
                f"Patient {existing['full_name']} profile updated",
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

    return jsonify({"message": "Patient updated successfully"})


@app.delete("/api/patients/<int:patient_id>")
def delete_patient(patient_id):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, full_name FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        if not existing:
            return jsonify({"error": "Patient not found"}), 404

        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.execute(
            """
            INSERT INTO activity_logs (patient_id, action, description, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                patient_id,
                "DELETE",
                f"Patient {existing['full_name']} removed from CRM",
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    return jsonify({"message": "Patient deleted successfully"})


@app.get("/api/dashboard")
def dashboard():
    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_patients,
                SUM(CASE WHEN status = 'New' THEN 1 ELSE 0 END) AS new_patients,
                SUM(CASE WHEN status = 'In Treatment' THEN 1 ELSE 0 END) AS in_treatment,
                SUM(CASE WHEN status = 'Follow-up Needed' THEN 1 ELSE 0 END) AS follow_up_needed,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) AS closed_cases
            FROM patients
            """
        ).fetchone()

        recent_activity = conn.execute(
            """
            SELECT action, description, created_at
            FROM activity_logs
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()

    return jsonify(
        {
            "summary": dict(totals),
            "recent_activity": [dict(row) for row in recent_activity],
        }
    )


@app.get("/api/export/patients.csv")
def export_patients_csv():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, full_name, phone, status, notes, next_follow_up, created_at
            FROM patients
            ORDER BY created_at DESC
            """
        ).fetchall()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "full_name",
            "phone",
            "status",
            "notes",
            "next_follow_up",
            "created_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["full_name"],
                row["phone"],
                row["status"],
                row["notes"],
                row["next_follow_up"],
                row["created_at"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=merciful_health_patients.csv"},
    )


init_db()


if __name__ == "__main__":
    app.run(debug=True)
