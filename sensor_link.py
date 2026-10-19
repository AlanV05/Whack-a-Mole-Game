"""
ENGG3000 Whack-a-Mole - sensor link (PC side)

Receives the three ESP32 ultrasonic readings over Wi-Fi/UDP and turns them
into everything the game needs:

    which sensors are online      -> Sensor Check screen
    which hole the player is in   -> cursor position
    a "whack" event               -> replaces the mouse click
    whether the player is too close to the screen -> warning + buzzer

No pygame in here, so this file can be tested on its own
(see tests/test_sensor_link.py).

Physical layout this assumes (from the play-area drawing):

          wall / screen  (1.5 m wide)
     [S1 LEFT]     [S2 MID]     [S3 RIGHT]     <- sensors on the wall, facing out
    |------------ dead zone 0-60 cm -------------|   warning + buzzer
    |   left col   |   mid col    |   right col  |   60-200 cm = play area
    |              |              |              |   split into 3 rows of ~46.7 cm

    Column = which sensor sees the player (the closest valid reading).
    Row    = how far that sensor says the player is from the wall.

Packet format sent by each ESP32 (plain text):   "<sensor_id>,<distance_mm>"
    e.g. "1,850"   -> sensor 1 sees something 850 mm away
         "2,-1"    -> sensor 2 got no echo (nothing in front of it)

Buzzer command sent back to the buzzer box:      "BUZZ 1" / "BUZZ 0"
"""

import socket
import statistics
import time

# ---------------------------------------------------------------------------
# Settings - change these to match the real setup
# ---------------------------------------------------------------------------
LISTEN_PORT = 5005           # PC listens here (same number as in the ESP32 sketch)
BUZZER_PORT = 5006           # buzzer ESP32 listens here for BUZZ commands
SENSOR_IDS = (1, 2, 3)
BUZZER_SENSOR_ID = 2         # schematic puts the buzzer in Box 2 (wireless doc said #3 - check!)

# Which on-screen column each sensor covers (0 = left, 1 = middle, 2 = right).
# If the boxes end up mounted in a different order, just swap the numbers.
COLUMN_FOR_SENSOR = {1: 0, 2: 1, 3: 2}

DEAD_ZONE_CM = 60.0          # closer than this to the wall = too close
PLAY_FAR_CM = 200.0          # back edge of the play area
FAR_MARGIN_CM = 20.0         # still count someone standing just past the back line
MIN_VALID_CM = 2.0           # RCWL-1601 can't measure closer than this
MAX_VALID_CM = 400.0         # anything further is treated as "no echo"

ONLINE_TIMEOUT_S = 1.0       # sensor counts as offline if silent this long
MEDIAN_WINDOW = 5            # readings per sensor used for the median filter
ROW_HYSTERESIS_CM = 5.0      # stops the cursor flickering on a row boundary
COLUMN_HYSTERESIS_CM = 15.0  # keep current column unless another sensor is clearly closer

# Whack rule: the player has to step INTO a hole's zone and hold still for
# WHACK_DWELL_S.  That fires one whack.  To whack the same hole again they
# must step out and back in (stops someone just standing on one hole).
WHACK_DWELL_S = 0.35

BUZZER_RESEND_S = 0.3        # resend BUZZ 1 this often (UDP can drop packets;
                             # the ESP32 turns itself off if it stops hearing it)

GRID_ROWS = 3
GRID_COLS = 3

_NO_ECHO = float("inf")


def parse_packet(data):
    """b"1,850" -> (1, 85.0 cm).  Bad packets return None.  No echo -> (id, inf)."""
    try:
        text = data.decode("ascii").strip()
        parts = text.replace(":", ",").split(",")
        sensor_id = int(parts[0].strip().lstrip("Ss"))
        distance_mm = float(parts[1])
    except (UnicodeDecodeError, ValueError, IndexError):
        return None
    if sensor_id not in SENSOR_IDS:
        return None
    distance_cm = distance_mm / 10.0
    if not (MIN_VALID_CM <= distance_cm <= MAX_VALID_CM):
        distance_cm = _NO_ECHO
    return sensor_id, distance_cm


def row_for_distance(distance_cm, previous_row=None):
    """
    Distance from the wall -> row index (0 = row nearest the screen).

    Play area (60-200 cm) is split into 3 equal bands of ~46.7 cm.
    Anyone in the dead zone is put in row 0 (they are also flagged too close).
    """
    depth = PLAY_FAR_CM - DEAD_ZONE_CM
    fraction = (distance_cm - DEAD_ZONE_CM) / depth
    fraction = min(max(fraction, 0.0), 0.999)
    row = int(fraction * GRID_ROWS)

    # Hysteresis: if we are only just over the line from the previous row, stay.
    if previous_row is not None and row != previous_row and abs(row - previous_row) == 1:
        boundary_cm = DEAD_ZONE_CM + depth * max(row, previous_row) / GRID_ROWS
        if abs(distance_cm - boundary_cm) < ROW_HYSTERESIS_CM:
            return previous_row
    return row


