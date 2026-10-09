# Design notes

## MQTT contract

| Topic | Direction | Payload | Flags |
|---|---|---|---|
| `home/{device_id}/telemetry` | device -> backend | `{"ts": ISO-8601, "temp_c": float, "humidity": float, "relay_on": bool}` | QoS 1 |
| `home/{device_id}/status` | device -> backend | `online` / `offline` | retained, QoS 1; `offline` is the last will |
| `home/{device_id}/command` | backend -> device | `{"setpoint_c": float}` | retained, QoS 1 |

## Decisions
- **Retained command:** a device that reconnects after an outage gets the latest setpoint immediately.
- **Last will:** the broker marks a device offline even if it dies without a clean disconnect.
- **Validation at both ends:** the API limits setpoint to 5-30 C; the device re-checks; the backend rejects out-of-range or future-dated readings.
- **Stale vs offline:** `status` says what the broker believes; `is_stale` says whether data is actually fresh.

## Data model
- `devices(id, setpoint_c, status)`
- `readings(id, device_id -> devices.id, ts, temp_c, humidity, relay_on)`

## Open questions
- What should the device do if it loses the network mid-schedule?
- How long to retain readings?
