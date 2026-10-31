"""
run.py - one-click start for the sensor Whack-a-Mole.

Starts the sensor tracker in the background, then the game (via
play_with_sensors.py). Close the game and the tracker is stopped too.

    python run.py                  -> latest game, biggest screen (TV if plugged in)
    python run.py --display 0      -> force the laptop screen
    python run.py whack_a_moleV2.py -> another game version

Anything you add after run.py is passed straight to play_with_sensors.py.
Tracker output goes to tracker_log.txt (check it if the boards don't connect).
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRACKER = HERE / "sensor_to_processing_zoned.py"
LAUNCHER = HERE / "play_with_sensors.py"
LOG = HERE / "tracker_log.txt"


def main():
    for f in (TRACKER, LAUNCHER):
        if not f.exists():
            raise SystemExit(f"Missing {f.name} - put run.py in the game folder.")

    print("Starting sensor tracker  (log: tracker_log.txt)")
    log = open(LOG, "w")
    tracker = subprocess.Popen([sys.executable, "-u", str(TRACKER)], cwd=HERE,
                               stdout=log, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    if tracker.poll() is not None:
        log.close()
        print(LOG.read_text()[-800:])
        raise SystemExit("Tracker stopped straight away (see above). "
                         "Is another copy already running? Close it and try again.")

    print("Starting game...")
    try:
        subprocess.run([sys.executable, str(LAUNCHER), *sys.argv[1:]], cwd=HERE)
    except KeyboardInterrupt:
        pass
    finally:
        print("Game closed - stopping tracker.")
        tracker.terminate()
        try:
            tracker.wait(timeout=3)
        except subprocess.TimeoutExpired:
            tracker.kill()
        log.close()
        found = [l.strip() for l in LOG.read_text().splitlines() if "board found" in l]
        if found:
            print("Boards seen this session:\n  " + "\n  ".join(found))


if __name__ == "__main__":
    main()
