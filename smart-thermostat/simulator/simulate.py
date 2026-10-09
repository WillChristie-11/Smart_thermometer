"""Fake thermostat device. Speaks the same MQTT contract the real ESP32 firmware will.

    python simulate.py --device-id dev1
    python simulate.py --device-id dev1 --crash-after 10   # drop off the network ungracefully
"""

import argparse
import json
import os
import time
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from model import RoomModel


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--device-id", default="dev1")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    p.add_argument("--time-scale", type=float, default=30.0, help="sim seconds per real second")
    p.add_argument("--crash-after", type=int, default=0, help="hard-exit after N readings")
    args = p.parse_args()

    base = f"home/{args.device_id}"
    model = RoomModel()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{args.device_id}")

    # Last will: the broker publishes this if we vanish without a clean disconnect.
    client.will_set(f"{base}/status", "offline", qos=1, retain=True)

    def on_connect(c, userdata, flags, reason_code, properties):
        print(f"connected: {reason_code}")
        c.publish(f"{base}/status", "online", qos=1, retain=True)
        c.subscribe(f"{base}/command", qos=1)

    def on_message(c, userdata, msg):
        try:
            setpoint = float(json.loads(msg.payload)["setpoint_c"])
        except (ValueError, KeyError, TypeError):
            print(f"ignored bad command: {msg.payload!r}")
            return
        if not 5 <= setpoint <= 30:  # the device enforces limits too; never trust the network
            print(f"ignored out-of-range setpoint: {setpoint}")
            return
        model.setpoint_c = setpoint
        print(f"new setpoint: {setpoint}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port)
    client.loop_start()

    sent = 0
    try:
        while True:
            model.step(args.interval * args.time_scale / 60)
            reading = {
                "ts": datetime.now(UTC).isoformat(),
                "temp_c": round(model.temp_c, 2),
                "humidity": 40.0,
                "relay_on": model.relay_on,
            }
            client.publish(f"{base}/telemetry", json.dumps(reading), qos=1)
            sent += 1
            print(f"sent {reading}")
            if args.crash_after and sent >= args.crash_after:
                os._exit(1)  # no DISCONNECT packet, so the broker fires the last will
            time.sleep(args.interval)
    except KeyboardInterrupt:
        client.publish(f"{base}/status", "offline", qos=1, retain=True).wait_for_publish()
        client.disconnect()


if __name__ == "__main__":
    main()
