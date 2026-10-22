"""
Zoned Whack-a-Mole tracker  (time-division firing + weighted-blend lateral)
==========================================================================
Polls the 4 ESP32 ultrasonic sensors over WiFi ONE AT A TIME and sends the
player's position to the Processing sketch over OSC.

TIME-DIVISION FIRING (new)
  Before, all boards free-ran and sometimes pinged at the same instant, so a
  sensor could hear ANOTHER sensor's echo and report a fake distance. That is
  what threw the avatar to the top-right and back.
  Now this script is the conductor: it sends "FIRE" to one board, waits for its
  reply (or a timeout), waits a short guard gap for the echo to die out, then
  moves to the next board. Only one sensor is ever pinging -> no crosstalk.
  Order is LEFT -> MID2 -> MID -> RIGHT so back-to-back pings come from
  far-apart sensors. Boards announce themselves with "HELLO <ID>" so no IPs to type in.

LATERAL (overlap fix)
  Lateral position is a softmax-weighted blend of every sensor that sees the
  player (nearest = heaviest), so overlap glides instead of twitching.

GHOST-READING GUARD
  A sensor that isn't tracking you must report CONFIRM_COUNT consistent
  readings in a row before it counts, so one-off junk echoes are ignored.

DATA IN  (UDP 9000): "LEFT 123.45" (id + cm, -1 = no echo) and "HELLO LEFT"
DATA OUT (UDP 9002 to boards): "FIRE"
DATA OUT (OSC 9001): /avatar [depth_cm, lateral_frac, d_1 .. d_N]   (raw cm per sensor, SENSORS order)
                     /boards [online_1 .. online_N]                (1/0)
                     /stats  [hz xN, reply% xN, round-trip ms xN]  (once a second)
Boards find this PC by itself (they broadcast HELLO) - no IP to configure.

Requires:  pip install python-osc
"""

import math
import socket
import time
from collections import deque

from pythonosc import udp_client

# ------------------------------------------------------------------ PLAY AREA
PLAY_WIDTH_CM = 150.0
PLAY_DEPTH_CM = 140.0                          # play-area depth (spec)
DEADZONE_CM = 60.0                             # SEPARATE space in front of the play area
FAR_EDGE_CM = DEADZONE_CM + PLAY_DEPTH_CM      # 200 = sensor -> back of play area
USABLE_DEPTH_CM = PLAY_DEPTH_CM                # 140. Player reads 60..200cm from the sensor.

# ------------------------------------------------------------------ NETWORK
UDP_LISTEN_PORT = 9000        # boards -> PC
POLL_PORT = 9002              # PC -> boards (must match POLL_PORT on the ESP32)
OSC_IP = "127.0.0.1"          # Processing is on THIS machine -> localhost
OSC_OUT_PORT = 9001
SEND_HZ = 60

# ------------------------------------------------------------------ TIME-DIVISION
# ------------------------------------------------------------------ SENSOR LAYOUT
# (board SENSOR_ID, x position across the play area in cm), listed LEFT -> RIGHT.
# 4 sensors, all facing STRAIGHT ahead, one per 37.5 cm lane (lane centres).
# Want the old 3-sensor setup back? Use [("LEFT", 25), ("MID", 75), ("RIGHT", 125)]
# and FIRE_ORDER = ["LEFT", "RIGHT", "MID"].
SENSORS = [("LEFT", 18.75), ("MID", 56.25), ("MID2", 93.75), ("RIGHT", 131.25)]
FIRE_ORDER = ["LEFT", "MID2", "MID", "RIGHT"]   # far-apart sensors back to back
REPLY_TIMEOUT_MS = 60         # give up on a board's reply after this
GUARD_MS = 10                 # quiet gap after each ping so the echo dies out
BOARD_ONLINE_MS = 1000        # a board counts as online if we heard from it this recently

# ------------------------------------------------------------------ DETECTION
MAX_DETECT_CM = 250.0
SENSOR_STALE_MS = 400         # 4 sensors -> each updates ~every 170ms, so allow a bit more
HYSTERESIS_CM = 20.0

# ------------------------------------------------------------------ SMOOTHING
# 0..1 per frame. LOWER = smoother + more lag. HIGHER = snappier + more jitter.
LATERAL_SMOOTH = 0.35
DEPTH_SMOOTH = 0.5

# How sharply the lateral blend favours the nearest sensor, in cm.
#   SMALL (~8) -> snaps to nearest sensor's column; LARGE (~25) -> softer blend
LATERAL_TAU_CM = 15.0

# ------------------------------------------------------------------ PER-SENSOR FILTER
SMOOTHING_WINDOW = 3          # was 8: shorter average = dot keeps up with the player
MEDIAN_WINDOW = 3
MAX_JUMP_CM = 40.0

# Ghost-reading guard (see top). Readings under MIN_VALID_CM always ignored.
CONFIRM_COUNT = 2
CONFIRM_TOL_CM = 15.0
MIN_VALID_CM = 20.0

