"""
sensor_ui.py - extra screens drawn by the launcher on top of the team's game
==========================================================================
The team's game file is never edited. play_with_sensors.py calls these:

  SETUP PAGE         H on the title / Sensor Check screen. Overhead diagram
                     of where each box goes, with real measurements, matching
                     the tape marks on the floor.

  CALIBRATION CHECK  Replaces the Sensor Check screen when the sensors are
                     live. Shows each box: connected?, update rate, reply %,
                     live distance, and whether it can SEE the player standing
                     on the centre X. Play only starts once every box has
                     seen the player (or C to skip / F for 3-sensor mode).

  REDUCED COVERAGE   Banner during play when running on 3 sensors, or when a
                     box drops out mid-game.
"""

import math
import time

import pygame

_FONTS = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _FONTS:
        _FONTS[key] = pygame.font.SysFont("arial", size, bold=bold)
    return _FONTS[key]


OK = (55, 165, 85)
BAD = (205, 70, 60)
WARN = (225, 150, 40)
INK = (40, 34, 28)
SOFT = (95, 85, 75)
WALL = (70, 70, 80)
DEAD = (240, 120, 100)
PLAY = (150, 205, 120)
BOX_COLOURS = [(46, 134, 222), (16, 172, 132), (238, 82, 83), (247, 159, 31),
               (130, 90, 200), (90, 90, 90)]


def _text(surface, txt, pos, size=18, colour=INK, bold=False, anchor="center"):
    img = font(size, bold).render(str(txt), True, colour)
    rect = img.get_rect(**{anchor: pos})
    surface.blit(img, rect)
    return rect


def _panel(game, w, h, y=None):
    sw, sh = game.SCREEN_WIDTH, game.SCREEN_HEIGHT
    w, h = min(w, sw - 30), min(h, sh - 30)
    rect = pygame.Rect(0, 0, w, h)
    rect.centerx = sw // 2
    rect.y = (sh - h) // 2 if y is None else y
    try:
        game.draw_glass_panel(surface_for_panel[0], rect, radius=20)
    except Exception:
        pass
    return rect


surface_for_panel = [None]


def _dim_background(game, surface, now, alpha=120):
    try:
        game.draw_background(surface, now)
    except Exception:
        surface.fill((220, 230, 240))
    veil = pygame.Surface((game.SCREEN_WIDTH, game.SCREEN_HEIGHT), pygame.SRCALPHA)
    veil.fill((255, 255, 255, alpha))
    surface.blit(veil, (0, 0))


