from datetime import datetime
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request

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
        conn.commit()


@app.route("/")
def home():
    return render_template("index.html")


@app.get("/api/patients")
def list_patients():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM patients ORDER BY created_at DESC"
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
        conn.commit()
    return jsonify({"id": cursor.lastrowid, "message": "Patient added"}), 201


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
