import json
from datetime import UTC, datetime, timedelta

from app.ingest import handle_status, handle_telemetry


def seed(session, device_id="dev1", age_seconds=0, temp_c=20.0):
    ts = datetime.now(UTC) - timedelta(seconds=age_seconds)
    body = {"ts": ts.isoformat(), "temp_c": temp_c, "humidity": 40, "relay_on": True}
    handle_telemetry(session, device_id, json.dumps(body).encode())


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_unknown_device_is_404(client):
    assert client.get("/devices/nope/state").status_code == 404
    assert client.get("/devices/nope/readings").status_code == 404
    assert client.put("/devices/nope/setpoint", json={"setpoint_c": 21}).status_code == 404


def test_state_reflects_latest_reading(client, session):
    handle_status(session, "dev1", b"online")
    seed(session, temp_c=19.5)
    data = client.get("/devices/dev1/state").json()
    assert data["status"] == "online"
    assert data["latest"]["temp_c"] == 19.5
    assert data["is_stale"] is False


def test_state_marks_old_reading_as_stale(client, session):
    seed(session, age_seconds=600)
    assert client.get("/devices/dev1/state").json()["is_stale"] is True


def test_state_with_no_readings_is_stale(client, session):
    handle_status(session, "dev1", b"online")
    data = client.get("/devices/dev1/state").json()
    assert data["latest"] is None and data["is_stale"] is True


def test_set_setpoint_persists_and_publishes(client, session, publisher):
    seed(session)
    resp = client.put("/devices/dev1/setpoint", json={"setpoint_c": 22.5})
    assert resp.status_code == 200
    assert publisher.commands == [("dev1", 22.5)]
    assert client.get("/devices/dev1/state").json()["setpoint_c"] == 22.5


def test_setpoint_out_of_range_is_rejected_and_not_published(client, session, publisher):
    seed(session)
    for bad in (-5, 4.9, 30.1, 100):
        assert client.put("/devices/dev1/setpoint", json={"setpoint_c": bad}).status_code == 422
    assert publisher.commands == []


def test_readings_newest_first_and_limited(client, session):
    for age in (300, 200, 100):
        seed(session, age_seconds=age, temp_c=age / 10)
    rows = client.get("/devices/dev1/readings?limit=2").json()
    assert [r["temp_c"] for r in rows] == [10.0, 20.0]


def test_readings_limit_validation(client, session):
    seed(session)
    assert client.get("/devices/dev1/readings?limit=0").status_code == 422
