
def test_live_returns_200(client):
    response = client.get("/live")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_cors_allows_frontend_origin(client):
    response = client.get("/live", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


def test_cors_blocks_other_origins(client):
    response = client.get("/live", headers={"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in response.headers


def test_ready_returns_200_when_db_is_up(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ready"