NAMES = [n for n, _ in SENSORS]
SENSOR_X = dict(SENSORS)
assert sorted(FIRE_ORDER) == sorted(NAMES), "FIRE_ORDER must list every sensor once"


def ms():
    return int(time.time() * 1000)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fmt(v):
    return f"{v:.0f}" if v is not None else "--"


class SensorReader:
    def __init__(self, name):
        self.name = name
        self.raw_window = deque(maxlen=MEDIAN_WINDOW)
        self.history = deque(maxlen=SMOOTHING_WINDOW)
        self.value = None
        self.last_valid_ms = 0
        self.pending = deque(maxlen=CONFIRM_COUNT)

    def push(self, raw):
        if raw is None or raw < MIN_VALID_CM or raw > MAX_DETECT_CM:
            return

        if self.value is None:
            # Not tracking yet -> make it prove itself before it counts.
            self.pending.append(raw)
            if len(self.pending) < CONFIRM_COUNT:
                return
            if max(self.pending) - min(self.pending) > CONFIRM_TOL_CM:
                return  # inconsistent = junk; keep waiting
            for p in self.pending:
                self.raw_window.append(p)
                self.history.append(p)
            self.pending.clear()
            self.value = sum(self.history) / len(self.history)
            self.last_valid_ms = ms()
            return

        if abs(raw - self.value) > MAX_JUMP_CM:
            return
        self.raw_window.append(raw)
        median_val = sorted(self.raw_window)[len(self.raw_window) // 2]
        self.history.append(median_val)
        self.value = sum(self.history) / len(self.history)
        self.last_valid_ms = ms()

    def current(self):
        if self.value is None:
            return None
        if ms() - self.last_valid_ms > SENSOR_STALE_MS:
            self.value = None
            self.raw_window.clear()
            self.history.clear()
            self.pending.clear()
            return None
        return self.value


def pick_column(seen, current_col):
    """Which sensor owns DEPTH? Nearest sensor, with hysteresis to stop flicker.
    seen = [(sensor_name, distance_cm), ...]"""
    if not seen:
        return current_col, None
    best_col, best_dist = min(seen, key=lambda t: t[1])
    if current_col is None:
        return best_col, best_dist
    current_dist = next((d for c, d in seen if c == current_col), None)
    if current_dist is None:
        return best_col, best_dist
    if best_col != current_col and (current_dist - best_dist) > HYSTERESIS_CM:
        return best_col, best_dist
    return current_col, current_dist


def lateral_target(seen):
    """Softmax-weighted blend of the x position of every sensor that sees the
    player (nearest = heaviest). Returns 0..1 across the play width."""
    if not seen:
        return None
    d_min = min(d for _, d in seen)
    num = den = 0.0
    for name, d in seen:
        w = math.exp(-(d - d_min) / LATERAL_TAU_CM)
        num += SENSOR_X[name] * w
        den += w
    return clamp((num / den) / PLAY_WIDTH_CM, 0.0, 1.0)


class Poller:
    """Fires one board at a time: FIRE -> wait reply/timeout -> guard gap -> next."""

    def __init__(self, sock):
        self.sock = sock
        self.addrs = {}            # sensor name -> board IP, learned from packets
        self.last_seen = {}        # sensor name -> ms of last packet (HELLO or reading)
        self.turn = 0
        self.state = "idle"        # idle -> waiting -> guard -> idle
        self.expected = None
        self.t_state = 0
        # Performance counters, reset every second -> /stats (used for test data)
        self.replies = {n: 0 for n in FIRE_ORDER}
        self.timeouts = {n: 0 for n in FIRE_ORDER}
        self.rtt_sum = {n: 0 for n in FIRE_ORDER}
        self.stats = {"hz": {n: 0.0 for n in FIRE_ORDER},
                      "ok": {n: 0.0 for n in FIRE_ORDER},
                      "rtt": {n: 0.0 for n in FIRE_ORDER}}
        self.stats_t = ms()

    def roll_stats(self):
        """Once a second: turn counters into update rate, reply %, round-trip ms."""
        now = ms()
        span = now - self.stats_t
        if span < 1000:
            return False
        for n in FIRE_ORDER:
            r, t = self.replies[n], self.timeouts[n]
            self.stats["hz"][n] = r * 1000.0 / span
            self.stats["ok"][n] = 100.0 * r / (r + t) if (r + t) else 0.0
            self.stats["rtt"][n] = self.rtt_sum[n] / r if r else 0.0
            self.replies[n] = self.timeouts[n] = self.rtt_sum[n] = 0
        self.stats_t = now
        return True

    def learn(self, name, ip):
        self.last_seen[name] = ms()
        if self.addrs.get(name) != ip:
            print(f"[{name}] board found at {ip}")
            self.addrs[name] = ip

    def got_reply(self, name):
        if self.state == "waiting" and name == self.expected:
            now = ms()
            self.replies[name] += 1
            self.rtt_sum[name] += now - self.t_state
            self.state = "guard"
            self.t_state = now

    def step(self):
        now = ms()
        if self.state == "idle":
            for _ in range(len(FIRE_ORDER)):
                name = FIRE_ORDER[self.turn]
                self.turn = (self.turn + 1) % len(FIRE_ORDER)
                if name in self.addrs:
                    try:
                        self.sock.sendto(b"FIRE", (self.addrs[name], POLL_PORT))
                    except OSError:
                        continue
                    self.expected = name
                    self.state = "waiting"
                    self.t_state = now
                    return
        elif self.state == "waiting" and now - self.t_state > REPLY_TIMEOUT_MS:
            self.timeouts[self.expected] += 1
            self.state = "guard"           # no reply; still leave the quiet gap
            self.t_state = now
        elif self.state == "guard" and now - self.t_state >= GUARD_MS:
            self.state = "idle"


def handle_packet(data, addr, readers, poller):
    try:
        parts = data.decode(errors="ignore").strip().split()
        if len(parts) != 2:
            return
        a, b = parts[0].upper(), parts[1]
        if a == "HELLO":
            name = b.upper()
            if name in readers:
                poller.learn(name, addr[0])
            return
        if a in readers:
            poller.learn(a, addr[0])
            readers[a].push(float(b))
            poller.got_reply(a)
    except ValueError:
        pass


def main():
    readers = {name: SensorReader(name) for name in NAMES}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_LISTEN_PORT))
    sock.setblocking(False)

    osc = udp_client.SimpleUDPClient(OSC_IP, OSC_OUT_PORT)
    poller = Poller(sock)

    active_col = None
    depth = 0.0
    lateral = 0.5
    send_interval_ms = 1000 // SEND_HZ
    last_send = 0
    last_print = 0

    print(f"Listening on UDP {UDP_LISTEN_PORT}, polling boards on {POLL_PORT}, "
          f"OSC to {OSC_IP}:{OSC_OUT_PORT}  (Ctrl+C to stop)")
    print("Waiting for boards to say HELLO...")

    try:
        while True:
            # 1) drain incoming packets
            while True:
                try:
                    data, addr = sock.recvfrom(64)
                except BlockingIOError:
                    break
                handle_packet(data, addr, readers, poller)

            # 2) advance the firing schedule
            poller.step()

            now = ms()
            if now - last_send >= send_interval_ms:
                last_send = now

                # 3) snapshot sensors
                cur = {name: r.current() for name, r in readers.items()}
                seen = [(name, d) for name, d in cur.items() if d is not None]

                # 4) depth source + continuous lateral blend, eased
                active_col, active_dist = pick_column(seen, active_col)
                if active_dist is not None:
                    target_depth = clamp(active_dist - DEADZONE_CM, 0.0, USABLE_DEPTH_CM)
                    target_lateral = lateral_target(seen)
                    depth += (target_depth - depth) * DEPTH_SMOOTH
                    lateral += (target_lateral - lateral) * LATERAL_SMOOTH
                # else: nobody seen -> hold last position

                # 5) dead-zone alarm
                nearest = min([d for d in cur.values() if d is not None], default=None)
                deadzone = nearest is not None and nearest < DEADZONE_CM

                # 6) send to Processing
                osc.send_message("/avatar", [float(depth), float(lateral)] + [
                    float(cur[n]) if cur[n] is not None else -1.0 for n in NAMES])
                # Board health (1 = heard from it in the last second), SENSORS order.
                # Used by the pygame game's Sensor Check screen.
                osc.send_message("/boards", [
                    int(now - poller.last_seen.get(name, -BOARD_ONLINE_MS) < BOARD_ONLINE_MS)
                    for name in NAMES
                ])
                # Performance stats once a second (for hd_tests.py):
                # [hz x N, reply% x N, round-trip ms x N], SENSORS order
                if poller.roll_stats():
                    osc.send_message("/stats",
                        [float(poller.stats[k][n]) for k in ("hz", "ok", "rtt") for n in NAMES])

                if now - last_print > 500:
                    col_name = active_col or "----"
                    warn = "   !!! DEAD ZONE !!!" if deadzone else ""
                    boards = ",".join(n for n in NAMES if n in poller.addrs) or "none"
                    dists = " ".join(f"{n}={fmt(cur[n])}" for n in NAMES)
                    hz = "/".join(f"{poller.stats['hz'][n]:.0f}" for n in NAMES)
                    print(f"near: {col_name:5} depth: {depth:5.1f}/{USABLE_DEPTH_CM:.0f}cm "
                          f"lat: {lateral:.2f}  ({dists})  boards: {boards}  Hz: {hz}{warn}")
                    last_print = now

            time.sleep(0.001)   # 1ms tick keeps the schedule tight without maxing a CPU core

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()