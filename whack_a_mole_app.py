"""
whack_a_mole_app.py - ONE program: sensor tracker + game together
================================================================
This is what the Windows installer runs (WhackAMole.exe). It can also be run
on any computer with:  python whack_a_mole_app.py

  * starts the sensor tracker (sensor_to_processing_zoned.py) in the background
  * starts the game through play_with_sensors.py
  * writes everything the two print to whack_log.txt next to the program,
    so if the boards don't connect you can read what happened

Any extra arguments are passed to the game, e.g.
    WhackAMole.exe --display 1        (put the game on screen 1, the TV)
    WhackAMole.exe --picture 0.95     (shrink the picture if the TV cuts the edges)
    WhackAMole.exe --windowed

The first time it runs, Windows asks whether to let it use the network:
tick BOTH Private and Public and press Allow, or the boards can't reach it.
"""

import sys
import threading
import traceback

import game_settings

LOG_NAME = "whack_log.txt"


class _Tee:
    """Write to the log file and, if there is one, the console too."""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, text):
        for s in self.streams:
            try:
                s.write(text)
                s.flush()
            except Exception:
                pass

    def flush(self):
        pass


def _start_logging():
    try:
        log = open(game_settings.app_dir() / LOG_NAME, "w", buffering=1, encoding="utf-8")
    except OSError:
        return
    sys.stdout = _Tee(log, sys.__stdout__)
    sys.stderr = _Tee(log, sys.__stderr__)


def _run_tracker():
    try:
        import sensor_to_processing_zoned as tracker
        tracker.main()
    except Exception:
        print("[tracker] stopped with an error - the game will fall back to the mouse:")
        traceback.print_exc()


def main():
    _start_logging()
    print("Whack-a-Mole starting (tracker + game). Log:", game_settings.app_dir() / LOG_NAME)
    threading.Thread(target=_run_tracker, daemon=True, name="tracker").start()

    import play_with_sensors
    play_with_sensors.main()


if __name__ == "__main__":
    main()
