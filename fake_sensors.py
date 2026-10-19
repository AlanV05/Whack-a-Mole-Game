"""
Pretend to be the three ESP32 sensor boxes, so the game can be tested
without any hardware (wireless plan step 11).

Start the game first:      python play_with_sensors.py
Then in another terminal:  python tools/fake_sensors.py

Modes
    python tools/fake_sensors.py                  walk through all 9 holes, then
                                                  step into the dead zone, then leave
    python tools/fake_sensors.py --fixed 100 200 300
                                                  keep sending fixed mm values for
                                                  sensors 1, 2, 3 (-1 = no echo)
    --host 192.168.1.100                          send to another PC instead of this one

It also prints any BUZZ commands the game sends back to the buzzer box.
"""

import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sensor_link as cfg  # noqa: E402  (reuse the same port / zone settings)

SEND_HZ = 15


def zone_centre_cm(row):
    depth = cfg.PLAY_FAR_CM - cfg.DEAD_ZONE_CM
    return cfg.DEAD_ZONE_CM + depth * (row + 0.5) / cfg.GRID_ROWS


def readings_for(col, distance_cm):
    """Player standing in front of one column: that sensor sees them, the others don't."""
    out = {}
    for sid, sensor_col in cfg.COLUMN_FOR_SENSOR.items():
        out[sid] = int(distance_cm * 10) if (col is not None and sensor_col == col) else -1
    return out


def tour():
    """Yields (label, readings) for a scripted walk, ~1.5 s per stop."""
    yield "nobody in play area", readings_for(None, 0), 2.0
    for row in range(cfg.GRID_ROWS):
        for col in range(cfg.GRID_COLS):
            d = zone_centre_cm(row)
            yield f"hole col={col} row={row}  ({d:.0f} cm)", readings_for(col, d), 1.5
    yield "TOO CLOSE: middle, 40 cm", readings_for(1, 40), 2.5
    yield "back to middle hole", readings_for(1, zone_centre_cm(1)), 1.5
    yield "left the play area", readings_for(None, 0), 2.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--fixed", nargs=3, type=int, metavar=("S1_MM", "S2_MM", "S3_MM"))
    parser.add_argument("--loop", action="store_true", help="repeat the tour forever")
    args = parser.parse_args()

    senders = {sid: socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for sid in cfg.SENSOR_IDS}
    buzzer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        buzzer.bind(("0.0.0.0", cfg.BUZZER_PORT))
        buzzer.setblocking(False)
    except OSError:
        buzzer = None
        print(f"(port {cfg.BUZZER_PORT} busy - buzzer commands won't be shown)")

    def send(readings):
        for sid, mm in readings.items():
            senders[sid].sendto(f"{sid},{mm}".encode(), (args.host, cfg.LISTEN_PORT))
        if buzzer is not None:
            while True:
                try:
                    data, _ = buzzer.recvfrom(64)
                except (BlockingIOError, OSError):
                    break
                print(f"    buzzer box got: {data.decode()}")

    if args.fixed:
        readings = dict(zip(cfg.SENSOR_IDS, args.fixed))
        print(f"Sending fixed values {readings} to {args.host}:{cfg.LISTEN_PORT}  (Ctrl+C to stop)")
        while True:
            send(readings)
            time.sleep(1 / SEND_HZ)

    print(f"Sending to {args.host}:{cfg.LISTEN_PORT}  (Ctrl+C to stop)")
    while True:
        for label, readings, seconds in tour():
            print(f"- {label:38s} {readings}")
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                send(readings)
                time.sleep(1 / SEND_HZ)
        if not args.loop:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
