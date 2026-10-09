"""A tiny physical model of a room with a heater. Pure Python, easy to test."""

from dataclasses import dataclass


@dataclass
class RoomModel:
    temp_c: float = 18.0
    setpoint_c: float = 21.0
    outdoor_c: float = 5.0
    relay_on: bool = False
    hysteresis_c: float = 0.5
    heat_rate_c_per_min: float = 0.5
    loss_coeff_per_min: float = 0.02

    def update_relay(self) -> None:
        """Bang-bang control with hysteresis so the relay doesn't chatter at the setpoint."""
        if self.temp_c < self.setpoint_c - self.hysteresis_c:
            self.relay_on = True
        elif self.temp_c > self.setpoint_c + self.hysteresis_c:
            self.relay_on = False

    def step(self, minutes: float) -> None:
        self.update_relay()
        heating = self.heat_rate_c_per_min * minutes if self.relay_on else 0.0
        loss = self.loss_coeff_per_min * (self.temp_c - self.outdoor_c) * minutes
        self.temp_c += heating - loss