class SensorLink:
    def __init__(self, port=LISTEN_PORT, clock=time.monotonic, sock=None):
        self._clock = clock
        if sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError as exc:
                raise OSError(
                    f"Could not listen on UDP port {port} ({exc}). "
                    "Is another copy of the game already running?"
                ) from exc
        sock.setblocking(False)
        self._sock = sock

        self._history = {sid: [] for sid in SENSOR_IDS}
        self._last_seen = {sid: None for sid in SENSOR_IDS}
        self._address = {sid: None for sid in SENSOR_IDS}
        self.packets_received = 0

        self._zone = None              # (col, row) or None
        self._zone_since = None
        self._whack_fired = False
        self._pending_whack = False

        self._buzzer_wanted = False
        self._buzzer_sent_state = None
        self._buzzer_sent_at = 0.0

    # ----- receiving -------------------------------------------------------
    def poll(self):
        """Call once per frame.  Reads every waiting packet, never blocks."""
        while True:
            try:
                data, address = self._sock.recvfrom(256)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            self.feed(data, address)
        self._update_zone()
        self._update_buzzer()

    def feed(self, data, address=None):
        """Handle one packet (used by poll(), and directly by the tests)."""
        parsed = parse_packet(data)
        if parsed is None:
            return
        sensor_id, distance_cm = parsed
        history = self._history[sensor_id]
        history.append(distance_cm)
        if len(history) > MEDIAN_WINDOW:
            del history[0]
        self._last_seen[sensor_id] = self._clock()
        if address is not None:
            self._address[sensor_id] = address[0]
        self.packets_received += 1

    # ----- status ----------------------------------------------------------
    def is_online(self, sensor_id):
        seen = self._last_seen[sensor_id]
        return seen is not None and (self._clock() - seen) <= ONLINE_TIMEOUT_S

    def status(self):
        """{1: True/False, 2: ..., 3: ...} in the same shape the game already uses."""
        return {sid: self.is_online(sid) for sid in SENSOR_IDS}

    def all_online(self):
        return all(self.status().values())

    def distance_cm(self, sensor_id):
        """Filtered distance, or None if offline / nothing in front of the sensor."""
        if not self.is_online(sensor_id) or not self._history[sensor_id]:
            return None
        value = statistics.median(self._history[sensor_id])
        return None if value == _NO_ECHO else value

    # ----- player position -------------------------------------------------
    def _best_column(self):
        """(sensor_id, distance) of the sensor that is tracking the player."""
        seen = {}
        for sid in SENSOR_IDS:
            d = self.distance_cm(sid)
            if d is not None and d <= PLAY_FAR_CM + FAR_MARGIN_CM:
                seen[sid] = d
        if not seen:
            return None
        best_sid = min(seen, key=seen.get)

        # Column hysteresis: two neighbouring sensors can both see the player
        # when they stand on the line.  Stay put unless the other one is clearly closer.
        if self._zone is not None:
            current_sid = next(
                (sid for sid, col in COLUMN_FOR_SENSOR.items() if col == self._zone[0]), None
            )
            if current_sid in seen and seen[current_sid] - seen[best_sid] < COLUMN_HYSTERESIS_CM:
                best_sid = current_sid
        return best_sid, seen[best_sid]

    def _update_zone(self):
        best = self._best_column()
        if best is None:
            new_zone = None
        else:
            sid, distance = best
            col = COLUMN_FOR_SENSOR[sid]
            previous_row = self._zone[1] if (self._zone and self._zone[0] == col) else None
            new_zone = (col, row_for_distance(distance, previous_row))

        now = self._clock()
        if new_zone != self._zone:
            self._zone = new_zone
            self._zone_since = now
            self._whack_fired = False
        elif (new_zone is not None and not self._whack_fired
              and not self.too_close()
              and now - self._zone_since >= WHACK_DWELL_S):
            self._whack_fired = True
            self._pending_whack = True

    def player_zone(self):
        """(col, row) of the hole the player is standing in, or None."""
        return self._zone

    def hole_index(self):
        """Index into the game's HOLE_POSITIONS (row-major), or None."""
        if self._zone is None:
            return None
        col, row = self._zone
        return row * GRID_COLS + col

    def take_whack(self):
        """True once per whack.  The game calls this every frame."""
        if self._pending_whack:
            self._pending_whack = False
            return True
        return False

    # ----- safety ----------------------------------------------------------
    def too_close(self):
        """True if ANY online sensor sees someone inside the dead zone."""
        for sid in SENSOR_IDS:
            d = self.distance_cm(sid)
            if d is not None and d < DEAD_ZONE_CM:
                return True
        return False

    def set_buzzer(self, on):
        self._buzzer_wanted = bool(on)

    def _update_buzzer(self):
        address = self._address.get(BUZZER_SENSOR_ID)
        if address is None:
            return  # haven't heard from the buzzer box yet, so don't know its IP
        now = self._clock()
        changed = self._buzzer_wanted != self._buzzer_sent_state
        keepalive = self._buzzer_wanted and (now - self._buzzer_sent_at) >= BUZZER_RESEND_S
        if changed or keepalive:
            message = b"BUZZ 1" if self._buzzer_wanted else b"BUZZ 0"
            try:
                self._sock.sendto(message, (address, BUZZER_PORT))
            except OSError:
                return
            self._buzzer_sent_state = self._buzzer_wanted
            self._buzzer_sent_at = now

    def close(self):
        self._buzzer_wanted = False
        self._buzzer_sent_state = None
        self._update_buzzer()
        self._sock.close()
