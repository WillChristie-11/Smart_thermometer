import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    mqtt_host: str
    mqtt_port: int
    mqtt_enabled: bool
    stale_after_seconds: int


def get_settings() -> Settings:
    """Read settings from the environment on each call so tests can override them."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://thermostat:thermostat@localhost:5432/thermostat",
        ),
        mqtt_host=os.getenv("MQTT_HOST", "localhost"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        mqtt_enabled=os.getenv("MQTT_ENABLED", "true").lower() == "true",
        stale_after_seconds=int(os.getenv("STALE_AFTER_SECONDS", "60")),
    )
