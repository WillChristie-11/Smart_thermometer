import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.models import Device, Reading
from app.mqtt import CommandPublisher, MqttBridge, NullPublisher

logging.basicConfig(level=logging.INFO)


class SetpointIn(BaseModel):
    setpoint_c: float = Field(ge=5, le=30)


class ReadingOut(BaseModel):
    ts: datetime
    temp_c: float
    humidity: float | None
    relay_on: bool


class StateOut(BaseModel):
    device_id: str
    status: str
    setpoint_c: float | None
    latest: ReadingOut | None
    is_stale: bool


def _as_utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; Postgres returns aware ones.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def create_app(
    database_url: str | None = None,
    mqtt_enabled: bool | None = None,
    publisher: CommandPublisher | None = None,
) -> FastAPI:
    settings = get_settings()
    engine = make_engine(database_url or settings.database_url)
    use_mqtt = settings.mqtt_enabled if mqtt_enabled is None else mqtt_enabled

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)  # swap for Alembic migrations later
        bridge = None
        if use_mqtt and publisher is None:
            bridge = MqttBridge(settings.mqtt_host, settings.mqtt_port, app.state.session_factory)
            bridge.start()
            app.state.publisher = bridge
        yield
        if bridge:
            bridge.stop()

    app = FastAPI(title="Smart Thermostat API", lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    app.state.publisher = publisher or NullPublisher()
    app.state.stale_after = timedelta(seconds=settings.stale_after_seconds)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/devices/{device_id}/state", response_model=StateOut)
    def get_state(device_id: str, request: Request, session: Session = Depends(get_session)):
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(404, "Unknown device")
        latest = session.scalars(
            select(Reading)
            .where(Reading.device_id == device_id)
            .order_by(Reading.ts.desc())
            .limit(1)
        ).first()
        is_stale = latest is None or (
            datetime.now(UTC) - _as_utc(latest.ts) > request.app.state.stale_after
        )
        return StateOut(
            device_id=device.id,
            status=device.status,
            setpoint_c=device.setpoint_c,
            latest=ReadingOut.model_validate(latest, from_attributes=True) if latest else None,
            is_stale=is_stale,
        )

    @app.get("/devices/{device_id}/readings", response_model=list[ReadingOut])
    def get_readings(
        device_id: str,
        limit: int = Query(100, ge=1, le=1000),
        session: Session = Depends(get_session),
    ):
        if session.get(Device, device_id) is None:
            raise HTTPException(404, "Unknown device")
        rows = session.scalars(
            select(Reading)
            .where(Reading.device_id == device_id)
            .order_by(Reading.ts.desc())
            .limit(limit)
        ).all()
        return [ReadingOut.model_validate(r, from_attributes=True) for r in rows]

    @app.put("/devices/{device_id}/setpoint")
    def set_setpoint(
        device_id: str,
        body: SetpointIn,
        request: Request,
        session: Session = Depends(get_session),
    ):
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(404, "Unknown device")
        device.setpoint_c = body.setpoint_c
        session.commit()
        request.app.state.publisher.publish_command(device_id, body.setpoint_c)
        return {"device_id": device_id, "setpoint_c": body.setpoint_c}

    return app


app = create_app()
