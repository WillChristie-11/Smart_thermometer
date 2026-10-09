import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.ingest import handle_status, handle_telemetry, parse_telemetry, parse_topic
from app.models import Device, Reading

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def payload(**overrides) -> bytes:
    body = {"ts": NOW.isoformat(), "temp_c": 20.5, "humidity": 40, "relay_on": False}
    body.update(overrides)
    return json.dumps(body).encode()


def test_parse_topic():
    assert parse_topic("home/abc/telemetry") == ("abc", "telemetry")
    assert parse_topic("home/abc") is None
    assert parse_topic("other/abc/telemetry") is None
    assert parse_topic("home//telemetry") is None


def test_parse_valid_telemetry():
    t = parse_telemetry(payload())
    assert t is not None and t.temp_c == 20.5


def test_parse_assumes_utc_for_naive_timestamp():
    t = parse_telemetry(payload(ts="2026-01-01T12:00:00"))
    assert t is not None and t.ts.tzinfo is not None


def test_parse_rejects_garbage():
    assert parse_telemetry(b"not json") is None
    assert parse_telemetry(b'{"temp_c": 20}') is None


def test_parse_rejects_out_of_range_temperature():
    assert parse_telemetry(payload(temp_c=500)) is None
    assert parse_telemetry(payload(humidity=150)) is None


def test_handle_telemetry_stores_reading_and_creates_device(session):
    assert handle_telemetry(session, "dev1", payload(), now=NOW) is True
    assert session.get(Device, "dev1") is not None
    assert len(session.scalars(select(Reading)).all()) == 1


def test_handle_telemetry_rejects_future_timestamp(session):
    future = (NOW + timedelta(hours=1)).isoformat()
    assert handle_telemetry(session, "dev1", payload(ts=future), now=NOW) is False
    assert session.scalars(select(Reading)).all() == []


def test_handle_telemetry_rejects_malformed(session):
    assert handle_telemetry(session, "dev1", b"nope", now=NOW) is False


def test_handle_status_updates_device(session):
    assert handle_status(session, "dev1", b"online") is True
    assert session.get(Device, "dev1").status == "online"
    assert handle_status(session, "dev1", b"offline") is True
    assert session.get(Device, "dev1").status == "offline"


def test_handle_status_ignores_unknown_values(session):
    assert handle_status(session, "dev1", b"banana") is False
