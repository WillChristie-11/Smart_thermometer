"""Pure-ish ingestion logic: validate MQTT payloads and write them to the database.

Kept free of any MQTT client code so it can be unit tested with plain bytes.
"""

import logging
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.models import Device, Reading

log = logging.getLogger(__name__)

MAX_FUTURE_SKEW = timedelta(seconds=60)
VALID_STATUSES = {"online", "offline"}


class Telemetry(BaseModel):
    ts: datetime
    temp_c: float = Field(ge=-40, le=85)  # sensor range; anything else is a bad reading
    humidity: float | None = Field(default=None, ge=0, le=100)
    relay_on: bool


def parse_topic(topic: str) -> tuple[str, str] | None:
    """'home/<device_id>/<kind>' -> (device_id, kind), else None."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "home" or not parts[1]:
        return None
    return parts[1], parts[2]


def parse_telemetry(payload: bytes) -> Telemetry | None:
    try:
        telemetry = Telemetry.model_validate_json(payload)
    except ValidationError:
        return None
    if telemetry.ts.tzinfo is None:
        telemetry = telemetry.model_copy(update={"ts": telemetry.ts.replace(tzinfo=UTC)})
    return telemetry


def _get_or_create_device(session: Session, device_id: str) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        device = Device(id=device_id)
        session.add(device)
    return device


def handle_telemetry(
    session: Session, device_id: str, payload: bytes, now: datetime | None = None
) -> bool:
    """Store a reading. Returns False if the payload was rejected."""
    now = now or datetime.now(UTC)
    telemetry = parse_telemetry(payload)
    if telemetry is None:
        log.warning("Rejected malformed telemetry from %s", device_id)
        return False
    if telemetry.ts > now + MAX_FUTURE_SKEW:
        log.warning("Rejected telemetry from %s with future timestamp", device_id)
        return False

    _get_or_create_device(session, device_id)
    session.add(
        Reading(
            device_id=device_id,
            ts=telemetry.ts,
            temp_c=telemetry.temp_c,
            humidity=telemetry.humidity,
            relay_on=telemetry.relay_on,
        )
    )
    session.commit()
    return True


def handle_status(session: Session, device_id: str, payload: bytes) -> bool:
    status = payload.decode("utf-8", errors="replace").strip().lower()
    if status not in VALID_STATUSES:
        log.warning("Ignored unknown status %r from %s", status, device_id)
        return False
    device = _get_or_create_device(session, device_id)
    device.status = status
    session.commit()
    return True
