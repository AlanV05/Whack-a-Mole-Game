"""
play_with_sensors.py
====================
Runs the dev team's pygame Whack-a-Mole with the ultrasonic sensor rig.

The team's game file is NOT edited. This launcher loads it, then swaps a few
things in at runtime before calling its run_game():

  * pygame.mouse.get_pos()   -> returns the player's sensor position, mapped
                                onto the game's own 3x3 hole grid.
  * auto-whack               -> standing on a mole for a moment counts as a
                                hit (AUTO_WHACK setting). Stand-in for a jump.
  * mouse clicks             -> a click anywhere whacks at the PLAYER'S
                                position, not the mouse's. ENTER does the same,
                                so someone else can whack while you move.
                                (Real jump detection is still TBD.)
  * player_is_too_close_to_screen()  -> real distance from the sensors.
  * Sensor Check screen (V2 only)    -> real board status, not the 1-4 keys.

V2 COMPATIBILITY (Sprint 3 update)
  V2 draws on a fixed-size canvas and scales it up to fill the monitor, so it
  treats mouse positions as WINDOW pixels and converts them back with
  window_to_game(). The sensor position is worked out in GAME pixels, so it is
  now passed through the game's game_to_window() before being handed over
  (cursor + every injected click). Older game versions without that function
  are unaffected. The hole layout is also re-read every frame (the O key
  switches landscape/portrait), and the Sensor Check screen now shows all
  four boards one-to-one.

If no sensor data is coming in, everything falls back to the normal mouse, so
the game still works for testing without the rig.

HOW TO RUN (two terminals, both with the venv active)
  1) python sensor_to_processing_zoned.py
  2) python play_with_sensors.py                   -> runs whack_a_moleV2.py
     python play_with_sensors.py whack_a_mole.py   -> runs another version
     python play_with_sensors.py --display 1        -> force the game onto screen 1 (the TV)
     python play_with_sensors.py --picture 0.95     -> shrink the picture if the TV cuts edges
  Don't run the Processing sketch at the same time: both listen on port 9001.

Requires:  pip install pygame python-osc
"""

import importlib.util
import sys
import threading
import time
from pathlib import Path

import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

# ------------------------------------------------------------------ SETTINGS
DEFAULT_GAME = "whack_a_moleV2.py"
OSC_LISTEN_IP = "127.0.0.1"
OSC_LISTEN_PORT = 9001          # must match OSC_OUT_PORT in the tracker
SENSOR_TIMEOUT_S = 1.0          # no tracker data for this long -> fall back to mouse

PLAY_DEPTH_CM = 140.0           # must match USABLE_DEPTH_CM in the tracker

# Flip these if the avatar moves the wrong way on screen.
MIRROR_X = False                # True: LEFT sensor drives the RIGHT side of the screen
FLIP_Y = False                  # True: walking toward the sensors moves the cursor DOWN

# Lock the cursor onto the nearest hole, with a dead-band so it doesn't flicker
# on the line between two holes. False = free, continuous movement.
SNAP_TO_HOLES = True
SNAP_HYSTERESIS = 0.15          # fraction of a hole-spacing you must pass before switching

WHACK_KEY = pygame.K_RETURN     # keyboard whack at the player's position

# Auto-whack: standing on a mole for AUTO_WHACK_DWELL_MS counts as a hit, no
# click/ENTER needed. Stand-in until real jump detection exists. Set False to
# go back to click/ENTER only. (In V2 this includes red "AVOID" moles - step off them!)
AUTO_WHACK = True
AUTO_WHACK_DWELL_MS = 0         # 0 = instant hit the moment you're on the mole
FALLBACK_SAFETY_CM = 50.0       # used only if the game doesn't define its own

# Sensor Check slots -> tracker boards, by index into the tracker's SENSORS
# order [LEFT, MID, MID2, RIGHT]. Picked automatically from how many slots the
# game shows (its DEFAULT_SENSOR_STATUS).
SENSOR_SLOTS_4 = {1: [0], 2: [1], 3: [2], 4: [3]}   # V2: one slot per board
SENSOR_SLOTS_3 = {1: [0], 2: [1, 2], 3: [3]}        # older 3-slot game: slot 2 = both middles


