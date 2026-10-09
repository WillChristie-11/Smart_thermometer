from model import RoomModel


def test_heats_when_below_setpoint():
    m = RoomModel(temp_c=15, setpoint_c=21)
    m.step(1)
    assert m.relay_on is True
    assert m.temp_c > 15


def test_relay_off_when_above_setpoint():
    m = RoomModel(temp_c=25, setpoint_c=21, relay_on=True)
    m.step(1)
    assert m.relay_on is False


def test_hysteresis_holds_state_inside_band():
    on = RoomModel(temp_c=21.2, setpoint_c=21, relay_on=True)
    on.update_relay()
    assert on.relay_on is True
    off = RoomModel(temp_c=20.8, setpoint_c=21, relay_on=False)
    off.update_relay()
    assert off.relay_on is False


def test_cools_toward_outdoor_when_off():
    m = RoomModel(temp_c=21, setpoint_c=10, outdoor_c=0)
    m.step(10)
    assert 0 < m.temp_c < 21


def test_settles_near_setpoint():
    m = RoomModel(temp_c=15, setpoint_c=21)
    for _ in range(300):
        m.step(1)
    assert abs(m.temp_c - 21) < 1.5