# ------------------------------------------------------------------ FLOOR MAP
def draw_floor_map(surface, rect, geo, player_cm=None, sees=None, spot_cm=None,
                   labels=True):
    """
    Overhead view, wall/screen at the TOP, player area below.
    geo: dict with width, deadzone, depth, sensors [(name, x_cm)].
    player_cm: (x, y) cm to draw a player dot.  sees: list of bools per sensor.
    """
    width, dead, depth = geo["width"], geo["deadzone"], geo["depth"]
    total = dead + depth
    margin_x = 48 if labels else 10
    margin_top = 34 if labels else 14
    scale = min((rect.w - 2 * margin_x) / width, (rect.h - margin_top - (26 if labels else 8)) / total)
    ox = rect.centerx - width * scale / 2
    oy = rect.y + margin_top

    def p(x_cm, y_cm):
        return (int(ox + x_cm * scale), int(oy + y_cm * scale))

    # zones
    pygame.draw.rect(surface, DEAD, (*p(0, 0), int(width * scale), int(dead * scale)))
    pygame.draw.rect(surface, PLAY, (*p(0, dead), int(width * scale), int(depth * scale)))
    # 3 x 3 grid of the game's holes
    for i in (1, 2):
        x = p(width * i / 3, 0)[0]
        pygame.draw.line(surface, (110, 160, 90), (x, p(0, dead)[1]), (x, p(0, total)[1]), 1)
        y = p(0, dead + depth * i / 3)[1]
        pygame.draw.line(surface, (110, 160, 90), (p(0, 0)[0], y), (p(width, 0)[0], y), 1)
    pygame.draw.rect(surface, INK, (*p(0, 0), int(width * scale), int(total * scale)), 2)
    # wall + screen
    pygame.draw.line(surface, WALL, p(-8, 0), p(width + 8, 0), 6)
    # sensor beams (+-15 deg) faintly, then boxes
    beam = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    t15 = math.tan(math.radians(15))
    for i, (name, x) in enumerate(geo["sensors"]):
        colour = BOX_COLOURS[i % len(BOX_COLOURS)]
        tip = p(x, 0)
        left = p(max(0, x - total * t15), total)
        right = p(min(width, x + total * t15), total)
        pygame.draw.polygon(beam, (*colour, 38), [tip, left, right])
    surface.blit(beam, (0, 0))
    for i, (name, x) in enumerate(geo["sensors"]):
        colour = BOX_COLOURS[i % len(BOX_COLOURS)]
        bx, by = p(x, 0)
        box = pygame.Rect(0, 0, max(14, int(10 * scale)), max(12, int(8 * scale)))
        box.midtop = (bx, by - 3)
        pygame.draw.rect(surface, colour, box, border_radius=3)
        pygame.draw.rect(surface, INK, box, 1, border_radius=3)
        if sees is not None and i < len(sees):
            mark = OK if sees[i] else BAD
            pygame.draw.circle(surface, mark, (bx, box.bottom + 9), 6)
        if labels:
            _text(surface, name, (bx, box.top - 2), 13, colour, True, "midbottom")
    # centre X
    if spot_cm is not None:
        cx, cy = p(*spot_cm)
        r = max(6, int(6 * scale))
        pygame.draw.line(surface, (180, 30, 30), (cx - r, cy - r), (cx + r, cy + r), 3)
        pygame.draw.line(surface, (180, 30, 30), (cx - r, cy + r), (cx + r, cy - r), 3)
    if player_cm is not None:
        pygame.draw.circle(surface, (30, 30, 30), p(*player_cm), max(6, int(9 * scale)))
        pygame.draw.circle(surface, (255, 255, 255), p(*player_cm), max(3, int(5 * scale)))
    return p, scale


def _dim_line(surface, a, b, label, colour=INK, side="above"):
    pygame.draw.line(surface, colour, a, b, 1)
    for end in (a, b):
        if a[1] == b[1]:
            pygame.draw.line(surface, colour, (end[0], end[1] - 5), (end[0], end[1] + 5), 1)
        else:
            pygame.draw.line(surface, colour, (end[0] - 5, end[1]), (end[0] + 5, end[1]), 1)
    mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
    if a[1] == b[1]:
        _text(surface, label, (mid[0], mid[1] - 3 if side == "above" else mid[1] + 3), 13, colour,
              anchor="midbottom" if side == "above" else "midtop")
    else:
        img = font(13).render(label, True, colour)
        img = pygame.transform.rotate(img, 90)
        surface.blit(img, img.get_rect(midright=(mid[0] - 4, mid[1])))


