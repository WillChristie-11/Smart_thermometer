import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class FakePublisher:
    def __init__(self):
        self.commands: list[tuple[str, float]] = []

    def publish_command(self, device_id: str, setpoint_c: float) -> None:
        self.commands.append((device_id, setpoint_c))


@pytest.fixture
def publisher():
    return FakePublisher()


@pytest.fixture
def app(publisher):
    return create_app(database_url="sqlite://", mqtt_enabled=False, publisher=publisher)


@pytest.fixture
def client(app):
    with TestClient(app) as c:  # context manager runs the lifespan (creates tables)
        yield c


@pytest.fixture
def session(app, client):
    with app.state.session_factory() as s:
        yield s
