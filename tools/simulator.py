"""SelfXTrack device simulator.

Pretends to be a tracker walking a route and (optionally) pressing SOS.
Use it to test the backend and Android app before the hardware is ready.

  # 1) provision a device (prints secret + claim code)
  python tools/simulator.py provision SX-0001
  # lost the secret? get a new one (tracker stays claimed)
  python tools/simulator.py reset-secret SX-0001
  # 2) claim it in the Android app with the device ID + claim code
  # 3) run the walk (HTTP)
  python tools/simulator.py run SX-0001 <secret> --sos-after 60
  # elderly fall / school bus / OTA
  python tools/simulator.py run SX-0003 <secret> --fall-after 30
  python tools/simulator.py run SX-0001 <secret> --bus BUS-12 --board-after 20 --alight-after 80
  python tools/simulator.py run SX-0001 <secret> --fw 1.1.0     # accepts an OTA offer and "installs" it
"""
import argparse
import math
import time

import httpx

ROUTE = [  # small loop in Bengaluru (replace with your area)
    (12.97160, 77.59460), (12.97230, 77.59520), (12.97310, 77.59610),
    (12.97380, 77.59700), (12.97300, 77.59790), (12.97200, 77.59720),
]


def heading(a, b):
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(math.radians(b[0]))
    x = math.cos(math.radians(a[0])) * math.sin(math.radians(b[0])) - \
        math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def reset_secret(args):
    r = httpx.post(f"{args.server}/api/admin/devices/{args.device_id}/secret", headers={"X-Admin-Key": args.admin_key})
    print(r.status_code, r.json())


def provision(args):
    r = httpx.post(f"{args.server}/api/admin/devices", json={"device_id": args.device_id},
                   headers={"X-Admin-Key": args.admin_key})
    r.raise_for_status()
    print(r.json())


def run(args):
    h = {"X-Device-Id": args.device_id, "X-Device-Secret": args.secret}
    bat, i, start, fw = 90.0, 0, time.time(), args.fw
    fall_sent = False
    while True:
        a, b = ROUTE[i % len(ROUTE)], ROUTE[(i + 1) % len(ROUTE)]
        el = time.time() - start
        sos = 1 if args.sos_after is not None and el >= args.sos_after else 0
        fall = 1 if args.fall_after is not None and el >= args.fall_after and not fall_sent else 0
        still = args.still or (args.fall_after is not None and el >= args.fall_after)
        body = {"t": int(time.time()), "lat": a[0], "lon": a[1], "acc": 8, "spd": 0 if still else 4.5,
                "hdg": round(heading(a, b)), "bat": int(bat), "chg": 0, "sos": sos, "fall": fall, "fw": fw,
                "act": 0 if still else 12}
        if args.bus:   # on the bus between --board-after and --alight-after seconds
            on = (args.board_after or 0) <= el < (args.alight_after or 1e9)
            body["ble"] = [args.bus] if on else []
        try:
            r = httpx.post(f"{args.server}/api/device/telemetry", json=body, headers=h, timeout=10)
            j = r.json()
            print(r.status_code, {k: v for k, v in j.items() if v is not None}, body)
            if fall:
                fall_sent = True
            if j.get("ota"):
                print("  -> OTA offered:", j["ota"]["version"], "(simulating install)")
                httpx.post(f"{args.server}/api/device/ota-status", headers=h, timeout=10,
                           json={"version": j["ota"]["version"], "status": "installed"})
                fw = j["ota"]["version"]
        except httpx.HTTPError as e:
            print("network error:", e)
        if not still:
            i += 1
        bat = max(5.0, bat - args.drain)
        time.sleep(args.interval)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--server", default="http://localhost:8000")
    p.add_argument("--admin-key", default="change-me-admin-key")
    sub = p.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("provision"); s1.add_argument("device_id"); s1.set_defaults(fn=provision)
    s3 = sub.add_parser("reset-secret"); s3.add_argument("device_id"); s3.set_defaults(fn=reset_secret)
    s2 = sub.add_parser("run"); s2.add_argument("device_id"); s2.add_argument("secret")
    s2.add_argument("--interval", type=float, default=5); s2.add_argument("--sos-after", type=float)
    s2.add_argument("--fall-after", type=float, help="send a fall (elderly) after N seconds, then stay still")
    s2.add_argument("--still", action="store_true", help="no movement (elderly inactivity test)")
    s2.add_argument("--bus", help="BLE beacon ID of the bus, e.g. BUS-12")
    s2.add_argument("--board-after", type=float); s2.add_argument("--alight-after", type=float)
    s2.add_argument("--drain", type=float, default=0.1, help="battery %% used per report")
    s2.add_argument("--fw", default="sim-0.1")
    s2.set_defaults(fn=run)
    a = p.parse_args(); a.fn(a)
