import json
import logging
from typing import Protocol

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session, sessionmaker

from app.ingest import handle_status, handle_telemetry, parse_topic

log = logging.getLogger(__name__)


class CommandPublisher(Protocol):
    def publish_command(self, device_id: str, setpoint_c: float) -> None: ...


class NullPublisher:
    """Used when MQTT is disabled (tests, running the API on its own)."""

    def publish_command(self, device_id: str, setpoint_c: float) -> None:
        log.info("MQTT disabled; dropping command for %s", device_id)


class MqttBridge:
    """Subscribes to device topics and publishes commands."""

    def __init__(self, host: str, port: int, session_factory: sessionmaker[Session]):
        self._host = host
        self._port = port
        self._session_factory = session_factory
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="thermostat-backend")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def start(self) -> None:
        # connect_async + loop_start: the API still boots if the broker is down,
        # and paho keeps retrying in the background.
        self._client.connect_async(self._host, self._port)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish_command(self, device_id: str, setpoint_c: float) -> None:
        # retain=True so a device that reconnects later still receives the latest setpoint.
        self._client.publish(
            f"home/{device_id}/command",
            json.dumps({"setpoint_c": setpoint_c}),
            qos=1,
            retain=True,
        )

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        log.info("MQTT connected: %s", reason_code)
        # Subscribe on every (re)connect so subscriptions survive broker restarts.
        client.subscribe([("home/+/telemetry", 1), ("home/+/status", 1)])

    def _on_message(self, client, userdata, msg) -> None:
        parsed = parse_topic(msg.topic)
        if parsed is None:
            return
        device_id, kind = parsed
        try:
            with self._session_factory() as session:
                if kind == "telemetry":
                    handle_telemetry(session, device_id, msg.payload)
                elif kind == "status":
                    handle_status(session, device_id, msg.payload)
        except Exception:
            # Never let one bad message kill the network thread.
            log.exception("Error handling message on %s", msg.topic)
