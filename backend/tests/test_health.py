from fastapi.testclient import TestClient
from app.main import app


def test_health_is_local_liveness_without_provider_or_configuration_disclosure():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
