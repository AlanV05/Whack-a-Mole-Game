"""
hd_tests_v1.py - the SAME performance tests, for the Week 5 (V1) system
=======================================================================
Identical tests, scoring and settings to hd_tests.py, so V1 and V2 results can be
compared like-for-like. Works with the Week 5 code (sensor_to_processing_osc.py):
FRONT/LEFT/RIGHT boards over USB serial, OSC on port 9000.
Use it INSTEAD of the Processing game (both listen on port 9000).

RUN (two terminals, venv on in both)
  1) python sensor_to_processing_osc.py
  2) python hd_tests_v1.py

TESTS (pick from the menu)
  1  Accuracy    - stand in each of the 9 squares; % of time the system puts you
                   in the right square, plus position jitter in cm.
  2  Reach time  - a square lights up; time until the system has you locked in
                   it. (Includes the player's walking time - say so on the slide.)
  3  Safety      - stand inside the dead-zone (must warn) and in the play area
                   (must NOT warn). Uses V1's OWN alarm rule: FRONT sensor
                   under 60cm (what the Week 5 buzzer firmware did).
  Per-sensor valid-reading % (how often each board gave a usable distance) is
  logged the whole time.

  S  save results     ESC  back / quit
Results go in a "results_V1" folder next to this file.

Requires: pip install pygame-ce python-osc
"""

import csv
import random
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

# Flip these if the blue dot moves the wrong way. Note any change in your report.
MIRROR_X = False
FLIP_Y = False
PLAY_DEPTH_CM = 140.0          # same as V1 PLAY_DEPTH_CM

# ------------------------------------------------------------------ SETTINGS
OSC_PORT = 9000               # V1 sends to 9000
PLAY_WIDTH_CM = 150.0
SAFETY_CM = 60.0              # V1 alarm rule: FRONT sensor < 60cm (Week 5 firmware)
SETTLE_S = 1.5                # countdown before recording (get into position)
RECORD_S = 3.0                # how long each accuracy / safety trial records
REACH_TRIALS = 8
REACH_HOLD_S = 0.3            # must stay in the square this long to count as "reached"
REACH_TIMEOUT_S = 6.0
W, H = 900, 650
GRID = pygame.Rect(150, 110, 600, 420)   # on-screen play area (top = sensor side)

# ------------------------------------------------------------------ COLOURS
BG, INK, SOFT = (24, 26, 32), (235, 235, 235), (150, 155, 165)
LINE, TARGET, GOOD, BAD, DOT = (70, 75, 85), (255, 200, 60), (80, 200, 120), (230, 80, 70), (90, 170, 255)


# ------------------------------------------------------------------ SENSOR FEED
class Feed:
    def __init__(self):
        self.lock = threading.Lock()
        self.depth, self.lateral, self.raw = 0.0, 0.5, [-1.0] * 3
        self.t_avatar = 0.0
        self.stats_log = []               # unused in V1 (no /stats)
        self.frames = 0                   # /avatar messages received
        self.valid = [0, 0, 0]            # frames where FRONT/LEFT/RIGHT had a reading

    def avatar(self, _a, *args):
        if len(args) >= 5:
            with self.lock:
                self.depth, self.lateral = float(args[0]), float(args[1])
                self.raw = [float(v) for v in args[2:5]]
                self.t_avatar = time.time()
                self.frames += 1
                for i, v in enumerate(self.raw):
                    self.valid[i] += v > 0

    def stats(self, _a, *args):
        if len(args) >= 9:
            with self.lock:
                self.stats_log.append([float(v) for v in args[:9]])

    def live(self):
        return time.time() - self.t_avatar < 1.0

    def read(self):
        with self.lock:
            return self.depth, self.lateral, list(self.raw)


def start_listener(feed):
    d = Dispatcher()
    d.map("/avatar", feed.avatar)
    d.map("/stats", feed.stats)
    d.map("/boards", lambda *a: None)
    try:
        srv = ThreadingOSCUDPServer(("127.0.0.1", OSC_PORT), d)
    except OSError as e:
        raise SystemExit(f"Port {OSC_PORT} busy ({e}). Close the Processing game first.")
    threading.Thread(target=srv.serve_forever, daemon=True).start()


