from app import app, init_db


def run_checks():
    init_db()
    client = app.test_client()

    response = client.get("/api/patients")
    assert response.status_code == 200, "GET /api/patients should return 200"
    assert isinstance(response.get_json(), list), "GET /api/patients should return a list"

    invalid_payload = {"full_name": "Test User"}
    response = client.post("/api/patients", json=invalid_payload)
    assert response.status_code == 400, "POST /api/patients with missing fields should return 400"

    valid_payload = {
        "full_name": "Amina Yusuf",
        "phone": "+254700000000",
        "status": "New",
        "notes": "Initial intake completed",
        "next_follow_up": "2026-05-01",
    }
    response = client.post("/api/patients", json=valid_payload)
    assert response.status_code == 201, "POST /api/patients with valid payload should return 201"

    response = client.get("/api/patients")
    patients = response.get_json()
    assert any(p["full_name"] == "Amina Yusuf" for p in patients), "New patient should be retrievable"

    print("All Merciful Health CRM API checks passed.")


if __name__ == "__main__":
    run_checks()