# ------------------------------------------------------------------ SENSOR FEED
class SensorFeed:
    """Holds the latest data from the tracker, filled in by a background thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.depth = 0.0
        self.lateral = 0.5
        self.raw = []                      # distance per sensor in cm (-1 = none)
        self.boards = []                   # online flag per sensor
        self.last_avatar = 0.0
        self.last_boards = 0.0

    def on_avatar(self, _addr, *args):
        if len(args) < 3:
            return
        with self.lock:
            self.depth = float(args[0])
            self.lateral = float(args[1])
            self.raw = [float(a) for a in args[2:]]
            self.last_avatar = time.time()

    def on_boards(self, _addr, *args):
        if not args:
            return
        with self.lock:
            self.boards = [int(a) for a in args]
            self.last_boards = time.time()

    def live(self):
        return time.time() - self.last_avatar < SENSOR_TIMEOUT_S

    def boards_live(self):
        return time.time() - self.last_boards < SENSOR_TIMEOUT_S

    def snapshot(self):
        with self.lock:
            return self.depth, self.lateral, list(self.raw), list(self.boards)


def start_osc_listener(feed):
    dispatcher = Dispatcher()
    dispatcher.map("/avatar", feed.on_avatar)
    dispatcher.map("/boards", feed.on_boards)
    try:
        server = ThreadingOSCUDPServer((OSC_LISTEN_IP, OSC_LISTEN_PORT), dispatcher)
    except OSError as error:
        raise SystemExit(
            f"Can't listen on port {OSC_LISTEN_PORT} ({error}).\n"
            "Is the Processing sketch (or another copy of this) still running? Close it first."
        )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Listening for the sensor tracker on {OSC_LISTEN_IP}:{OSC_LISTEN_PORT}")


# ------------------------------------------------------------------ POSITION MAPPING
class GridMapper:
    """
    Maps the tracker's (depth, lateral) onto the game's own hole grid, read from
    the game's HOLE_POSITIONS, so it lines up whatever layout the team uses.
    The play area is split into equal thirds each way: the middle of each third
    lands exactly on a hole row/column. Returns GAME (canvas) pixels.
    """

    def __init__(self, game):
        self.game = game
        self.snap_col = None
        self.snap_row = None

    @staticmethod
    def _continuous_index(frac, n):
        # cell i has its centre at (i + 0.5) / n
        return max(-0.5, min(n - 0.5, frac * n - 0.5))

    @staticmethod
    def _index_to_px(idx, centers):
        if len(centers) == 1:
            return centers[0]
        step = (centers[-1] - centers[0]) / (len(centers) - 1)
        return centers[0] + idx * step

    @staticmethod
    def _snap(idx, current, n):
        if current is None or abs(idx - current) > 0.5 + SNAP_HYSTERESIS:
            current = int(round(idx))
        return max(0, min(n - 1, current))

    def map(self, depth_cm, lateral_frac):
        # Read the layout live: V2 rebuilds HOLE_POSITIONS / SCREEN_WIDTH when
        # the screen is switched landscape <-> portrait.
        holes = self.game.HOLE_POSITIONS
        xs = sorted({p[0] for p in holes})
        ys = sorted({p[1] for p in holes})
        width, height = self.game.SCREEN_WIDTH, self.game.SCREEN_HEIGHT

        x_frac = 1.0 - lateral_frac if MIRROR_X else lateral_frac
        y_frac = max(0.0, min(1.0, depth_cm / PLAY_DEPTH_CM))
        if FLIP_Y:
            y_frac = 1.0 - y_frac

        col = self._continuous_index(x_frac, len(xs))
        row = self._continuous_index(y_frac, len(ys))

        if SNAP_TO_HOLES:
            self.snap_col = self._snap(col, self.snap_col, len(xs))
            self.snap_row = self._snap(row, self.snap_row, len(ys))
            col, row = self.snap_col, self.snap_row

        x = self._index_to_px(col, xs)
        y = self._index_to_px(row, ys)
        return (int(max(0, min(width - 1, x))),
                int(max(0, min(height - 1, y))))


# ------------------------------------------------------------------ LOADING + PATCHING
def load_game(name):
    path = Path(name)
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).resolve().parent / name
    if not path.exists():
        raise SystemExit(f"Can't find the game file: {name}\n"
                         "Put play_with_sensors.py in the same folder as the game.")
    spec = importlib.util.spec_from_file_location("team_game", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules["team_game"] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "run_game"):
        raise SystemExit(f"{path.name} has no run_game() - is this the right file?")
    print(f"Loaded game: {path.name}")
    return module


def hook_up(game, feed):
    mapper = GridMapper(game)
    real_get_pos = pygame.mouse.get_pos
    real_event_get = pygame.event.get

    # V2 scales its canvas to the window and expects window pixels from the
    # mouse; older versions draw 1:1 and have no converter (identity).
    to_window = getattr(game, "game_to_window", None) or (lambda p: p)

    # The older version whacks on a DOUBLE click, V2 on a single click.
    clicks_per_whack = 2 if hasattr(game, "DOUBLE_CLICK_TIME_MS") else 1

    def player_pos():
        """Player position in GAME pixels (same space as HOLE_POSITIONS / moles)."""
        if not feed.live():
            return None
        depth, lateral, _, _ = feed.snapshot()
        return mapper.map(depth, lateral)

    # --- cursor follows the player
    def sensor_get_pos():
        pos = player_pos()
        return to_window(pos) if pos is not None else real_get_pos()

    # --- track which moles are on screen (every game version draws each mole every frame)
    live_moles = {}                      # id(mole) -> (mole, last_draw_ms)
    if hasattr(game, "Mole"):
        original_draw = game.Mole.draw

        def tracked_draw(self, *a, **kw):
            live_moles[id(self)] = (self, pygame.time.get_ticks())
            return original_draw(self, *a, **kw)

        game.Mole.draw = tracked_draw

    dwell = {"mole": None, "since": 0}

    def auto_whack_target(pos, now):
        """The mole the player has been standing on long enough, or None."""
        for key in [k for k, (_, t) in live_moles.items() if now - t > 200]:
            live_moles.pop(key, None)             # mole no longer drawn
        for key, (mole, _) in live_moles.items():
            # Flag lives on the mole itself: id() values get reused by new
            # moles, which used to make some moles impossible to auto-whack.
            if getattr(mole, "_sensor_whacked", False) or getattr(mole, "hit", False):
                continue
            try:
                on_it = mole.contains(pos)
            except Exception:
                on_it = False
            if not on_it:
                continue
            if dwell["mole"] != key:
                dwell["mole"], dwell["since"] = key, now
            if now - dwell["since"] >= AUTO_WHACK_DWELL_MS:
                mole._sensor_whacked = True
                dwell["mole"] = None
                return mole
            return None
        dwell["mole"] = None
        return None

    # --- clicks / ENTER whack at the player's position
    def sensor_event_get(*args, **kwargs):
        events = real_event_get(*args, **kwargs)
        pos = player_pos()                                   # game pixels (for mole.contains)
        win_pos = to_window(pos) if pos is not None else None  # what the game expects in events
        out = []
        if AUTO_WHACK and pos is not None and auto_whack_target(pos, pygame.time.get_ticks()):
            for _ in range(clicks_per_whack):
                out.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                              {"pos": win_pos, "button": 1}))
        for ev in events:
            if (win_pos is not None
                    and ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
                    and getattr(ev, "button", 1) == 1):
                data = dict(ev.dict)
                data["pos"] = win_pos
                out.append(pygame.event.Event(ev.type, data))
                continue
            out.append(ev)
            if ev.type == pygame.KEYDOWN and ev.key == WHACK_KEY:
                whack_at = win_pos if win_pos is not None else real_get_pos()
                for _ in range(clicks_per_whack):
                    out.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                  {"pos": whack_at, "button": 1}))
        return out

    pygame.mouse.get_pos = sensor_get_pos
    pygame.event.get = sensor_event_get

    # --- safety warning from the real distance
    if hasattr(game, "player_is_too_close_to_screen"):
        original_too_close = game.player_is_too_close_to_screen
        limit_cm = getattr(game, "SAFETY_WARNING_DISTANCE_CM", FALLBACK_SAFETY_CM)

        def sensor_too_close(cursor_pos):
            if not feed.live():
                return original_too_close(cursor_pos)
            _, _, raw, _ = feed.snapshot()
            readings = [d for d in raw if d > 0]
            return bool(readings) and min(readings) < limit_cm

        game.player_is_too_close_to_screen = sensor_too_close

    # --- Sensor Check screen shows real board status
    slot_count = len(getattr(game, "DEFAULT_SENSOR_STATUS", {}))
    slots = SENSOR_SLOTS_4 if slot_count >= 4 else SENSOR_SLOTS_3

    def live_status():
        _, _, _, boards = feed.snapshot()
        return {gid: all(i < len(boards) and boards[i] for i in idxs)
                for gid, idxs in slots.items()}

    if hasattr(game, "sensors_ready"):
        original_ready = game.sensors_ready

        def sensor_ready(status):
            if feed.boards_live():
                return all(live_status().values())
            return original_ready(status)

        game.sensors_ready = sensor_ready

    if hasattr(game, "draw_sensor_calibration"):
        original_calibration = game.draw_sensor_calibration

        def sensor_calibration(surface, now, font_big, font_small, sensor_status):
            status = live_status() if feed.boards_live() else sensor_status
            return original_calibration(surface, now, font_big, font_small, status)

        game.draw_sensor_calibration = sensor_calibration

    auto = f"stand on a mole for {AUTO_WHACK_DWELL_MS}ms, or " if AUTO_WHACK else ""
    print(f"Whack = {auto}left-click / ENTER ({clicks_per_whack} click(s) sent per whack). "
          f"Sensor Check: {len(slots)} slots. No sensor data -> falls back to the mouse.")


def main():
    # first .py argument is the game file. Everything else (--display 1,
    # --picture 0.95, --windowed ...) is left for the game to read.
    py_args = [a for a in sys.argv[1:] if a.lower().endswith(".py")]
    game_file = py_args[0] if py_args else DEFAULT_GAME
    game = load_game(game_file)
    feed = SensorFeed()
    start_osc_listener(feed)
    hook_up(game, feed)
    game.run_game()


if __name__ == "__main__":
    main()