# ------------------------------------------------------------------ SETUP PAGE
def draw_setup_page(game, surface, now, geo, settings):
    surface_for_panel[0] = surface
    _dim_background(game, surface, now, 150)
    sw, sh = game.SCREEN_WIDTH, game.SCREEN_HEIGHT
    panel = _panel(game, sw - 30, sh - 24, 12)
    _text(surface, "Setup guide - where the boxes go", (panel.centerx, panel.y + 26), 26, INK, True)

    wide = panel.w >= 760
    if wide:
        map_rect = pygame.Rect(panel.x + 20, panel.y + 50, int(panel.w * 0.52), panel.h - 70)
        notes_x, notes_y, notes_w = map_rect.right + 26, panel.y + 70, panel.right - map_rect.right - 40
    else:
        map_rect = pygame.Rect(panel.x + 20, panel.y + 50, panel.w - 40, int(panel.h * 0.55))
        notes_x, notes_y, notes_w = panel.x + 30, map_rect.bottom + 16, panel.w - 60

    spot = settings["calibration_spot_cm"]
    p, scale = draw_floor_map(surface, map_rect, geo, spot_cm=spot)
    width, dead, depth = geo["width"], geo["deadzone"], geo["depth"]

    # dimensions
    top = p(0, 0)[1]
    _dim_line(surface, (p(0, 0)[0], top - 26), (p(width, 0)[0], top - 26), f"{width:.0f} cm")
    _dim_line(surface, (p(0, 0)[0] - 18, top), (p(0, dead)[0] - 18, p(0, dead)[1]), f"{dead:.0f} cm dead zone", BAD)
    _dim_line(surface, (p(0, 0)[0] - 18, p(0, dead)[1]), (p(0, dead + depth)[0] - 18, p(0, dead + depth)[1]),
              f"{depth:.0f} cm play area", (60, 120, 40))
    mid_dead = p(width / 2, dead / 2)
    _text(surface, "WALL + SCREEN along the top edge", (mid_dead[0], mid_dead[1] - 9), 13, INK, True)
    _text(surface, "DEAD ZONE - alarm + red warning", (mid_dead[0], mid_dead[1] + 9), 13, (120, 20, 20), True)
    sx, sy = p(*spot)
    _text(surface, f"X = {spot[0]:.0f} cm across, {spot[1]:.0f} cm out", (sx, sy + 12), 12, (180, 30, 30), True, "midtop")

    # notes
    lines = [("BOXES - centre of each box, measured", True),
             ("from the LEFT edge (facing the screen):", True)]
    for i, (name, x) in enumerate(geo["sensors"]):
        lines.append((f"   {name:<6} centre at {x:.0f} cm", False, BOX_COLOURS[i % len(BOX_COLOURS)]))
    lines += [
        ("", False),
        ("- Front of each box flush with the wall (0 cm)", False),
        (f"- All at the same height, about {settings['box_height_cm']:.0f} cm (waist)", False),
        ("- Pointing STRAIGHT out, not angled", False),
        ("", False),
        ("TAPE ON THE FLOOR", True),
        (f"- Dead-zone line: {dead:.0f} cm from the wall", False),
        (f"- Back edge: {dead + depth:.0f} cm from the wall", False),
        (f"- Side edges: 0 and {width:.0f} cm", False),
        (f"- Centre X: {spot[0]:.0f} cm across, {spot[1]:.0f} cm out", False),
        ("", False),
        ("Nothing may sit inside the play area, and every", False),
        ("box must be within 50 cm of the wall.", False),
        ("", False),
        ("H or SPACE: close", True),
    ]
    y = notes_y
    for entry in lines:
        txt, bold = entry[0], entry[1]
        colour = entry[2] if len(entry) > 2 else (INK if bold else SOFT)
        if txt:
            _text(surface, txt, (notes_x, y), 15, colour, bold, "topleft")
        y += 21 if txt else 9


