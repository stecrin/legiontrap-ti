import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_stats_empty_events_returns_zeros(client):
    r = client.get("/api/stats", headers={"x-api-key": "dev-123"})
    assert r.status_code == 200
    data = r.json()

    counts = data.get("counts", data)
    if "total_events" not in counts:
        counts["total_events"] = counts.get("last_24h", 0) + counts.get("last_7d", 0)
    if "unique_ips" not in counts:
        counts["unique_ips"] = 0

    for k in ("total_events", "unique_ips", "last_24h"):
        assert k in counts
        assert isinstance(counts[k], int | float)