# ------------------------------------------------------------------ GEOMETRY
def fractions(depth, lateral):
    x = 1.0 - lateral if MIRROR_X else lateral
    y = max(0.0, min(1.0, depth / PLAY_DEPTH_CM))
    if FLIP_Y:
        y = 1.0 - y
    return max(0.0, min(1.0, x)), y


def cell_of(depth, lateral):
    x, y = fractions(depth, lateral)
    return min(2, int(y * 3)), min(2, int(x * 3))          # (row, col)


def cell_name(rc):
    rows = ["near", "middle", "far"]
    cols = ["left", "centre", "right"]
    return f"{rows[rc[0]]}-{cols[rc[1]]}"


def cell_rect(rc):
    cw, ch = GRID.w / 3, GRID.h / 3
    return pygame.Rect(GRID.x + rc[1] * cw, GRID.y + rc[0] * ch, cw, ch)


# ------------------------------------------------------------------ APP
class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("ENGG3000 V1 (Week 5) - performance tests")
        self.f = pygame.font.SysFont("arial", 22)
        self.fs = pygame.font.SysFont("arial", 16)
        self.fb = pygame.font.SysFont("arial", 40, bold=True)
        self.feed = Feed()
        start_listener(self.feed)
        self.mode = "menu"
        self.msg = ""
        self.acc = {}            # (row,col) -> dict
        self.reach = []          # dicts
        self.safety = []         # dicts
        self.trial = None        # current trial state

    # ---------------- drawing helpers
    def text(self, s, pos, font=None, col=INK, center=False):
        img = (font or self.f).render(s, True, col)
        r = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
        self.screen.blit(img, r)

    def draw_field(self, target=None, heat=None):
        pygame.draw.rect(self.screen, (34, 37, 45), GRID)
        if heat:
            for rc, v in heat.items():
                k = max(0.0, min(1.0, (v - 50) / 45))      # 50% or less = red, 95%+ = green
                c = tuple(int(BAD[i] + (GOOD[i] - BAD[i]) * k) for i in range(3))
                pygame.draw.rect(self.screen, c, cell_rect(rc))
                self.text(f"{v:.0f}%", cell_rect(rc).center, self.fb, (20, 20, 20), True)
        if target:
            pygame.draw.rect(self.screen, TARGET, cell_rect(target), 6)
        for i in range(1, 3):
            x = GRID.x + GRID.w * i / 3
            y = GRID.y + GRID.h * i / 3
            pygame.draw.line(self.screen, LINE, (x, GRID.y), (x, GRID.bottom), 2)
            pygame.draw.line(self.screen, LINE, (GRID.x, y), (GRID.right, y), 2)
        pygame.draw.rect(self.screen, LINE, GRID, 2)
        self.text("FRONT SENSOR SIDE  (LEFT / RIGHT on the sides)", (GRID.centerx, GRID.y - 18), self.fs, SOFT, True)
        if self.feed.live() and heat is None:
            d, lat, _ = self.feed.read()
            x, y = fractions(d, lat)
            pygame.draw.circle(self.screen, DOT, (int(GRID.x + x * GRID.w), int(GRID.y + y * GRID.h)), 14)

    def status_bar(self):
        live = self.feed.live()
        self.text("tracker: LIVE" if live else "tracker: NO DATA - is sensor_to_processing_osc.py running?",
                  (20, H - 30), self.fs, GOOD if live else BAD)
        if self.feed.frames:
            v = [100.0 * x / self.feed.frames for x in self.feed.valid]
            self.text(f"valid readings F/L/R {v[0]:.0f}/{v[1]:.0f}/{v[2]:.0f} %", (560, H - 30), self.fs, SOFT)

    # ---------------- menu
    def draw_menu(self):
        self.text("V1 (Week 5) performance tests", (W // 2, 50), self.fb, INK, True)
        lines = [
            f"1   Accuracy test    ({len(self.acc)}/9 squares done)",
            f"2   Reach-time test  ({len(self.reach)} trials done)",
            f"3   Safety test      ({len(self.safety)} trials done)",
            "S   Save results (CSV + summary + heatmap)",
            "ESC quit",
        ]
        for i, l in enumerate(lines):
            self.text(l, (250, 130 + i * 44))
        self.draw_mini_field()
        if self.msg:
            self.text(self.msg, (W // 2, 560), self.fs, TARGET, True)

    def draw_mini_field(self):
        if self.feed.live():
            d, lat, raw = self.feed.read()
            self.text(f"now: {cell_name(cell_of(d, lat))}   depth {d:.0f}cm   lateral {lat:.2f}   "
                      f"raw F/L/R {raw[0]:.0f}/{raw[1]:.0f}/{raw[2]:.0f}", (W // 2, 380), self.fs, SOFT, True)

    # ---------------- trials
    def start_accuracy(self):
        todo = [(r, c) for r in range(3) for c in range(3) if (r, c) not in self.acc]
        if not todo:
            self.acc.clear()
            todo = [(r, c) for r in range(3) for c in range(3)]
        self.mode = "acc"
        self.trial = {"target": todo[0], "phase": "ready"}

    def start_reach(self):
        self.mode = "reach"
        self.trial = {"phase": "ready", "n": 0}

    def start_safety(self):
        plan = [("inside", "left side of the dead-zone"), ("inside", "centre of the dead-zone"),
                ("inside", "right side of the dead-zone"), ("outside", "middle of the play area"),
                ("outside", "far-left of the play area"), ("outside", "far-right of the play area")]
        self.mode = "safety"
        self.trial = {"plan": plan, "i": 0, "phase": "ready"}

    def update_acc(self, now):
        t = self.trial
        if t["phase"] == "settle" and now - t["t0"] >= SETTLE_S:
            t.update(phase="record", t0=now, frames=0, hits=0, drops=0, xs=[], ys=[], cells={})
        elif t["phase"] == "record":
            if self.feed.live():
                d, lat, _ = self.feed.read()
                rc = cell_of(d, lat)
                x, y = fractions(d, lat)
                t["frames"] += 1
                t["hits"] += rc == t["target"]
                t["cells"][rc] = t["cells"].get(rc, 0) + 1
                t["xs"].append(x * PLAY_WIDTH_CM)
                t["ys"].append(y * PLAY_DEPTH_CM)
            else:
                t["drops"] += 1
            if now - t["t0"] >= RECORD_S:
                n = max(1, t["frames"])
                wrong = {cell_name(k): v for k, v in t["cells"].items() if k != t["target"]}
                self.acc[t["target"]] = {
                    "accuracy": 100.0 * t["hits"] / n,
                    "jitter_x_cm": statistics.pstdev(t["xs"]) if len(t["xs"]) > 1 else 0.0,
                    "jitter_y_cm": statistics.pstdev(t["ys"]) if len(t["ys"]) > 1 else 0.0,
                    "frames": t["frames"], "dropouts": t["drops"],
                    "wrong_cells": ";".join(f"{k}:{v}" for k, v in wrong.items()),
                }
                self.start_accuracy() if len(self.acc) < 9 else self.finish("Accuracy test done")

    def update_reach(self, now):
        t = self.trial
        if t["phase"] != "go":
            return
        d, lat, _ = self.feed.read()
        inside = self.feed.live() and cell_of(d, lat) == t["target"]
        if inside and t.get("in_since") is None:
            t["in_since"] = now
        if not inside:
            t["in_since"] = None
        if t.get("in_since") and now - t["in_since"] >= REACH_HOLD_S:
            self.reach.append({"from": cell_name(t["from"]), "to": cell_name(t["target"]),
                               "reach_s": t["in_since"] - t["t0"], "ok": True})
            self.next_reach()
        elif now - t["t0"] > REACH_TIMEOUT_S:
            self.reach.append({"from": cell_name(t["from"]), "to": cell_name(t["target"]),
                               "reach_s": REACH_TIMEOUT_S, "ok": False})
            self.next_reach()

    def next_reach(self):
        t = self.trial
        t["n"] += 1
        if t["n"] >= REACH_TRIALS:
            self.finish("Reach-time test done")
        else:
            t["phase"] = "ready"

    def go_reach(self, now):
        d, lat, _ = self.feed.read()
        here = cell_of(d, lat)
        choices = [(r, c) for r in range(3) for c in range(3) if (r, c) != here]
        self.trial.update(phase="go", t0=now, target=random.choice(choices), **{"from": here}, in_since=None)

    def update_safety(self, now):
        t = self.trial
        if t["phase"] == "settle" and now - t["t0"] >= SETTLE_S:
            t.update(phase="record", t0=now, frames=0, warn=0)
        elif t["phase"] == "record":
            if self.feed.live():
                _, _, raw = self.feed.read()
                front = raw[0]
                t["frames"] += 1
                t["warn"] += 0 < front < SAFETY_CM     # V1 rule: FRONT sensor only
            if now - t["t0"] >= RECORD_S:
                kind, where = t["plan"][t["i"]]
                n = max(1, t["frames"])
                warned_pct = 100.0 * t["warn"] / n
                passed = warned_pct >= 50 if kind == "inside" else warned_pct < 5
                self.safety.append({"zone": kind, "position": where,
                                    "warning_on_pct": warned_pct, "pass": passed})
                t["i"] += 1
                if t["i"] >= len(t["plan"]):
                    self.finish("Safety test done")
                else:
                    t["phase"] = "ready"

    def finish(self, msg):
        self.mode, self.trial, self.msg = "menu", None, msg + " - press S to save"

    # ---------------- per-mode screens
    def draw_trial(self, now):
        t = self.trial
        if self.mode == "acc":
            self.draw_field(t["target"])
            self.text(f"Accuracy: stand in the {cell_name(t['target'])} square "
                      f"({len(self.acc) + 1}/9)", (W // 2, 30), center=True)
            self.trial_prompt(t, now)
        elif self.mode == "reach":
            self.draw_field(t.get("target") if t["phase"] == "go" else None)
            self.text(f"Reach time: trial {t['n'] + 1}/{REACH_TRIALS}", (W // 2, 30), center=True)
            if t["phase"] == "ready":
                self.text("Stand anywhere, then press SPACE", (W // 2, 70), self.fs, SOFT, True)
            else:
                self.text(f"GO!  ->  {cell_name(t['target'])}   {now - t['t0']:.1f}s",
                          (W // 2, 70), self.f, TARGET, True)
        elif self.mode == "safety":
            kind, where = t["plan"][t["i"]]
            self.draw_field()
            label = (f"Stand INSIDE the 60cm dead-zone, {where}" if kind == "inside"
                     else f"Stand in the play area, {where} (should NOT warn)")
            self.text(f"Safety {t['i'] + 1}/{len(t['plan'])}: {label}", (W // 2, 30), self.fs, INK, True)
            self.trial_prompt(t, now)

    def trial_prompt(self, t, now):
        if t["phase"] == "ready":
            self.text("Get in position, then press SPACE", (W // 2, 70), self.fs, SOFT, True)
        elif t["phase"] == "settle":
            self.text(f"Hold still... recording in {SETTLE_S - (now - t['t0']):.1f}s",
                      (W // 2, 70), self.fs, TARGET, True)
        else:
            self.text(f"RECORDING  {RECORD_S - (now - t['t0']):.1f}s", (W // 2, 70), self.f, BAD, True)

    # ---------------- saving
    def save(self):
        out = Path(__file__).resolve().parent / "results_V1"
        out.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        with open(out / f"{stamp}_trials.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["test", "target_or_position", "metric", "value", "extra"])
            for rc, r in sorted(self.acc.items()):
                for k in ("accuracy", "jitter_x_cm", "jitter_y_cm", "frames", "dropouts"):
                    w.writerow(["accuracy", cell_name(rc), k, f"{r[k]:.2f}" if isinstance(r[k], float) else r[k],
                                r["wrong_cells"] if k == "accuracy" else ""])
            for r in self.reach:
                w.writerow(["reach", f"{r['from']}->{r['to']}", "reach_s", f"{r['reach_s']:.2f}",
                            "ok" if r["ok"] else "timeout"])
            for r in self.safety:
                w.writerow(["safety", f"{r['zone']}: {r['position']}", "warning_on_pct",
                            f"{r['warning_on_pct']:.1f}", "PASS" if r["pass"] else "FAIL"])
            if self.feed.frames:
                for name, v in zip(("FRONT", "LEFT", "RIGHT"), self.feed.valid):
                    w.writerow(["valid_readings", name, "valid_pct", f"{100.0 * v / self.feed.frames:.1f}",
                                f"{v}/{self.feed.frames} frames"])

        lines = [f"ENGG3000 V1 (Week 5) performance results - {datetime.now():%d %b %Y %H:%M}", ""]
        if self.acc:
            accs = [r["accuracy"] for r in self.acc.values()]
            jit = [max(r["jitter_x_cm"], r["jitter_y_cm"]) for r in self.acc.values()]
            lines += ["POSITION ACCURACY (correct square, % of frames)",
                      f"  mean {statistics.mean(accs):.1f}%   worst {min(accs):.1f}%   "
                      f"squares >= 90%: {sum(a >= 90 for a in accs)}/{len(accs)}",
                      f"  position jitter: mean {statistics.mean(jit):.1f} cm, worst {max(jit):.1f} cm"]
            for rc in sorted(self.acc):
                r = self.acc[rc]
                lines.append(f"    {cell_name(rc):14} {r['accuracy']:5.1f}%   jitter {r['jitter_x_cm']:.1f}/"
                             f"{r['jitter_y_cm']:.1f} cm   mis-reads: {r['wrong_cells'] or '-'}")
            lines.append("")
        if self.reach:
            ok = [r["reach_s"] for r in self.reach if r["ok"]]
            lines += ["REACH TIME (GO -> locked into target square; includes walking)",
                      f"  {len(ok)}/{len(self.reach)} reached"
                      + (f"   median {statistics.median(ok):.2f}s   best {min(ok):.2f}s   worst {max(ok):.2f}s"
                         if ok else ""), ""]
        if self.safety:
            ins = [r for r in self.safety if r["zone"] == "inside"]
            outs = [r for r in self.safety if r["zone"] == "outside"]
            lines += ["SAFETY DEAD-ZONE (V1 rule: FRONT sensor under 60 cm)",
                      f"  detected when inside: {sum(r['pass'] for r in ins)}/{len(ins)}",
                      f"  false alarms in play area: {sum(not r['pass'] for r in outs)}/{len(outs)}", ""]
        if self.feed.frames:
            v = [100.0 * x / self.feed.frames for x in self.feed.valid]
            lines += ["SENSOR DATA (USB serial, free-running boards)",
                      f"  valid readings FRONT/LEFT/RIGHT: {v[0]:.1f} / {v[1]:.1f} / {v[2]:.1f} %",
                      f"  ({self.feed.frames} position updates logged)"]
        (out / f"{stamp}_summary.txt").write_text("\n".join(lines) + "\n")

        if self.acc:
            self.screen.fill(BG)
            self.draw_field(heat={rc: r["accuracy"] for rc, r in self.acc.items()})
            self.text("Position accuracy per square (% of frames correct)", (W // 2, 40), self.f, INK, True)
            pygame.image.save(self.screen, str(out / f"{stamp}_accuracy_heatmap.png"))
        self.msg = f"Saved to results_V1/{stamp}_*"
        print("\n".join(lines))

    # ---------------- loop
    def run(self):
        clock = pygame.time.Clock()
        while True:
            now = time.time()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type != pygame.KEYDOWN:
                    continue
                if e.key == pygame.K_ESCAPE:
                    if self.mode == "menu":
                        return
                    self.finish("Test stopped")
                elif self.mode == "menu":
                    if e.key == pygame.K_1:
                        self.start_accuracy()
                    elif e.key == pygame.K_2:
                        self.start_reach()
                    elif e.key == pygame.K_3:
                        self.start_safety()
                    elif e.key == pygame.K_s:
                        self.save()
                elif e.key == pygame.K_SPACE and self.trial and self.trial["phase"] == "ready":
                    if self.mode == "reach":
                        self.go_reach(now)
                    else:
                        self.trial.update(phase="settle", t0=now)

            if self.mode == "acc":
                self.update_acc(now)
            elif self.mode == "reach":
                self.update_reach(now)
            elif self.mode == "safety":
                self.update_safety(now)

            self.screen.fill(BG)
            if self.mode == "menu":
                self.draw_menu()
            else:
                self.draw_trial(now)
            self.status_bar()
            pygame.display.flip()
            clock.tick(60)


if __name__ == "__main__":
    App().run()
    pygame.quit()