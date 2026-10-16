"""MQTT ingestion.

Device publishes JSON (same fields as TelemetryIn plus "secret") to:
    selfx/<device_id>/telemetry
Server replies on:
    selfx/<device_id>/cmd   {"interval_s": 300, "sos_active": false}

Production: enable TLS + per-device broker credentials (ACL: a device may only
publish/subscribe its own topics). The "secret" field is then optional.
"""
import json
import logging
import threading

from .config import settings
from .db import SessionLocal
from .schemas import TelemetryIn
from .security import authenticate_device
from .services import ingest_telemetry

log = logging.getLogger("selfx.mqtt")


def start() -> None:
    if not settings.mqtt_enabled:
        return
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="selfx-backend")
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    def on_connect(c, userdata, flags, rc, props=None):
        log.info("MQTT connected rc=%s", rc)
        c.subscribe("selfx/+/telemetry", qos=1)

    def on_message(c, userdata, msg):
        try:
            device_id = msg.topic.split("/")[1]
            data = json.loads(msg.payload)
            secret = data.pop("secret", "")
            with SessionLocal() as db:
                dev = authenticate_device(db, device_id, secret)
                interval, sos_on = ingest_telemetry(db, dev, TelemetryIn(**data))
            c.publish(f"selfx/{device_id}/cmd", json.dumps({"interval_s": interval, "sos_active": sos_on}), qos=1)
        except Exception as e:  # never crash the bridge
            log.warning("MQTT message rejected on %s: %s", msg.topic, e)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    threading.Thread(target=client.loop_forever, daemon=True).start()