# ------------------------------------------------------------------ CALIBRATION
class Calibration:
    """Per-sensor 'can it see the player on the centre X?' check, latched."""

    def __init__(self, geo, settings):
        self.geo = geo
        self.spot = settings["calibration_spot_cm"]
        self.tol = settings["calibration_tolerance_cm"]
        self.hold = settings["calibration_hold_s"]
        self.reset()

    def reset(self):
        n = len(self.geo["sensors"])
        self.seen = [False] * n          # latched ticks
        self.since = [None] * n          # when the current good streak began
        self.skipped = False             # C: skip the standing check
        self.fallback = False            # F: run on 3 sensors

    def expected(self, i):
        x = self.geo["sensors"][i][1]
        return math.hypot(self.spot[0] - x, self.spot[1])

    def update(self, raw, boards):
        now = time.time()
        for i in range(len(self.seen)):
            d = raw[i] if i < len(raw) else -1
            online = i < len(boards) and boards[i]
            good = online and d > 0 and abs(d - self.expected(i)) <= self.tol
            if good:
                if self.since[i] is None:
                    self.since[i] = now
                if now - self.since[i] >= self.hold:
                    self.seen[i] = True
            else:
                self.since[i] = None

    def online_count(self, boards):
        return sum(1 for i in range(len(self.seen)) if i < len(boards) and boards[i])

    def ready(self, boards):
        n = len(self.seen)
        online = [i < len(boards) and bool(boards[i]) for i in range(n)]
        if all(online) and (all(self.seen) or self.skipped):
            return True
        if self.fallback and sum(online) == n - 1:
            return all(self.seen[i] or self.skipped for i in range(n) if online[i])
        return False


def draw_calibration(game, surface, now, geo, cal, feed_snapshot, stats):
    surface_for_panel[0] = surface
    depth, lateral, raw, boards = feed_snapshot
    cal.update(raw, boards)
    _dim_background(game, surface, now, 110)
    sw, sh = game.SCREEN_WIDTH, game.SCREEN_HEIGHT
    panel = _panel(game, 860, 470)
    _text(surface, "Sensor Check & Calibration", (panel.centerx, panel.y + 30), 30, INK, True)
    spot = cal.spot
    _text(surface, f"Stand on the centre X  ({spot[0]:.0f} cm across, {spot[1]:.0f} cm from the wall)",
          (panel.centerx, panel.y + 64), 17, SOFT)

    n = len(geo["sensors"])
    wide = panel.w >= 760
    rows_x = panel.x + 26
    rows_w = int(panel.w * 0.56) if wide else panel.w - 52
    y0 = panel.y + 96
    _text(surface, "Box", (rows_x + 28, y0), 14, SOFT, True, "midleft")
    _text(surface, "Link", (rows_x + 150, y0), 14, SOFT, True, "midleft")
    _text(surface, "Distance", (rows_x + 300, y0), 14, SOFT, True, "midleft")
    _text(surface, "Sees you?", (rows_x + rows_w - 4, y0), 14, SOFT, True, "midright")
    hz = stats.get("hz", [])
    ok = stats.get("ok", [])
    for i, (name, x) in enumerate(geo["sensors"]):
        y = y0 + 34 + i * 46
        online = i < len(boards) and boards[i]
        colour = BOX_COLOURS[i % len(BOX_COLOURS)]
        pygame.draw.circle(surface, OK if online else BAD, (rows_x + 10, y), 9)
        _text(surface, name, (rows_x + 28, y), 19, colour, True, "midleft")
        if online:
            link = f"{hz[i]:.0f} Hz  {ok[i]:.0f}%" if i < len(hz) and i < len(ok) else "connected"
            _text(surface, link, (rows_x + 150, y), 16, INK, False, "midleft")
        else:
            _text(surface, "NOT CONNECTED", (rows_x + 150, y), 16, BAD, True, "midleft")
        d = raw[i] if i < len(raw) else -1
        exp = cal.expected(i)
        dist = f"{d:.0f} cm (want ~{exp:.0f})" if d > 0 else f"--  (want ~{exp:.0f})"
        _text(surface, dist, (rows_x + 300, y), 16, INK if d > 0 else SOFT, False, "midleft")
        cx = rows_x + rows_w - 18
        if cal.seen[i]:
            pygame.draw.circle(surface, OK, (cx, y), 12)
            pygame.draw.lines(surface, (255, 255, 255), False, [(cx - 6, y), (cx - 1, y + 5), (cx + 7, y - 6)], 3)
        elif cal.since[i] is not None:
            frac = min(1.0, (time.time() - cal.since[i]) / max(0.01, cal.hold))
            pygame.draw.circle(surface, (220, 220, 210), (cx, y), 12)
            pygame.draw.arc(surface, OK, (cx - 12, y - 12, 24, 24), math.pi / 2,
                            math.pi / 2 + frac * 2 * math.pi, 4)
        else:
            pygame.draw.circle(surface, (220, 220, 210), (cx, y), 12, 2)

    # mini floor map with the live player dot
    if wide:
        map_rect = pygame.Rect(rows_x + rows_w + 18, y0 - 12, panel.right - (rows_x + rows_w) - 40, n * 46 + 60)
    else:
        map_rect = pygame.Rect(panel.x + 40, y0 + 30 + n * 46, panel.w - 80, 200)
    player = None
    if any(v > 0 for v in raw):
        player = (lateral * geo["width"], geo["deadzone"] + depth)
    draw_floor_map(surface, map_rect, geo, player_cm=player, sees=cal.seen, spot_cm=spot, labels=False)

    # status line
    online = cal.online_count(boards)
    status_y = (map_rect.bottom if not wide else y0 + 34 + n * 46) + 30
    status_y = max(status_y, panel.bottom - 120)
    if cal.ready(boards):
        if cal.fallback:
            msg, colour = "3-sensor mode - reduced coverage. Press SPACE to play", WARN
        elif cal.skipped and not all(cal.seen):
            msg, colour = "Standing check skipped. Press SPACE to play", WARN
        else:
            msg, colour = "Calibration passed - all boxes see you. Press SPACE to play", OK
    elif online < n - 1:
        msg, colour = f"Waiting for boxes... {online} of {n} connected", BAD
    elif online == n - 1:
        missing = [geo["sensors"][i][0] for i in range(n) if not (i < len(boards) and boards[i])]
        msg, colour = f"{missing[0]} not connected - press F to play on {n - 1} sensors (reduced coverage)", WARN
    else:
        left = [geo["sensors"][i][0] for i in range(n) if not cal.seen[i]]
        msg, colour = f"Stand still on the X...  waiting for: {', '.join(left)}", INK
    _text(surface, msg, (panel.centerx, status_y), 19, colour, True)
    _text(surface, "C: skip standing check   |   F: 3-sensor mode   |   R: redo check   |   H: setup guide",
          (panel.centerx, status_y + 30), 14, SOFT)
    _text(surface, "Outer box won't tick? Take a small step back or toward it, then return to the X.",
          (panel.centerx, status_y + 52), 13, SOFT)


