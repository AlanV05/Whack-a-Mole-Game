"""
game_settings.py - tuning values in a plain text file (whack_settings.json)
=========================================================================
So the hammer, reach, calibration spot etc. can be changed on demo day
(or on another laptop, or in the installed Windows version) WITHOUT editing
code. The file sits next to the game (or next to WhackAMole.exe). If it is
missing it is created with the defaults below the first time the game runs.

Delete the file to go back to the defaults.
"""

import json
import sys
from pathlib import Path

SETTINGS_FILE = "whack_settings.json"

DEFAULTS = {
    "_help": "Edit the values, save, restart the game. Delete this file to reset to defaults.",

    # --- hammer movement
    "snap_to_holes": False,        # true = old behaviour, hammer jumps hole to hole
    "mirror_x": False,             # true if moving left makes the hammer go right
    "flip_y": False,               # true if walking toward the screen moves the hammer down
    "lateral_gain": 1.35,          # stretch left/right so the outer holes can be reached
    "free_smoothing": 0.45,        # 0..1 per frame: lower = steadier, more lag
    "deadband_cm": 3.0,            # ignore movements smaller than this (stops jitter when standing still)
    "hit_reach": 0.35,             # how close counts as a hit, in hole-spacings (0.35 ~ 17 cm)

    # --- whacking
    "auto_whack": True,            # standing on a mole whacks it
    "auto_whack_dwell_ms": 0,      # how long you must stand on it first

    # --- calibration check (player stands on the centre X)
    "calibration_spot_cm": [75, 170],   # [across from the left edge, out from the wall]
    "calibration_tolerance_cm": 40,     # a sensor 'sees you' if within this of the expected distance
    "calibration_hold_s": 0.6,          # ...for this long

    # --- setup guide
    "box_height_cm": 100,          # height to mount the sensor boxes (shown on the setup page)
}


def app_dir():
    """Folder the game runs from (next to the .exe when installed)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load():
    """Defaults, overridden by whatever is in whack_settings.json."""
    settings = dict(DEFAULTS)
    path = app_dir() / SETTINGS_FILE
    if path.exists():
        try:
            user = json.loads(path.read_text())
            for key, value in user.items():
                if key in DEFAULTS:
                    settings[key] = value
            print(f"[settings] loaded {path}")
        except (OSError, ValueError) as error:
            print(f"[settings] couldn't read {path} ({error}) - using defaults")
    else:
        try:
            path.write_text(json.dumps(DEFAULTS, indent=2))
            print(f"[settings] created {path} with the default values")
        except OSError:
            pass      # read-only folder: just use the defaults
    return settings