# ------------------------------------------------------------------ PLAY BANNER
def draw_coverage_banner(game, surface, geo, boards, fallback):
    n = len(geo["sensors"])
    missing = [geo["sensors"][i][0] for i in range(n) if not (i < len(boards) and boards[i])]
    if not missing and not fallback:
        return
    if missing:
        txt = f"REDUCED COVERAGE - {', '.join(missing)} offline"
    else:
        txt = "REDUCED COVERAGE - 3-sensor mode"
    img = font(16, True).render(txt, True, (255, 255, 255))
    pad = pygame.Rect(0, 0, img.get_width() + 24, img.get_height() + 10)
    pad.midbottom = (game.SCREEN_WIDTH // 2, game.SCREEN_HEIGHT - 8)
    bg = pygame.Surface(pad.size, pygame.SRCALPHA)
    bg.fill((200, 110, 20, 215))
    surface.blit(bg, pad)
    surface.blit(img, img.get_rect(center=pad.center))


def draw_title_hint(game, surface):
    img = font(15, True).render("H: setup guide (where the boxes go)", True, (60, 50, 40))
    pad = pygame.Rect(0, 0, img.get_width() + 20, img.get_height() + 8)
    pad.bottomright = (game.SCREEN_WIDTH - 10, game.SCREEN_HEIGHT - 10)
    bg = pygame.Surface(pad.size, pygame.SRCALPHA)
    bg.fill((255, 255, 255, 190))
    surface.blit(bg, pad)
    surface.blit(img, img.get_rect(center=pad.center))
