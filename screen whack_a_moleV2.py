"""
ENGG3000 - Whack-a-Mole Game
Sprint 1 MVP - Initial Interface (v4, visual polish pass)

Scope (per team scrum plan):
- Basic pygame window with background
- Moving cursor (mouse-driven placeholder, swap to ESP32/sensor input later)
- One mole spawning at a random hole, disappearing after a timeout
- Whack action = single left-click for the prototype. Later this can be
  replaced by the real sensor-detected jump/whack event.
- Score counter + simple fixed-length timer (60s)

v3 added: mole animation states (spawn/idle/hit/missed), spinning star
burst on hit, taunting face + speech bubble on a miss, floating score
popups, combo counter, hit particles, screen shake.

v4 (this pass) is purely a visual/interface upgrade, no new mechanics:
- Mole body now has actual shading (highlight + shadow blobs) instead
  of a flat circle, plus little paws
- Holes have depth shading and a few grass tufts instead of a flat oval
- Background has layered hills + a glowing sun instead of flat shapes
- HUD panels are "glassy" with a soft drop shadow and small icons
  instead of plain rounded rectangles
- A timer bar under the clock that shifts green -> amber -> red
- A proper title screen and a game-over screen with a star rating,
  instead of dropping straight into gameplay

FILE: whack_a_moleV2.py - the team's game, run by play_with_sensors.py with
the 4-sensor tracker (LEFT 18.75 cm, MID 56.25, MID2 93.75, RIGHT 131.25,
all facing straight out).  Can also be run on its own with the mouse.

Names play_with_sensors.py relies on (keep them):
  run_game(), HOLE_POSITIONS, SCREEN_WIDTH, SCREEN_HEIGHT, LEVELS,
  SAFETY_WARNING_DISTANCE_CM, get_player_position(),
  player_is_too_close_to_screen(), sensors_ready(), draw_sensor_calibration(),
  Mole.draw / Mole.contains, and game_to_window() for scaling positions.

Sprint 3 (final product) changes:
- Full screen by default and the picture fills the whole screen (the canvas
  takes the monitor's shape, no black bars).  --windowed for a window.
- The three hole columns / rows line up with the three 50 cm columns and
  three 46.7 cm rows of the 1.5 m x 1.4 m play area.
- Hammer cursor instead of the red dot.
- Safety strip removed from the top of the screen.  The dead-zone warning
  (red overlay) and an audible alarm still fire when a player is within
  60 cm of the screen (required by the brief).
- Four sensors on the Sensor Check screen.
- Every level has its own scenery and colour, with clearer HUD text.

Sprint 2 additions in this version:
- Multiple mole types, reaction bonus, combo score multipliers
- Level transition screens and prototype sensor calibration/status UI
- Real audio remains future work
"""

import os
import pygame
import random
import sys
import math

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Screen orientation (horizontal / vertical screen support)
# ---------------------------------------------------------------------------
# The game is drawn at a fixed "logical" size for each orientation and then
# scaled to fit the real window / monitor, so it looks the same on a laptop,
# a projector or a TV that has been turned on its side.
#
#   ORIENTATION = "auto"       portrait if the monitor is taller than it is wide
#                 "landscape"  always horizontal
#                 "portrait"   always vertical
#
# Can also be chosen from the command line:
#     python whack_a_moleV2.py --portrait
#     python whack_a_moleV2.py --windowed
# and switched live with the O key on the title screen.  F11 toggles fullscreen.
ORIENTATION = "auto"
START_FULLSCREEN = True        # final product runs full screen; --windowed to turn off

# Which screen the game opens on when a TV / projector is plugged in.
#   "auto" = the BIGGEST screen (the TV, not the laptop)
#   0, 1, 2 ... = a specific screen (0 = the laptop's main screen)
# Or from the command line:  python whack_a_moleV2.py --display 1
GAME_DISPLAY = "auto"

LANDSCAPE = "landscape"
PORTRAIT = "portrait"
LOGICAL_SIZES = {
    LANDSCAPE: (900, 650),     # replaced at start-up by fit_canvas_to_monitor()
    PORTRAIT: (650, 1000),
}


def fit_canvas_to_monitor(width, height):
    """
    Give the drawing canvas the same shape as the monitor, so the game fills
    the whole screen with no black bars.  The short side stays 650 px (the
    size every panel was designed for); only the long side changes.
    """
    if width <= 0 or height <= 0:
        return
    if width >= height:
        LOGICAL_SIZES[LANDSCAPE] = (int(max(900, min(1400, round(650 * width / height)))), 650)
        LOGICAL_SIZES[PORTRAIT] = (650, 1000)
    else:
        LOGICAL_SIZES[PORTRAIT] = (650, int(max(1000, min(1400, round(650 * height / width)))))
        LOGICAL_SIZES[LANDSCAPE] = (900, 650)

# These are (re)set by configure_layout() further down.  Everything that
# draws reads them at call time, so switching orientation just means calling
# configure_layout() again.
CURRENT_ORIENTATION = LANDSCAPE
SCREEN_WIDTH, SCREEN_HEIGHT = LOGICAL_SIZES[LANDSCAPE]
FPS = 60

# Mole times are set for FULL-BODY play: the team's reach-time test measured
# 1.8 s median (1.25 best, 4.0 worst) to walk into a square, so a mole has to
# stay up longer than with a mouse.  Each level is still harder than the last.
LEVELS = [
    {
        "name": "Warm Up",
        "time": 60,
        "mole_timeout": 3.5,
        "movement_speed": 1.0,
        "hits_required": 8
    },
    {
        "name": "Quick Whack",
        "time": 60,
        "mole_timeout": 3.0,
        "movement_speed": 1.2,
        "hits_required": 12
    },
    {
        "name": "Mole Rush",
        "time": 60,
        "mole_timeout": 2.5,
        "movement_speed": 1.45,
        "hits_required": 16
    },
    {
        "name": "Expert Mode",
        "time": 60,
        "mole_timeout": 2.0,
        "movement_speed": 1.75,
        "hits_required": 20
    }
]

# ---------------------------------------------------------------------------
# Sprint 2 gameplay add-ons
# ---------------------------------------------------------------------------
# Mole types are chosen randomly.  Keep this PC-side so ESP32 sensor code
# only has to report player position / hit events.
MOLE_TYPES = {
    "normal": {"weight": 70, "base_points": 1, "label": "NORMAL"},
    "golden": {"weight": 15, "base_points": 3, "label": "GOLD +3"},
    "red":    {"weight": 8,  "base_points": -2, "label": "AVOID!"},
    "blue":   {"weight": 7,  "base_points": 1, "label": "TIME +3s"},
}

# Reaction bonus is based on how quickly a valid mole is hit after spawning.
REACTION_FAST_SECONDS = 0.50
REACTION_GOOD_SECONDS = 0.90
REACTION_FAST_BONUS = 2
REACTION_GOOD_BONUS = 1

# Combo multiplier thresholds.
COMBO_X2_AT = 5
COMBO_X3_AT = 10

# Level-transition screen duration.
LEVEL_TRANSITION_MS = 1800

# Prototype sensor status.  Later replace these booleans with UDP health
# checks (for example: sensor is online if a packet arrived in the last second).
DEFAULT_SENSOR_STATUS = {1: True, 2: True, 3: True, 4: True}   # four ultrasonic sensors
# Names match SENSOR_ID on each ESP32 / SENSORS in sensor_to_processing_zoned.py
SENSOR_NAMES = {1: "LEFT", 2: "MID", 3: "MID2", 4: "RIGHT"}

HOLE_RADIUS = 55
MOLE_RADIUS = 45
CURSOR_RADIUS = 10

# Screen safety warning
SAFETY_ZONE_HEIGHT = 0           # the orange strip is gone; HUD starts at the top
SAFETY_WARNING_DISTANCE_CM = 60  # dead zone from the brief: 60 cm out from the wall
ALARM_TEST_KEY = pygame.K_w      # mouse mode: hold W to test the dead-zone alarm

# Prototype input: one left-click counts as a whack.
# Later this click event can be replaced with the ESP32/sensor hit event.

# Mole animation timings (ms unless noted)
MOLE_SPAWN_MS = 150
MOLE_HIT_MS = 650
MOLE_MISS_MS = 700
MOLE_SQUASH_MS = 140            # squash portion at the start of a hit

# Colors
SKY_TOP = (120, 195, 250)
SKY_BOTTOM = (210, 238, 255)
HILL_FAR = (163, 205, 150)
HILL_NEAR = (132, 190, 110)
GROUND_TOP = (150, 214, 100)
GROUND_BOTTOM = (98, 165, 63)
COLOR_HOLE_RIM = (94, 68, 42)
COLOR_HOLE_RIM_DARK = (70, 50, 30)
COLOR_HOLE = (40, 28, 20)
COLOR_HOLE_CENTER = (20, 14, 10)
COLOR_GRASS_TUFT = (86, 156, 60)
COLOR_MOLE = (156, 110, 71)
COLOR_MOLE_DARK = (118, 80, 49)
COLOR_MOLE_LIGHT = (196, 152, 112)
COLOR_MOLE_HIT = (232, 96, 96)
COLOR_MOLE_HIT_LIGHT = (250, 150, 140)
COLOR_MOLE_HIT_DARK = (185, 60, 60)
COLOR_MOLE_GOLD = (238, 190, 55)
COLOR_MOLE_GOLD_LIGHT = (255, 229, 125)
COLOR_MOLE_GOLD_DARK = (180, 125, 25)
COLOR_MOLE_RED = (205, 72, 72)
COLOR_MOLE_RED_LIGHT = (245, 130, 120)
COLOR_MOLE_RED_DARK = (145, 42, 42)
COLOR_MOLE_BLUE = (80, 145, 215)
COLOR_MOLE_BLUE_LIGHT = (145, 200, 250)
COLOR_MOLE_BLUE_DARK = (45, 90, 155)
COLOR_SENSOR_OK = (55, 165, 85)
COLOR_SENSOR_BAD = (205, 70, 60)
COLOR_CURSOR = (220, 30, 30)
COLOR_TEXT = (40, 34, 28)
COLOR_TEXT_SOFT = (90, 80, 70)
COLOR_PANEL = (255, 253, 248)
COLOR_PANEL_BORDER = (215, 197, 168)
COLOR_SUN = (255, 236, 160)
COLOR_SUN_GLOW = (255, 244, 200)
COLOR_CLOUD = (255, 255, 255)
COLOR_SAFETY_ZONE = (242, 169, 89)
COLOR_WARNING = (175, 25, 25)
COLOR_WARNING_PANEL = (255, 248, 245)
COLOR_STAR = (255, 215, 60)
COLOR_STAR_DARK = (235, 170, 30)
COLOR_DUST = (196, 164, 116)
COLOR_POPUP = (255, 200, 40)
COLOR_MISS_BUBBLE = (255, 255, 255)
COLOR_MISS_BUBBLE_BORDER = (200, 60, 60)
COLOR_TIMER_GOOD = (95, 190, 110)
COLOR_TIMER_WARN = (235, 180, 60)
COLOR_TIMER_BAD = (210, 70, 60)
COLOR_TITLE = (60, 42, 28)
COLOR_SHADOW = (20, 20, 25)

# ---------------------------------------------------------------------------
# Level themes - every level gets its own scenery.  Purely visual: the
# gameplay, scoring, add-ons and sensor input are exactly the same.
# THEMES[i] is used for LEVELS[i]; extra levels reuse the last theme.
# ---------------------------------------------------------------------------
THEMES = [
    {   # Level 1 - Warm Up
        "name": "Sunny Meadow",
        "accent": (46, 140, 60),
        "sky": (SKY_TOP, SKY_BOTTOM),
        "hills": (HILL_FAR, HILL_NEAR),
        "ground": (GROUND_TOP, GROUND_BOTTOM),
        "rim": (COLOR_HOLE_RIM, (170, 130, 90), COLOR_HOLE_RIM_DARK),
        "hole": (COLOR_HOLE, COLOR_HOLE_CENTER),
        "tuft": COLOR_GRASS_TUFT,
        "sky_feature": "sun",
        "ground_feature": "flowers",
    },
    {   # Level 2 - Quick Whack
        "name": "Autumn Sunset",
        "accent": (200, 90, 25),
        "sky": ((250, 140, 95), (255, 214, 150)),
        "hills": ((196, 120, 92), (170, 96, 70)),
        "ground": ((214, 168, 82), (168, 112, 52)),
        "rim": ((112, 66, 38), (186, 120, 80), (78, 44, 26)),
        "hole": ((46, 26, 16), (24, 12, 8)),
        "tuft": (178, 98, 40),
        "sky_feature": "sunset",
        "ground_feature": "leaves",
    },
    {   # Level 3 - Mole Rush
        "name": "Moonlit Night",
        "accent": (70, 90, 200),
        "sky": ((16, 22, 58), (52, 62, 120)),
        "hills": ((36, 48, 88), (28, 56, 70)),
        "ground": ((44, 92, 78), (24, 58, 52)),
        "rim": ((70, 58, 52), (120, 110, 120), (44, 36, 34)),
        "hole": ((18, 16, 20), (6, 6, 10)),
        "tuft": (70, 140, 110),
        "sky_feature": "moon",
        "ground_feature": "fireflies",
    },
    {   # Level 4 - Expert Mode
        "name": "Volcano",
        "accent": (205, 45, 25),
        "sky": ((52, 18, 22), (150, 62, 40)),
        "hills": ((70, 34, 34), (52, 28, 30)),
        "ground": ((86, 72, 68), (48, 38, 38)),
        "rim": ((64, 54, 52), (120, 100, 92), (34, 28, 28)),
        "hole": ((26, 14, 12), (60, 16, 6)),
        "tuft": (232, 112, 40),
        "sky_feature": "volcano",
        "ground_feature": "lava",
    },
]

CURRENT_THEME = THEMES[0]


def set_level_theme(level_index):
    """Switch the scenery to match a level (0-based)."""
    global CURRENT_THEME
    index = min(max(0, level_index), len(THEMES) - 1)
    CURRENT_THEME = THEMES[index]

# 3x3 grid of hole positions (placeholder layout for the playing area).
# Same 3x3 grid in both orientations, so the sensor mapping (left/right ->
# column, distance from screen -> row) works identically; only the spacing
# changes.  Top row = closest to the screen in both cases.
GRID_ROWS = 3
GRID_COLS = 3

# Per-orientation layout numbers (logical pixels).
#   margin_x      left/right gap to the outer hole centres
#   margin_y      y of the top row of holes (must clear the safety band + HUD)
#   bottom_margin gap below the bottom row of holes
#   hud_rows      1 = score | level | time in one row, 2 = stacked for narrow screens
# margin_x is a fraction of the width: 1/6 puts the three hole columns in the
# centre of three equal columns, matching the 3 x 50 cm columns on the floor.
LAYOUTS = {
    LANDSCAPE: {"margin_x": 1 / 6, "margin_y": 205, "bottom_margin": 58, "hud_rows": 1},
    PORTRAIT:  {"margin_x": 1 / 6, "margin_y": 265, "bottom_margin": 80, "hud_rows": 2},
}

GRID_MARGIN_X = GRID_MARGIN_Y = GRID_SPACING_X = GRID_SPACING_Y = 0
HUD_ROWS = 1
HOLE_POSITIONS = []
HOLE_TUFTS = {}


def configure_layout(orientation):
    """
    Rebuilds every size/position that depends on the screen shape.

    Call this before creating any Mole: moles copy a hole position when
    they spawn.  play_with_sensors.py re-reads HOLE_POSITIONS every frame, so
    the sensor mapping follows automatically.
    """
    global CURRENT_ORIENTATION, SCREEN_WIDTH, SCREEN_HEIGHT
    global GRID_MARGIN_X, GRID_MARGIN_Y, GRID_SPACING_X, GRID_SPACING_Y
    global HUD_ROWS, HOLE_POSITIONS, HOLE_TUFTS

    if orientation not in LOGICAL_SIZES:
        raise ValueError(f"orientation must be '{LANDSCAPE}' or '{PORTRAIT}', not {orientation!r}")

    layout = LAYOUTS[orientation]
    CURRENT_ORIENTATION = orientation
    SCREEN_WIDTH, SCREEN_HEIGHT = LOGICAL_SIZES[orientation]
    GRID_MARGIN_X = int(round(SCREEN_WIDTH * layout["margin_x"]))
    GRID_MARGIN_Y = layout["margin_y"]
    GRID_SPACING_X = (SCREEN_WIDTH - 2 * GRID_MARGIN_X) // (GRID_COLS - 1)
    GRID_SPACING_Y = (SCREEN_HEIGHT - GRID_MARGIN_Y - layout["bottom_margin"]) // (GRID_ROWS - 1)
    HUD_ROWS = layout["hud_rows"]

    HOLE_POSITIONS = [
        (GRID_MARGIN_X + col * GRID_SPACING_X, GRID_MARGIN_Y + row * GRID_SPACING_Y)
        for row in range(GRID_ROWS)
        for col in range(GRID_COLS)
    ]

    # Fixed per-hole grass tuft layout so it doesn't re-randomize every frame
    rng = random.Random(1234)
    HOLE_TUFTS = {
        pos: [
            (
                rng.uniform(-1, 1) * (HOLE_RADIUS + 12),
                rng.uniform(0.2, 0.5) * HOLE_RADIUS,
                rng.uniform(10, 16),
            )
            for _ in range(6)
        ]
        for pos in HOLE_POSITIONS
    }


def is_portrait():
    return CURRENT_ORIENTATION == PORTRAIT


def screen_y(landscape_y):
    """
    Panels on the overlay screens were placed for a 650 px tall window.
    This keeps them vertically centred on taller (portrait) screens while
    leaving the landscape positions exactly as they were.
    """
    return landscape_y + (SCREEN_HEIGHT - LOGICAL_SIZES[LANDSCAPE][1]) // 2


def centred_panel(width, height, landscape_y):
    """A horizontally centred panel that never runs off a narrow screen."""
    width = min(width, SCREEN_WIDTH - 40)
    return pygame.Rect(SCREEN_WIDTH // 2 - width // 2, screen_y(landscape_y), width, height)


configure_layout(LANDSCAPE)   # sensible default at import time


# ---------------------------------------------------------------------------
# Small easing / helper functions
# ---------------------------------------------------------------------------
def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def ease_out_back(t):
    """A little overshoot so the mole 'pops' out instead of just sliding up."""
    c1 = 1.70158
    c3 = c1 + 1
    t = clamp(t)
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_in_quad(t):
    t = clamp(t)
    return t * t


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    t = clamp(t)
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


# ---------------------------------------------------------------------------
# Sensor input interface (stub)
# ---------------------------------------------------------------------------
def get_player_position(mouse_pos):
    """
    Returns the player's tracked (x, y) position on screen.

    Currently a placeholder driven by the mouse. Once the ESP32 sensor
    boxes are streaming data (serial/UDP), replace this function's body
    with a read from that connection and map it into screen coordinates.
    Keeping this as a single function means the rest of the game code
    doesn't need to change when real sensor input is wired in.
    """
    return mouse_pos


def sensors_ready(sensor_status):
    """True only when all four sensor streams are available."""
    return all(sensor_status.get(sensor_id, False) for sensor_id in DEFAULT_SENSOR_STATUS)


# ---------------------------------------------------------------------------
# Shared visual helpers (shading, glow, glass panels, icons)
# ---------------------------------------------------------------------------
def draw_shaded_ellipse(surface, rect, base_color, light_color, dark_color,
                         light_alpha=140, shadow_alpha=90):
    """
    Flat ellipses read as stickers; this fakes a bit of sphere-like shading
    by layering a soft highlight (top-left) and shadow (bottom-right) blob
    on top of a base fill, all within the ellipse's own footprint.
    """
    x, y, w, h = rect
    pygame.draw.ellipse(surface, base_color, rect)

    shade_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(shade_surf, (*dark_color, shadow_alpha),
                         (w * 0.18, h * 0.20, w * 0.82, h * 0.80))
    pygame.draw.ellipse(shade_surf, (*light_color, light_alpha),
                         (w * 0.06, h * 0.04, w * 0.55, h * 0.42))
    surface.blit(shade_surf, (x, y))


def catmull_rom_closed(points, samples=8):
    """
    Smoothly interpolates a closed loop through a small set of anchor
    points, so a hand-placed silhouette (e.g. a body with ear bumps and
    a snout point) comes out as one continuous organic curve instead of
    a jagged polygon or a stack of separate circles.
    """
    n = len(points)
    curve = []
    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i % n]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            curve.append((x, y))
    return curve


def draw_shaded_polygon(surface, points, base_color, light_color, dark_color,
                         light_pos=(0.32, 0.26), dark_pos=(0.68, 0.78),
                         light_radius_factor=0.62, dark_radius_factor=0.68,
                         light_alpha=150, shadow_alpha=100):
    """
    Fills an arbitrary silhouette (a real body outline, not just a circle)
    and adds a soft highlight/shadow blob clipped to that exact shape, so
    curved, non-circular shapes (the mole's body, ears and all) still read
    as rounded and lit rather than flat.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 2
    w = max(1, int(max_x - min_x) + pad * 2)
    h = max(1, int(max_y - min_y) + pad * 2)
    local_points = [(px - min_x + pad, py - min_y + pad) for px, py in points]

    poly_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(poly_surf, base_color, local_points)

    mask_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask_surf, (255, 255, 255, 255), local_points)

    overlay_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    dx, dy = w * dark_pos[0], h * dark_pos[1]
    lx, ly = w * light_pos[0], h * light_pos[1]
    dr = max(w, h) * dark_radius_factor
    lr = max(w, h) * light_radius_factor
    pygame.draw.circle(overlay_surf, (*dark_color, shadow_alpha), (int(dx), int(dy)), int(dr))
    pygame.draw.circle(overlay_surf, (*light_color, light_alpha), (int(lx), int(ly)), int(lr))

    # clip the highlight/shadow to the silhouette's own alpha so nothing
    # leaks outside the body outline (e.g. into the gaps beside the ears)
    overlay_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    poly_surf.blit(overlay_surf, (0, 0))

    surface.blit(poly_surf, (min_x - pad, min_y - pad))


# Hand-placed silhouette anchors for the mole's body: two ear bumps up top,
# wide shoulders, and a snout point at the bottom. Smoothed once at import
# time into a dense closed curve so per-frame drawing is just a scale +
# translate, not a re-fit of the spline every frame.
_MOLE_BODY_ANCHORS = [
    (0.00, -0.58), (0.30, -0.80), (0.46, -1.05), (0.62, -0.78),
    (0.90, -0.32), (1.00, 0.12), (0.85, 0.55), (0.48, 0.85),
    (0.16, 1.00), (0.00, 1.08), (-0.16, 1.00), (-0.48, 0.85),
    (-0.85, 0.55), (-1.00, 0.12), (-0.90, -0.32), (-0.62, -0.78),
    (-0.46, -1.05), (-0.30, -0.80),
]
MOLE_BODY_SILHOUETTE = catmull_rom_closed(_MOLE_BODY_ANCHORS, samples=8)

_MOLE_PAW_ANCHORS = [
    (-0.9, 0.15), (-0.65, -0.70), (-0.20, -0.50), (0.15, -0.85),
    (0.60, -0.35), (0.90, 0.25), (0.50, 0.85), (-0.50, 0.85),
]
MOLE_PAW_SILHOUETTE = catmull_rom_closed(_MOLE_PAW_ANCHORS, samples=6)


def draw_glow(surface, center, max_radius, color, steps=5, max_alpha=90):
    """Soft concentric-circle glow, used behind the sun / small highlights."""
    glow_surf = pygame.Surface((max_radius * 2, max_radius * 2), pygame.SRCALPHA)
    for i in range(steps, 0, -1):
        t = i / steps
        radius = int(max_radius * t)
        alpha = int(max_alpha * (1 - t) + 6)
        pygame.draw.circle(glow_surf, (*color, alpha), (max_radius, max_radius), radius)
    surface.blit(glow_surf, (center[0] - max_radius, center[1] - max_radius))


def draw_drop_shadow(surface, rect, offset=(0, 4), alpha=45, radius=14):
    shadow_surf = pygame.Surface((rect[2] + 12, rect[3] + 12), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (*COLOR_SHADOW, alpha), (6, 6, rect[2], rect[3]),
                      border_radius=radius)
    surface.blit(shadow_surf, (rect[0] - 6 + offset[0], rect[1] - 6 + offset[1]))


def draw_glass_panel(surface, rect, border_color=COLOR_PANEL_BORDER, radius=16):
    """A softer 'glass' panel: drop shadow, translucent fill, subtle top sheen."""
    draw_drop_shadow(surface, rect, radius=radius)

    panel_surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(panel_surf, (255, 253, 248, 242), (0, 0, rect[2], rect[3]), border_radius=radius)
    surface.blit(panel_surf, (rect[0], rect[1]))
    # soft sheen along the top edge only, blended on top (never behind text)
    sheen = pygame.Surface((max(1, int(rect[2] - 2 * radius)), 3), pygame.SRCALPHA)
    sheen.fill((255, 255, 255, 140))
    surface.blit(sheen, (rect[0] + radius, rect[1] + 4))
    pygame.draw.rect(surface, border_color, rect, width=2, border_radius=radius)


def draw_star_icon(surface, center, size, color=COLOR_STAR, outline=COLOR_STAR_DARK):
    cx, cy = center
    points = []
    for i in range(10):
        radius = size if i % 2 == 0 else size * 0.45
        angle = math.radians(-90 + i * 36)
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    pygame.draw.polygon(surface, color, points)
    pygame.draw.polygon(surface, outline, points, width=1)


def draw_clock_icon(surface, center, size, color=COLOR_TEXT):
    cx, cy = center
    pygame.draw.circle(surface, color, center, size, width=2)
    pygame.draw.line(surface, color, (cx, cy), (cx, cy - size * 0.55), 2)
    pygame.draw.line(surface, color, (cx, cy), (cx + size * 0.4, cy + size * 0.2), 2)


def draw_target_icon(surface, center, size, color=(200, 60, 40)):
    cx, cy = center
    pygame.draw.circle(surface, color, center, size, width=2)
    pygame.draw.circle(surface, color, center, int(size * 0.55), width=2)
    pygame.draw.circle(surface, color, center, 2)


# ---------------------------------------------------------------------------
# Little "juice" effects: floating text, dust puffs, spinning stars
# ---------------------------------------------------------------------------
class FloatingText:
    """A short-lived bit of text that drifts up and fades out (score popups etc)."""

    def __init__(self, pos, text, color, font, life_ms=650, rise=40):
        self.pos = pos
        self.text = text
        self.color = color
        self.font = font
        self.start = pygame.time.get_ticks()
        self.life_ms = life_ms
        self.rise = rise

    def is_dead(self, now):
        return (now - self.start) >= self.life_ms

    def draw(self, surface, now):
        t = clamp((now - self.start) / self.life_ms)
        y_offset = -self.rise * t
        alpha = int(255 * (1 - t))
        label = self.font.render(self.text, True, self.color)
        outline = self.font.render(self.text, True, (30, 22, 18))
        label.set_alpha(alpha)
        outline.set_alpha(alpha)
        rect = label.get_rect(center=(self.pos[0], self.pos[1] + y_offset))
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            surface.blit(outline, rect.move(dx, dy))
        surface.blit(label, rect)


class DustPuff:
    """Little dirt specks that pop out sideways when a mole gets whacked."""

    def __init__(self, pos):
        self.pos = pos
        self.start = pygame.time.get_ticks()
        self.life_ms = 400
        self.particles = []
        for _ in range(8):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 110)
            self.particles.append({
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 40,
                "size": random.randint(2, 4),
            })

    def is_dead(self, now):
        return (now - self.start) >= self.life_ms

    def draw(self, surface, now):
        t = clamp((now - self.start) / self.life_ms)
        alpha = int(220 * (1 - t))
        for p in self.particles:
            x = self.pos[0] + p["vx"] * t
            y = self.pos[1] + p["vy"] * t + 260 * t * t  # gravity-ish arc
            dust_surf = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
            pygame.draw.circle(dust_surf, (*COLOR_DUST, alpha), (p["size"], p["size"]), p["size"])
            surface.blit(dust_surf, (x - p["size"], y - p["size"]))


def draw_star(surface, center, size, angle_deg, color, dark_color, alpha=255):
    """Draws a simple 5-point star rotated by angle_deg, used for the hit burst."""
    cx, cy = center
    points_outer = 5
    star_points = []
    for i in range(points_outer * 2):
        radius = size if i % 2 == 0 else size * 0.45
        angle = math.radians(angle_deg + i * (360 / (points_outer * 2)))
        star_points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

    star_surf = pygame.Surface((size * 3, size * 3), pygame.SRCALPHA)
    offset_points = [(px - cx + size * 1.5, py - cy + size * 1.5) for px, py in star_points]
    pygame.draw.polygon(star_surf, (*color, alpha), offset_points)
    pygame.draw.polygon(star_surf, (*dark_color, alpha), offset_points, width=2)
    surface.blit(star_surf, (cx - size * 1.5, cy - size * 1.5))


class StarBurst:
    """A little ring of stars that spin around above a mole's head after a hit."""

    STAR_COUNT = 4
    ORBIT_RADIUS = 34
    LIFE_MS = MOLE_HIT_MS - MOLE_SQUASH_MS - 50

    def __init__(self, center):
        self.center = center  # point above the mole's head to orbit around
        self.start = pygame.time.get_ticks()
        self.base_angle = random.uniform(0, 360)

    def draw(self, surface, now):
        t = clamp((now - self.start) / self.LIFE_MS)
        # spin fast, fade out towards the end, drift upward a touch
        spin = self.base_angle + (now - self.start) * 0.35
        fade = 1 - ease_in_quad(t)
        alpha = int(255 * fade)
        drift_y = -14 * t
        for i in range(self.STAR_COUNT):
            angle = spin + i * (360 / self.STAR_COUNT)
            rad = math.radians(angle)
            x = self.center[0] + self.ORBIT_RADIUS * math.cos(rad)
            y = self.center[1] + drift_y + (self.ORBIT_RADIUS * 0.45) * math.sin(rad)
            size = 8 + 2 * math.sin(rad * 2)
            draw_star(surface, (x, y), size, spin * 2, COLOR_STAR, COLOR_STAR_DARK, alpha)


# ---------------------------------------------------------------------------
# Mole
# ---------------------------------------------------------------------------
class Mole:
    SPAWNING = "spawning"
    IDLE = "idle"
    HIT = "hit"
    MISSED = "missed"
    HIDDEN = "hidden"

    MISS_LINES = ["Missed me!", "Too slow!", "Ha! Nice try", "Nyeh heh heh"]

    def __init__(self, timeout=2.0, movement_speed=1.0):
        self.position = random.choice(HOLE_POSITIONS)
        self.spawn_time = pygame.time.get_ticks()
        self.state = Mole.SPAWNING
        self.state_time = self.spawn_time
        self.timeout = timeout
        self.movement_speed = movement_speed

        mole_names = list(MOLE_TYPES.keys())
        mole_weights = [MOLE_TYPES[name]["weight"] for name in mole_names]
        self.mole_type = random.choices(mole_names, weights=mole_weights, k=1)[0]

        self.blink_seed = random.uniform(0, 1000)
        self.miss_line = random.choice(Mole.MISS_LINES)
        self.star_burst = None

    def reaction_time_seconds(self, now):
        return max(0.0, (now - self.spawn_time) / 1000.0)

    def base_points(self):
        return MOLE_TYPES[self.mole_type]["base_points"]

    # -- state handling ----------------------------------------------------
    def _elapsed_total(self, now):
        return (now - self.spawn_time) / 1000.0

    def update(self, now):
        spawn_ms = MOLE_SPAWN_MS / self.movement_speed
        hit_ms = MOLE_HIT_MS / self.movement_speed
        miss_ms = MOLE_MISS_MS / self.movement_speed

        if self.state == Mole.SPAWNING and (now - self.state_time) >= spawn_ms:
            self.state = Mole.IDLE
            self.state_time = now
        elif self.state == Mole.IDLE and self._elapsed_total(now) >= self.timeout:
            self.state = Mole.MISSED
            self.state_time = now
        elif self.state == Mole.HIT and (now - self.state_time) >= hit_ms:
            self.state = Mole.HIDDEN
        elif self.state == Mole.MISSED and (now - self.state_time) >= miss_ms:
            self.state = Mole.HIDDEN

    def is_expired(self):
        return self._elapsed_total(pygame.time.get_ticks()) >= self.timeout

    def contains(self, pos):
        # can only actually be whacked while it's up and hasn't already
        # been hit or started its escape animation
        if self.state not in (Mole.SPAWNING, Mole.IDLE):
            return False
        dx = pos[0] - self.position[0]
        dy = pos[1] - self.position[1]
        return (dx ** 2 + dy ** 2) ** 0.5 <= MOLE_RADIUS

    def register_hit(self, now):
        self.state = Mole.HIT
        self.state_time = now
        head_point = (self.position[0], self.position[1] - 10 - MOLE_RADIUS - 10)
        self.star_burst = StarBurst(head_point)

    def should_remove(self):
        return self.state == Mole.HIDDEN

    # -- drawing -------------------------------------------------------
    def draw(self, surface, now):
        x, y = self.position
        base_y = y - 10

        rise = 1.0          # how far "up" the mole is (0 = fully in hole)
        squash_x, squash_y = 1.0, 1.0
        color = COLOR_MOLE
        light, dark = COLOR_MOLE_LIGHT, COLOR_MOLE_DARK
        if self.mole_type == "golden":
            color, light, dark = COLOR_MOLE_GOLD, COLOR_MOLE_GOLD_LIGHT, COLOR_MOLE_GOLD_DARK
        elif self.mole_type == "red":
            color, light, dark = COLOR_MOLE_RED, COLOR_MOLE_RED_LIGHT, COLOR_MOLE_RED_DARK
        elif self.mole_type == "blue":
            color, light, dark = COLOR_MOLE_BLUE, COLOR_MOLE_BLUE_LIGHT, COLOR_MOLE_BLUE_DARK

        face_mode = "happy"
        shake_x = 0

        if self.state == Mole.SPAWNING:
            spawn_ms = MOLE_SPAWN_MS / self.movement_speed
            t = clamp((now - self.state_time) / spawn_ms)
            rise = ease_out_back(t)

        elif self.state == Mole.IDLE:
            bob_period = 260.0 / self.movement_speed
            bob = math.sin((now - self.spawn_time) / bob_period) * 2
            rise = 1.0
            base_y += bob

        elif self.state == Mole.HIT:
            color = COLOR_MOLE_HIT
            light, dark = COLOR_MOLE_HIT_LIGHT, COLOR_MOLE_HIT_DARK
            face_mode = "dizzy"
            squash_ms = MOLE_SQUASH_MS / self.movement_speed
            hit_ms = MOLE_HIT_MS / self.movement_speed
            if (now - self.state_time) < squash_ms:
                squash_phase = clamp((now - self.state_time) / squash_ms)
                squash_x = lerp(1.0, 1.35, math.sin(squash_phase * math.pi))
                squash_y = lerp(1.0, 0.65, math.sin(squash_phase * math.pi))
                rise = 1.0
            else:
                sink_t = clamp((now - self.state_time - squash_ms) /
                                max(1, hit_ms - squash_ms))
                rise = lerp(1.0, 0.0, ease_in_quad(sink_t))

        elif self.state == Mole.MISSED:
            miss_ms = MOLE_MISS_MS / self.movement_speed
            t = clamp((now - self.state_time) / miss_ms)
            face_mode = "taunt"
            if t < 0.65:
                taunt_t = t / 0.65
                shake_x = math.sin(taunt_t * 30) * 2.2
                rise = 1.0
            else:
                sink_t = (t - 0.65) / 0.35
                rise = lerp(1.0, 0.0, ease_in_quad(sink_t))

        if self.state == Mole.HIDDEN:
            return

        body_y = base_y - int(15 * rise) - int(4 * (1 - rise))
        radius_x = MOLE_RADIUS * squash_x
        radius_y = MOLE_RADIUS * squash_y
        cx = x + shake_x

        # clip so the mole visually sinks "into" the hole rather than
        # just shrinking in place
        clip_bottom = y + HOLE_RADIUS // 2 - 4
        old_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(0, 0, SCREEN_WIDTH, clip_bottom))

        # paws, peeking out from behind the body while it's up - a real
        # little mitt shape (via the smoothed silhouette) rather than an oval
        if rise > 0.4:
            paw_y = body_y + radius_y * 0.68
            for side in (-1, 1):
                paw_cx = cx + side * radius_x * 0.72
                paw_points = [
                    (paw_cx + nx * 15 * squash_x, paw_y + ny * 13 * squash_y)
                    for nx, ny in MOLE_PAW_SILHOUETTE
                ]
                draw_shaded_polygon(surface, paw_points, color, light, dark,
                                     light_alpha=90, shadow_alpha=70)

        # body + ears drawn as one continuous, hand-shaped silhouette
        # (see MOLE_BODY_SILHOUETTE) instead of a body circle with ear
        # circles glued on top
        body_points = [
            (cx + nx * radius_x, body_y + ny * radius_y)
            for nx, ny in MOLE_BODY_SILHOUETTE
        ]
        draw_shaded_polygon(surface, body_points, color, light, dark)

        # small pink inner-ear patches at the tip of each ear bump
        for side in (-1, 1):
            ear_tip_x = cx + side * 0.40 * radius_x
            ear_tip_y = body_y - 0.80 * radius_y
            pygame.draw.circle(surface, (205, 150, 140),
                                (int(ear_tip_x), int(ear_tip_y)),
                                max(3, int(radius_x * 0.14)))

        self._draw_face(surface, cx, body_y, radius_x, radius_y, face_mode, now)

        # Small type marker.  The body colour is the main visual cue; this
        # label keeps special moles understandable during demonstrations.
        if self.state in (Mole.SPAWNING, Mole.IDLE):
            type_font = pygame.font.SysFont("arial", 11, bold=True)
            label = type_font.render(MOLE_TYPES[self.mole_type]["label"], True, (45, 35, 25))
            # small light pill behind the text so it reads on every level theme
            pill = label.get_rect(center=(int(cx), int(body_y - radius_y - 10))).inflate(10, 4)
            pill_surf = pygame.Surface(pill.size, pygame.SRCALPHA)
            pygame.draw.rect(pill_surf, (255, 250, 240, 190), pill_surf.get_rect(),
                             border_radius=pill.height // 2)
            surface.blit(pill_surf, pill.topleft)
            surface.blit(label, label.get_rect(center=pill.center))

        surface.set_clip(old_clip)

        # star burst orbits above the head, drawn outside the clip so it
        # doesn't get cut off by the hole
        if self.state == Mole.HIT and self.star_burst is not None:
            self.star_burst.draw(surface, now)

        # taunt speech bubble while missed
        if self.state == Mole.MISSED:
            miss_ms = MOLE_MISS_MS / self.movement_speed
            t = clamp((now - self.state_time) / miss_ms)
            if t < 0.65:
                self._draw_taunt_bubble(surface, cx, body_y - radius_y, t / 0.65)

    def _draw_face(self, surface, cx, body_y, radius_x, radius_y, mode, now):
        if mode == "happy":
            pygame.draw.circle(surface, (60, 40, 30), (int(cx), int(body_y + 12)), 6)
            blink = (math.sin((now + self.blink_seed) / 900.0) > 0.94)
            if blink:
                pygame.draw.line(surface, (30, 20, 15), (cx - 26, body_y - 12), (cx - 12, body_y - 12), 2)
                pygame.draw.line(surface, (30, 20, 15), (cx + 12, body_y - 12), (cx + 26, body_y - 12), 2)
            else:
                pygame.draw.arc(surface, (30, 20, 15), (cx - 24, body_y - 18, 16, 12), 3.6, 6.0, 2)
                pygame.draw.arc(surface, (30, 20, 15), (cx + 8, body_y - 18, 16, 12), 3.6, 6.0, 2)
            for side in (-1, 1):
                for dy in (-4, 2, 8):
                    pygame.draw.line(
                        surface, (40, 30, 20),
                        (cx + side * 22, body_y + dy),
                        (cx + side * 40, body_y + dy - 2), 1
                    )

        elif mode == "dizzy":
            # X_X style eyes for the brief hit flash
            for side in (-1, 1):
                ex = cx + side * 16
                ey = body_y - 12
                pygame.draw.line(surface, (60, 20, 20), (ex - 5, ey - 5), (ex + 5, ey + 5), 2)
                pygame.draw.line(surface, (60, 20, 20), (ex - 5, ey + 5), (ex + 5, ey - 5), 2)
            pygame.draw.arc(surface, (60, 20, 20), (cx - 10, body_y + 6, 20, 12), 3.4, 6.0, 2)

        elif mode == "taunt":
            # the "rage bait" face: big smug eyes + tongue out
            for side in (-1, 1):
                ex = cx + side * 15
                ey = body_y - 14
                pygame.draw.circle(surface, (255, 255, 255), (int(ex), int(ey)), 7)
                pygame.draw.circle(surface, (25, 20, 15), (int(ex + side * 2), int(ey + 1)), 4)
            # smug raised eyebrows
            pygame.draw.line(surface, (30, 20, 15), (cx - 24, body_y - 24), (cx - 8, body_y - 27), 2)
            pygame.draw.line(surface, (30, 20, 15), (cx + 8, body_y - 27), (cx + 24, body_y - 24), 2)
            # nose
            pygame.draw.circle(surface, (60, 40, 30), (int(cx), int(body_y + 10)), 6)
            # tongue sticking out, wagging a little
            wag = math.sin(now / 60.0) * 3
            tongue_rect = (cx - 8 + wag, body_y + 16, 16, 14)
            pygame.draw.ellipse(surface, (220, 90, 110), tongue_rect)

    def _draw_taunt_bubble(self, surface, cx, top_y, t):
        font = pygame.font.SysFont("arial", 16, bold=True)
        label = font.render(self.miss_line, True, COLOR_TEXT)
        pad_x, pad_y = 10, 6
        bubble_w = label.get_width() + pad_x * 2
        bubble_h = label.get_height() + pad_y * 2
        bob = math.sin(t * math.pi) * 4
        bubble_rect = pygame.Rect(0, 0, bubble_w, bubble_h)
        bubble_rect.center = (cx + 55, top_y - 30 - bob)
        alpha = int(255 * clamp(t * 4))  # fade in fast

        bubble_surf = pygame.Surface((bubble_w + 4, bubble_h + 4), pygame.SRCALPHA)
        pygame.draw.rect(bubble_surf, (*COLOR_MISS_BUBBLE, alpha), (2, 2, bubble_w, bubble_h),
                          border_radius=10)
        pygame.draw.rect(bubble_surf, (*COLOR_MISS_BUBBLE_BORDER, alpha), (2, 2, bubble_w, bubble_h),
                          width=2, border_radius=10)
        surface.blit(bubble_surf, bubble_rect.topleft)
        text_surf = label.copy()
        text_surf.set_alpha(alpha)
        surface.blit(text_surf, (bubble_rect.x + pad_x, bubble_rect.y + pad_y))


# ---------------------------------------------------------------------------
# Drawing helpers - background / holes / HUD
# ---------------------------------------------------------------------------
def draw_vertical_gradient(surface, rect, top_color, bottom_color):
    x, y, w, h = rect
    for i in range(h):
        t = i / max(1, h - 1)
        color = tuple(int(top_color[c] + (bottom_color[c] - top_color[c]) * t) for c in range(3))
        pygame.draw.line(surface, color, (x, y + i), (x + w, y + i))


def draw_hill_band(surface, base_y, amplitude, color, phase, y_span):
    """One soft rolling-hill silhouette band, used to give the background depth."""
    points = [(0, base_y + y_span)]
    step = 30
    for px in range(0, SCREEN_WIDTH + step, step):
        py = base_y + math.sin((px / 140.0) + phase) * amplitude
        points.append((px, py))
    points.append((SCREEN_WIDTH, base_y + y_span))
    pygame.draw.polygon(surface, color, points)


_DECOR_CACHE = {}


def _theme_layout(kind, count, y_min, y_max, seed):
    """Fixed random positions for decorations (same every frame, per screen size)."""
    key = (kind, count, SCREEN_WIDTH, SCREEN_HEIGHT, y_min, y_max)
    if key not in _DECOR_CACHE:
        rng = random.Random(seed)
        _DECOR_CACHE[key] = [
            (rng.uniform(0, SCREEN_WIDTH), rng.uniform(y_min, y_max), rng.random(), rng.random())
            for _ in range(count)
        ]
    return _DECOR_CACHE[key]


def _draw_clouds(surface, now, color, y_list):
    drift = (now / 40.0) % (SCREEN_WIDTH + 200)
    for cx, cy in zip((150, 400, 620), y_list):
        cloud_x = (cx + drift) % (SCREEN_WIDTH + 200) - 100
        for dx, dy, r in [(-20, 5, 18), (0, -5, 22), (22, 5, 18)]:
            pygame.draw.circle(surface, color, (int(cloud_x + dx), cy + dy), r)


def _draw_sky_feature(surface, now, theme, sky_height):
    feature = theme["sky_feature"]

    if feature == "sun":
        sun_center = (SCREEN_WIDTH - 90, 100)
        draw_glow(surface, sun_center, 85, COLOR_SUN_GLOW, steps=6, max_alpha=70)
        pygame.draw.circle(surface, COLOR_SUN, sun_center, 42)
        _draw_clouds(surface, now, COLOR_CLOUD, (90, 60, 120))

    elif feature == "sunset":
        # big low sun sinking behind the hills
        sun_center = (SCREEN_WIDTH - 150, sky_height - 10)
        draw_glow(surface, sun_center, 120, (255, 190, 120), steps=6, max_alpha=80)
        pygame.draw.circle(surface, (255, 150, 80), sun_center, 58)
        _draw_clouds(surface, now * 0.6, (255, 196, 186), (70, 45, 95))

    elif feature == "moon":
        for x, y, a, b in _theme_layout("stars", 45, 8, sky_height - 25, 31):
            twinkle = 0.5 + 0.5 * math.sin(now / 400.0 + a * 12)
            shade = int(150 + 105 * twinkle)
            pygame.draw.circle(surface, (shade, shade, min(255, shade + 20)),
                               (int(x), int(y)), 1 if b < 0.7 else 2)
        moon_center = (SCREEN_WIDTH - 100, 70)
        draw_glow(surface, moon_center, 75, (190, 205, 255), steps=5, max_alpha=55)
        pygame.draw.circle(surface, (236, 238, 220), moon_center, 34)
        for dx, dy, r in [(-10, -8, 7), (12, 6, 5), (-4, 14, 4)]:
            pygame.draw.circle(surface, (208, 210, 196),
                               (moon_center[0] + dx, moon_center[1] + dy), r)

    elif feature == "volcano":
        peak_x, peak_y = SCREEN_WIDTH * 0.72, max(30, sky_height - 95)
        base_y = sky_height + 20
        # lava glow behind the crater
        draw_glow(surface, (int(peak_x), int(peak_y)), 90, (255, 120, 50), steps=6,
                  max_alpha=int(60 + 25 * math.sin(now / 300.0)))
        pygame.draw.polygon(surface, (44, 22, 24), [
            (peak_x - 240, base_y), (peak_x - 34, peak_y), (peak_x + 34, peak_y),
            (peak_x + 240, base_y)
        ])
        # lava running down from the crater
        pygame.draw.polygon(surface, (240, 100, 30), [
            (peak_x - 34, peak_y), (peak_x + 34, peak_y),
            (peak_x + 10, peak_y + 30), (peak_x - 6, peak_y + 55), (peak_x - 18, peak_y + 22)
        ])
        # dark smoke clouds
        _draw_clouds(surface, now * 0.5, (70, 54, 56), (50, 30, 70))


def _draw_ground_feature(surface, now, theme, sky_height):
    feature = theme["ground_feature"]
    ground_top = sky_height + 20

    if feature == "flowers":
        petal_colors = [(255, 255, 255), (250, 210, 80), (240, 140, 170), (190, 160, 240)]
        for x, y, a, b in _theme_layout("flowers", 34, ground_top, SCREEN_HEIGHT - 8, 11):
            color = petal_colors[int(a * len(petal_colors)) % len(petal_colors)]
            for angle in range(0, 360, 72):
                rad = math.radians(angle)
                pygame.draw.circle(surface, color,
                                   (int(x + math.cos(rad) * 3), int(y + math.sin(rad) * 3)), 2)
            pygame.draw.circle(surface, (250, 190, 50), (int(x), int(y)), 2)

    elif feature == "leaves":
        leaf_colors = [(205, 92, 40), (230, 150, 50), (170, 70, 35), (240, 190, 70)]

        def leaf(cx, cy, size, angle, color):
            pts = []
            for k, r in enumerate((size, size * 0.45, size, size * 0.45)):
                rad = angle + k * math.pi / 2
                pts.append((cx + math.cos(rad) * r, cy + math.sin(rad) * r))
            pygame.draw.polygon(surface, color, pts)

        # leaves already on the ground
        for x, y, a, b in _theme_layout("leaves", 30, ground_top, SCREEN_HEIGHT - 8, 21):
            leaf(x, y, 5 + b * 3, a * math.pi, leaf_colors[int(b * 4) % 4])
        # a few drifting down
        fall_span = SCREEN_HEIGHT + 40
        for x, y, a, b in _theme_layout("falling", 12, 0, fall_span, 22):
            fy = (y + now * (0.03 + b * 0.03)) % fall_span - 20
            fx = x + math.sin(now / 600.0 + a * 6) * 25
            leaf(fx, fy, 6, now / 500.0 + a * 6, leaf_colors[int(a * 4) % 4])

    elif feature == "fireflies":
        # moonlight pooling on the grass
        draw_glow(surface, (SCREEN_WIDTH - 100, ground_top + 40), 220, (120, 150, 200),
                  steps=5, max_alpha=30)
        for x, y, a, b in _theme_layout("fireflies", 22, ground_top, SCREEN_HEIGHT - 20, 41):
            fx = x + math.sin(now / 900.0 + a * 9) * 30
            fy = y + math.cos(now / 700.0 + b * 9) * 18
            blink = 0.5 + 0.5 * math.sin(now / 350.0 + a * 20)
            if blink > 0.2:
                draw_glow(surface, (int(fx), int(fy)), 16, (210, 255, 120), steps=4,
                          max_alpha=int(140 * blink))
                pygame.draw.circle(surface, (245, 255, 190), (int(fx), int(fy)), 3)

    elif feature == "lava":
        pulse = 0.5 + 0.5 * math.sin(now / 350.0)
        crack_outer = lerp_color((150, 40, 20), (230, 90, 30), pulse)
        crack_inner = lerp_color((240, 120, 40), (255, 210, 110), pulse)
        for x, y, a, b in _theme_layout("cracks", 9, ground_top + 10, SCREEN_HEIGHT - 15, 51):
            rng = random.Random(int(a * 10000))
            pts = [(x, y)]
            for _ in range(4):
                px, py = pts[-1]
                pts.append((px + rng.uniform(15, 35) * (1 if b > 0.5 else -1),
                            py + rng.uniform(-10, 10)))
            pygame.draw.lines(surface, crack_outer, False, pts, 4)
            pygame.draw.lines(surface, crack_inner, False, pts, 1)
        # embers floating up
        rise_span = SCREEN_HEIGHT - ground_top + 60
        for x, y, a, b in _theme_layout("embers", 22, 0, rise_span, 52):
            ey = SCREEN_HEIGHT - (y + now * (0.04 + b * 0.05)) % rise_span
            ex = x + math.sin(now / 500.0 + a * 7) * 12
            draw_glow(surface, (int(ex), int(ey)), 7, (255, 140, 50), steps=2, max_alpha=90)
            pygame.draw.circle(surface, (255, 150 + int(80 * a), 60), (int(ex), int(ey)), 2)


def draw_background(surface, now):
    theme = CURRENT_THEME
    sky_height = GRID_MARGIN_Y - 90
    draw_vertical_gradient(surface, (0, 0, SCREEN_WIDTH, sky_height), *theme["sky"])

    _draw_sky_feature(surface, now, theme, sky_height)

    # rolling hills for a bit of depth before the flat playing field
    hill_far, hill_near = theme["hills"]
    hill_base = sky_height - 6
    draw_hill_band(surface, hill_base, 10, hill_far, phase=0.6, y_span=60)
    draw_hill_band(surface, hill_base + 14, 14, hill_near, phase=2.1, y_span=60)

    ground_rect = (0, sky_height, SCREEN_WIDTH, SCREEN_HEIGHT - sky_height)
    draw_vertical_gradient(surface, ground_rect, *theme["ground"])

    _draw_ground_feature(surface, now, theme, sky_height)


def draw_holes(surface):
    for pos in HOLE_POSITIONS:
        x, y = pos
        # soft shadow beneath the mound
        shadow_surf = pygame.Surface((HOLE_RADIUS * 2 + 30, HOLE_RADIUS + 30), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (20, 30, 10, 55), shadow_surf.get_rect())
        surface.blit(shadow_surf, (x - HOLE_RADIUS - 15, y - HOLE_RADIUS // 2 + 10))

        # rim, shaded so it reads as a raised mound of dirt
        rim_rect = (x - HOLE_RADIUS - 4, y - HOLE_RADIUS // 2 - 3, HOLE_RADIUS * 2 + 8, HOLE_RADIUS + 6)
        rim_base, rim_light, rim_dark = CURRENT_THEME["rim"]
        draw_shaded_ellipse(surface, rim_rect, rim_base, rim_light, rim_dark,
                             light_alpha=90, shadow_alpha=70)

        # dark hole opening with a darker centre for a bit of depth
        hole_rect = (x - HOLE_RADIUS, y - HOLE_RADIUS // 2, HOLE_RADIUS * 2, HOLE_RADIUS)
        hole_color, hole_centre = CURRENT_THEME["hole"]
        pygame.draw.ellipse(surface, hole_color, hole_rect)
        inner_rect = (x - HOLE_RADIUS * 0.55, y - HOLE_RADIUS * 0.22,
                      HOLE_RADIUS * 1.1, HOLE_RADIUS * 0.55)
        pygame.draw.ellipse(surface, hole_centre, inner_rect)

        # a few little grass tufts around the rim for texture
        for tx, ty, size in HOLE_TUFTS[pos]:
            gx, gy = x + tx, y + ty + HOLE_RADIUS // 2
            for blade in (-1, 0, 1):
                pygame.draw.line(
                    surface, CURRENT_THEME["tuft"],
                    (gx + blade * 3, gy),
                    (gx + blade * 5, gy - size),
                    2
                )


def _rotated(points, pivot, angle_deg):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    px, py = pivot
    return [(px + (x - px) * ca - (y - py) * sa, py + (x - px) * sa + (y - py) * ca)
            for x, y in points]


def draw_cursor(surface, pos, hit_flash):
    """
    Hammer cursor.  The ring on the ground marks exactly where the player is
    (that is the spot that whacks); the hammer floats above it, raised, and
    swings down when a whack lands.
    """
    if pos is None:
        return
    x, y = pos
    theme_ring = CURRENT_THEME.get("accent", (255, 255, 255))

    # target ring on the ground
    ring = pygame.Surface((70, 36), pygame.SRCALPHA)
    pygame.draw.ellipse(ring, (0, 0, 0, 70), ring.get_rect())
    pygame.draw.ellipse(ring, (*theme_ring, 255), ring.get_rect().inflate(-6, -6), 3)
    pygame.draw.ellipse(ring, (255, 255, 255, 230), ring.get_rect().inflate(-14, -12), 2)
    surface.blit(ring, (x - 35, y - 18))

    # hammer: pivot is the bottom of the handle, raised (-35 deg) or striking (+25 deg)
    angle = 25 if hit_flash else -35
    pivot = (x + 26, y + 4)
    handle = [(pivot[0] - 4, pivot[1]), (pivot[0] + 4, pivot[1]),
              (pivot[0] + 4, pivot[1] - 64), (pivot[0] - 4, pivot[1] - 64)]
    head = [(pivot[0] - 30, pivot[1] - 84), (pivot[0] + 22, pivot[1] - 84),
            (pivot[0] + 22, pivot[1] - 58), (pivot[0] - 30, pivot[1] - 58)]
    face = [(pivot[0] - 30, pivot[1] - 84), (pivot[0] - 22, pivot[1] - 84),
            (pivot[0] - 22, pivot[1] - 58), (pivot[0] - 30, pivot[1] - 58)]
    band = [(pivot[0] - 6, pivot[1] - 66), (pivot[0] + 6, pivot[1] - 66),
            (pivot[0] + 6, pivot[1] - 58), (pivot[0] - 6, pivot[1] - 58)]

    def big(points, k=1.35):
        return [(pivot[0] + (px - pivot[0]) * k, pivot[1] + (py - pivot[1]) * k) for px, py in points]

    handle, head, face, band = big(handle), big(head), big(face), big(band)
    shadow = [(px + 4, py + 4) for px, py in _rotated(head, pivot, angle)]
    sx, sy = min(p[0] for p in shadow), min(p[1] for p in shadow)
    shadow_surf = pygame.Surface((int(max(p[0] for p in shadow) - sx) + 2,
                                  int(max(p[1] for p in shadow) - sy) + 2), pygame.SRCALPHA)
    pygame.draw.polygon(shadow_surf, (0, 0, 0, 60), [(px - sx, py - sy) for px, py in shadow])
    surface.blit(shadow_surf, (sx, sy))

    pygame.draw.polygon(surface, (150, 98, 52), _rotated(handle, pivot, angle))
    pygame.draw.polygon(surface, (92, 58, 30), _rotated(handle, pivot, angle), 2)
    pygame.draw.polygon(surface, (120, 124, 134), _rotated(head, pivot, angle))
    pygame.draw.polygon(surface, (170, 175, 186), _rotated(face, pivot, angle))
    pygame.draw.polygon(surface, (60, 62, 70), _rotated(head, pivot, angle), 2)
    pygame.draw.polygon(surface, (200, 60, 50), _rotated(band, pivot, angle))


def draw_hammer_hit(surface, pos, t):
    """
    A quick little hammer-head flash at the whack point when a whack lands.
    t goes 0 -> 1 over the effect's short lifetime.
    """
    swing = ease_in_quad(t)
    handle_len = 34
    angle = lerp(-70, -10, swing)  # swinging down into the hit
    rad = math.radians(angle)
    hx, hy = pos[0] - handle_len * math.cos(rad), pos[1] - handle_len * math.sin(rad)
    alpha = int(255 * (1 - t))

    hammer_surf = pygame.Surface((80, 80), pygame.SRCALPHA)
    origin = (40, 40)
    tip = (40 + (hx - pos[0]), 40 + (hy - pos[1]))
    pygame.draw.line(hammer_surf, (120, 80, 40, alpha), origin, tip, 6)
    head_w, head_h = 26, 14
    head_surf_rect = pygame.Rect(0, 0, head_w, head_h)
    head_surf_rect.center = tip
    pygame.draw.rect(hammer_surf, (90, 90, 95, alpha), head_surf_rect, border_radius=3)
    surface.blit(hammer_surf, (pos[0] - 40, pos[1] - 40))


def player_is_too_close_to_screen(player_pos):
    """
    True when the player is inside the 60 cm dead zone.

    play_with_sensors.py replaces this with the real distance from the
    ultrasonic sensors.  With the mouse, hold W to test the warning + alarm.
    """
    try:
        return bool(pygame.key.get_pressed()[ALARM_TEST_KEY])
    except pygame.error:
        return False


class SafetyAlarm:
    """
    Audible dead-zone alarm: a fast two-tone beep from the PC speakers while
    the player is too close.  The tone is generated in code (no sound file),
    and if the PC has no audio device the game simply carries on silently.
    """
    BEEP_EVERY_MS = 260

    def __init__(self):
        self.sound = None
        self.next_beep = 0
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1)
            freq, _, channels = pygame.mixer.get_init()
            import array
            samples = array.array("h")
            for tone_hz, length_s in ((1400, 0.09), (1000, 0.09)):
                for i in range(int(freq * length_s)):
                    value = 9000 if math.sin(2 * math.pi * tone_hz * i / freq) >= 0 else -9000
                    for _ in range(channels):
                        samples.append(value)
            self.sound = pygame.mixer.Sound(buffer=samples.tobytes())
        except (pygame.error, ImportError, ValueError, TypeError) as error:
            print(f"[alarm] no audio device ({error}) - visual warning only")

    def update(self, active, now):
        if not active:
            self.next_beep = 0
            return
        if self.sound is not None and now >= self.next_beep:
            self.sound.play()
            self.next_beep = now + self.BEEP_EVERY_MS


def draw_safety_warning(surface, _font=None, now=0):
    # pulsing red wash + thick flashing border so it is seen from across the room
    pulse = 0.5 + 0.5 * math.sin(now / 120.0)
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((200, 30, 30, int(60 + 50 * pulse)))
    pygame.draw.rect(overlay, (230, 30, 30, 230), overlay.get_rect(), width=int(10 + 8 * pulse))
    surface.blit(overlay, (0, 0))

    font_big = pygame.font.SysFont("arial", 38, bold=True)
    one_line = font_big.render("WARNING  MOVE AWAY FROM THE SCREEN", True, COLOR_WARNING)
    if one_line.get_width() + 60 <= SCREEN_WIDTH - 40:
        lines = [one_line]
    else:
        # narrow (portrait) screen: split over two lines instead of clipping
        lines = [font_big.render("WARNING", True, COLOR_WARNING),
                 font_big.render("MOVE AWAY FROM THE SCREEN", True, COLOR_WARNING)]

    line_gap = 8
    text_h = sum(l.get_height() for l in lines) + line_gap * (len(lines) - 1)
    panel_w = min(860, SCREEN_WIDTH - 40)
    panel_h = max(130, text_h + 50)
    panel = pygame.Rect(SCREEN_WIDTH // 2 - panel_w // 2, SCREEN_HEIGHT // 2 - panel_h // 2,
                        panel_w, panel_h)
    draw_glass_panel(surface, panel, border_color=COLOR_WARNING, radius=14)

    y = panel.centery - text_h // 2
    for line in lines:
        surface.blit(line, line.get_rect(midtop=(panel.centerx, y)))
        y += line.get_height() + line_gap


def draw_hud(surface, font, small_font, score, time_remaining, combo,
             level_number, level_name, hits_this_level, hits_required, level_time):
    panel_y = SAFETY_ZONE_HEIGHT + 12
    panel_height = 58

    if HUD_ROWS == 1:
        # landscape: score | level | time across one row (original layout)
        side_panel_width = 185
        centre_panel_width = 390
        score_panel = pygame.Rect(20, panel_y, side_panel_width, panel_height)
        instruction_panel = pygame.Rect(
            SCREEN_WIDTH // 2 - centre_panel_width // 2, panel_y, centre_panel_width, panel_height
        )
        time_panel = pygame.Rect(
            SCREEN_WIDTH - side_panel_width - 20, panel_y, side_panel_width, panel_height
        )
    else:
        # portrait: score and time side by side, level/progress full width below
        gap = 12
        half_width = (SCREEN_WIDTH - 40 - gap) // 2
        score_panel = pygame.Rect(20, panel_y, half_width, panel_height)
        time_panel = pygame.Rect(SCREEN_WIDTH - 20 - half_width, panel_y, half_width, panel_height)
        instruction_panel = pygame.Rect(
            20, panel_y + panel_height + gap, SCREEN_WIDTH - 40, panel_height
        )

    accent = CURRENT_THEME.get("accent", COLOR_PANEL_BORDER)
    draw_glass_panel(surface, score_panel, border_color=accent)
    draw_glass_panel(surface, instruction_panel, border_color=accent)
    draw_glass_panel(surface, time_panel, border_color=accent)

    draw_star_icon(surface, (score_panel.x + 26, score_panel.centery), 12)
    score_text = font.render(f"{score}", True, COLOR_TEXT)
    surface.blit(score_text, (score_panel.x + 44, score_panel.centery - score_text.get_height() // 2))

    # Level name + progress. Combo is shown on the progress line when active.
    level_text = pygame.font.SysFont("arial", 22, bold=True).render(
        f"LEVEL {level_number}  {level_name}", True, accent
    )
    progress_label = f"Hits {hits_this_level}/{hits_required}"
    if combo >= COMBO_X3_AT:
        score_multiplier = 3
    elif combo >= COMBO_X2_AT:
        score_multiplier = 2
    else:
        score_multiplier = 1
    if combo >= 2:
        progress_label += f"   Combo {combo} | Score x{score_multiplier}"
    progress_text = pygame.font.SysFont("arial", 16, bold=True).render(
        progress_label, True, (190, 50, 30) if combo >= 2 else COLOR_TEXT
    )
    surface.blit(
        level_text,
        level_text.get_rect(center=(instruction_panel.centerx, instruction_panel.centery - 10))
    )
    surface.blit(
        progress_text,
        progress_text.get_rect(center=(instruction_panel.centerx, instruction_panel.centery + 13))
    )

    draw_clock_icon(surface, (time_panel.x + 26, time_panel.centery - 4), 11)
    time_text = font.render(f"{max(0, int(time_remaining))}s", True, COLOR_TEXT)
    surface.blit(time_text, (time_panel.x + 44, time_panel.centery - 4 - time_text.get_height() // 2))

    # Timer bar uses the current level's duration.
    frac = clamp(time_remaining / max(1, level_time))
    bar_rect = pygame.Rect(time_panel.x + 14, time_panel.bottom - 10, time_panel.width - 28, 6)
    pygame.draw.rect(surface, (0, 0, 0, 30), bar_rect, border_radius=3)
    if frac > 0.5:
        bar_color = lerp_color(COLOR_TIMER_WARN, COLOR_TIMER_GOOD, (frac - 0.5) * 2)
    else:
        bar_color = lerp_color(COLOR_TIMER_BAD, COLOR_TIMER_WARN, frac * 2)
    fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, int(bar_rect.width * frac), bar_rect.height)
    pygame.draw.rect(surface, bar_color, fill_rect, border_radius=3)


def draw_title_screen(surface, now, font_title, font_small):
    draw_background(surface, now)
    draw_holes(surface)

    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, 70))
    surface.blit(overlay, (0, 0))

    # a friendly mole peeking up out of the middle hole as decoration,
    # using the same body silhouette as in-game (not a stack of ellipses)
    bob = math.sin(now / 350.0) * 6
    mid_x, mid_y = SCREEN_WIDTH // 2, GRID_MARGIN_Y + GRID_SPACING_Y + int(bob)
    deco_rx, deco_ry = 62, 58
    deco_points = [
        (mid_x + nx * deco_rx, mid_y - 20 + ny * deco_ry)
        for nx, ny in MOLE_BODY_SILHOUETTE
    ]
    draw_shaded_polygon(surface, deco_points, COLOR_MOLE, COLOR_MOLE_LIGHT, COLOR_MOLE_DARK)
    for side in (-1, 1):
        ear_tip_x = mid_x + side * 0.40 * deco_rx
        ear_tip_y = mid_y - 20 - 0.80 * deco_ry
        pygame.draw.circle(surface, (205, 150, 140), (int(ear_tip_x), int(ear_tip_y)),
                            max(3, int(deco_rx * 0.14)))
    pygame.draw.circle(surface, (60, 40, 30), (mid_x, mid_y - 6), 7)
    pygame.draw.arc(surface, (30, 20, 15), (mid_x - 30, mid_y - 32, 20, 15), 3.6, 6.0, 2)
    pygame.draw.arc(surface, (30, 20, 15), (mid_x + 10, mid_y - 32, 20, 15), 3.6, 6.0, 2)

    panel = centred_panel(520, 110, 90)
    panel.y = 90   # keep the title up in the sky in both orientations
    draw_glass_panel(surface, panel, radius=20)
    title_text = font_title.render("WHACK-A-MOLE", True, COLOR_TITLE)
    subtitle_text = font_small.render("Full-body Whack-a-Mole  -  ENGG3000", True, COLOR_TEXT_SOFT)
    surface.blit(title_text, title_text.get_rect(center=(panel.centerx, panel.centery - 16)))
    surface.blit(subtitle_text, subtitle_text.get_rect(center=(panel.centerx, panel.centery + 24)))

    prompt_alpha = int(150 + 105 * math.sin(now / 300.0))
    prompt = pygame.font.SysFont("arial", 24, bold=True).render(
        "Click anywhere or press SPACE to start", True, COLOR_TEXT)
    prompt_surf = prompt.copy()
    prompt_surf.set_alpha(prompt_alpha)
    # sit the prompt on a pill in the gap between the middle and bottom rows,
    # so it is never drawn across a hole
    prompt_y = GRID_MARGIN_Y + int(GRID_SPACING_Y * 1.5) - 10
    hint_y = prompt_y + 34
    pill = pygame.Rect(0, 0, max(prompt.get_width(), 470) + 50, 82)
    pill.center = (SCREEN_WIDTH // 2, prompt_y + 16)
    draw_glass_panel(surface, pill, radius=18)
    surface.blit(prompt_surf, prompt_surf.get_rect(center=(SCREEN_WIDTH // 2, prompt_y)))

    other = "landscape" if is_portrait() else "portrait"
    hint = pygame.font.SysFont("arial", 15).render(
        f"O: {other} screen   |   F11: full screen   |   hold W: test alarm", True, COLOR_TEXT_SOFT
    )
    surface.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, hint_y)))


def draw_sensor_calibration(surface, now, font_big, font_small, sensor_status):
    """Status screen for the four ultrasonic sensors (live in sensor mode)."""
    draw_background(surface, now)
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, 105))
    surface.blit(overlay, (0, 0))

    panel = centred_panel(600, 420, 110)
    draw_glass_panel(surface, panel, radius=20)

    title = font_big.render("Sensor Check", True, COLOR_TITLE)
    surface.blit(title, title.get_rect(center=(panel.centerx, panel.y + 55)))

    subtitle = font_small.render(
        "ESP32 / ultrasonic status before gameplay", True, COLOR_TEXT_SOFT
    )
    surface.blit(subtitle, subtitle.get_rect(center=(panel.centerx, panel.y + 95)))

    for index, sensor_id in enumerate(DEFAULT_SENSOR_STATUS):
        online = sensor_status.get(sensor_id, False)
        y = panel.y + 140 + index * 48
        color = COLOR_SENSOR_OK if online else COLOR_SENSOR_BAD
        pygame.draw.circle(surface, color, (panel.x + 115, y), 12)
        status_word = "CONNECTED" if online else "NOT CONNECTED"
        name = SENSOR_NAMES.get(sensor_id, str(sensor_id))
        text = font_small.render(f"Sensor {sensor_id} ({name}): {status_word}", True, COLOR_TEXT)
        surface.blit(text, (panel.x + 145, y - text.get_height() // 2))

    if sensors_ready(sensor_status):
        message = "All sensors ready - press SPACE to continue"
        color = COLOR_SENSOR_OK
    else:
        message = f"Waiting for all {len(DEFAULT_SENSOR_STATUS)} sensors..."
        color = COLOR_SENSOR_BAD

    msg = font_small.render(message, True, color)
    surface.blit(msg, msg.get_rect(center=(panel.centerx, panel.bottom - 70)))

    test_note = pygame.font.SysFont("arial", 14).render(
        "Mouse test mode: keys 1-4 toggle sensor status", True, COLOR_TEXT_SOFT
    )
    surface.blit(test_note, test_note.get_rect(center=(panel.centerx, panel.bottom - 35)))


def draw_level_transition(surface, now, font_big, font_small, level_number, level):
    draw_background(surface, now)
    draw_holes(surface)
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((20, 25, 30, 115))
    surface.blit(overlay, (0, 0))

    panel = centred_panel(540, 270, 170)
    draw_glass_panel(surface, panel, radius=22)

    heading = font_big.render(f"LEVEL {level_number}", True,
                              CURRENT_THEME.get("accent", COLOR_TITLE))
    name = font_small.render(f"{level['name']}  -  {CURRENT_THEME['name']}", True, COLOR_TEXT)
    target = font_small.render(
        f"Target: {level['hits_required']} hits   |   Mole speed x{level['movement_speed']}",
        True, COLOR_TEXT_SOFT
    )
    prompt = font_small.render("Get ready!", True, (200, 80, 45))

    surface.blit(heading, heading.get_rect(center=(panel.centerx, panel.y + 65)))
    surface.blit(name, name.get_rect(center=(panel.centerx, panel.y + 120)))
    surface.blit(target, target.get_rect(center=(panel.centerx, panel.y + 165)))
    surface.blit(prompt, prompt.get_rect(center=(panel.centerx, panel.y + 220)))


def draw_game_over(surface, now, font_big, font_small, score, won=False):
    draw_background(surface, now)
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 15, 25, 130))
    surface.blit(overlay, (0, 0))

    panel = centred_panel(460, 260, 170)
    draw_glass_panel(surface, panel, radius=20)

    title = "You Win!" if won else "Time's Up!"
    over_text = font_big.render(title, True, COLOR_TEXT)
    score_text = font_small.render(f"Final Score: {score}", True, COLOR_TEXT)
    restart_text = font_small.render("Press R to play again, or ESC to quit", True, COLOR_TEXT_SOFT)

    surface.blit(over_text, over_text.get_rect(center=(SCREEN_WIDTH // 2, panel.y + 45)))
    surface.blit(score_text, score_text.get_rect(center=(SCREEN_WIDTH // 2, panel.y + 95)))

    # 0-3 star rating adjusted for the four-level game.
    thresholds = [25, 50, 80]
    stars_earned = sum(1 for t in thresholds if score >= t)
    for i in range(3):
        cx = SCREEN_WIDTH // 2 - 50 + i * 50
        cy = panel.y + 150
        color = COLOR_STAR if i < stars_earned else (215, 210, 200)
        outline = COLOR_STAR_DARK if i < stars_earned else (180, 175, 165)
        draw_star_icon(surface, (cx, cy), 20, color, outline)

    surface.blit(restart_text, restart_text.get_rect(center=(SCREEN_WIDTH // 2, panel.y + 210)))


# ---------------------------------------------------------------------------
# Display: window sizing, scaling and orientation switching
# ---------------------------------------------------------------------------
def _screen_sizes():
    try:
        return list(pygame.display.get_desktop_sizes())
    except (AttributeError, pygame.error):
        return []


def chosen_display():
    """
    Index of the screen the game should use: --display N on the command line,
    else GAME_DISPLAY; "auto" picks the biggest screen, so with a TV plugged
    into a laptop the game goes on the TV.
    """
    sizes = _screen_sizes()
    if not sizes:
        return 0
    choice = GAME_DISPLAY
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg.lower() in ("--display", "--screen") and i + 1 < len(argv):
            choice = argv[i + 1]
        elif arg.lower().startswith(("--display=", "--screen=")):
            choice = arg.split("=", 1)[1]
    if str(choice).isdigit() and int(choice) < len(sizes):
        return int(choice)
    return max(range(len(sizes)), key=lambda k: sizes[k][0] * sizes[k][1])


def desktop_size():
    """Size of the screen the game runs on (see chosen_display)."""
    sizes = _screen_sizes()
    if sizes:
        return sizes[chosen_display()]
    info = pygame.display.Info()
    return info.current_w, info.current_h


def _set_mode(size, flags):
    """set_mode on the chosen screen (older pygame without display= falls back)."""
    try:
        return pygame.display.set_mode(size, flags, display=chosen_display())
    except TypeError:
        return pygame.display.set_mode(size, flags)


# Used only if the Mac's real menu bar / Dock area can't be read: room to leave
# at the top (menu bar, incl. the notch) and bottom (Dock), in screen points.
MAC_FALLBACK_TOP = 38
MAC_FALLBACK_BOTTOM = 80
_USABLE_AREA = None


def _mac_visible_frame():
    """
    Asks macOS (NSScreen.visibleFrame) which part of the CHOSEN screen (laptop
    or TV) is not covered by its menu bar or the Dock.  Returns (x, y, w, h)
    in SDL's global coordinates (origin = top-left of the main screen, y down),
    so the window lands on the right screen.  None if it can't be read.
    Plain ctypes, so nothing extra to pip install.
    """
    import ctypes
    import ctypes.util
    import platform

    class NSRect(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                    ("w", ctypes.c_double), ("h", ctypes.c_double)]

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary(ctypes.util.find_library("AppKit"))
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]

    def send(func_name, restype, *extra):
        addr = ctypes.cast(getattr(objc, func_name), ctypes.c_void_p).value
        return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *extra)(addr)

    send_ptr = send("objc_msgSend", ctypes.c_void_p)
    send_count = send("objc_msgSend", ctypes.c_ulong)
    send_index = send("objc_msgSend", ctypes.c_void_p, ctypes.c_ulong)
    # Intel Macs return big structs through objc_msgSend_stret; Apple Silicon doesn't.
    send_rect = send("objc_msgSend" if platform.machine() == "arm64" else "objc_msgSend_stret",
                     NSRect)
    sel = objc.sel_registerName

    screens = send_ptr(objc.objc_getClass(b"NSScreen"), sel(b"screens"))
    if not screens:
        return None
    count = send_count(screens, sel(b"count"))
    found = []                      # (frame_w, frame_h, visible rect in SDL coords)
    main_h = None
    for i in range(count):
        screen = send_index(screens, sel(b"objectAtIndex:"), i)
        frame = send_rect(screen, sel(b"frame"))
        vis = send_rect(screen, sel(b"visibleFrame"))
        if main_h is None:          # screen 0 = the one with the menu bar
            main_h = frame.y + frame.h
        found.append((frame.w, frame.h,
                      (int(round(vis.x)), int(round(main_h - (vis.y + vis.h))),
                       int(vis.w), int(vis.h))))
    if not found:
        return None

    # Match the screen SDL is using by its size (the index order can differ).
    want_w, want_h = desktop_size()
    index = chosen_display()
    matches = [k for k, (w, h, _) in enumerate(found)
               if abs(w - want_w) <= 2 and abs(h - want_h) <= 2]
    if not matches:
        return None
    pick = index if index in matches else matches[0]
    area = found[pick][2]
    if area[2] < 200 or area[3] < 200:
        return None
    return area


def usable_area():
    """
    (x, y, w, h) of the screen area the game may cover.  On Windows/Linux real
    full screen covers everything.  On a Mac the game uses a borderless window,
    which the menu bar and Dock are drawn ON TOP of, so it must stay between them.
    """
    global _USABLE_AREA
    if _USABLE_AREA is not None:
        return _USABLE_AREA
    width, height = desktop_size()
    area = (0, 0, width, height)
    if sys.platform == "darwin":
        try:
            area = _mac_visible_frame() or None
        except Exception as error:      # any ctypes/AppKit problem -> safe guess
            print(f"[display] couldn't read the menu bar/Dock size ({error})")
            area = None
        if area is None and chosen_display() == 0:
            area = (0, MAC_FALLBACK_TOP, width,
                    height - MAC_FALLBACK_TOP - MAC_FALLBACK_BOTTOM)
        elif area is None:
            # TV but its position couldn't be read: let SDL centre the window
            # on that screen instead (x/y None, see Display.apply).
            area = (None, None, width, height)
        print(f"[display] Mac: game area {area[2]}x{area[3]} at ({area[0]}, {area[1]}) "
              f"- clear of the menu bar and Dock")
    _USABLE_AREA = area
    return area


def resolve_orientation(choice):
    """Turns 'auto' into landscape/portrait based on the monitor's shape."""
    if choice in (LANDSCAPE, PORTRAIT):
        return choice
    width, height = desktop_size()
    return PORTRAIT if height > width else LANDSCAPE


def parse_command_line(argv):
    """
    Optional flags: --portrait / --vertical, --landscape / --horizontal,
    --auto, --fullscreen, --windowed.  Anything else is ignored, so
    play_with_sensors.py can pass its own arguments through.
    """
    orientation, fullscreen = ORIENTATION, START_FULLSCREEN
    for arg in argv:
        arg = arg.lower()
        if arg in ("--portrait", "--vertical"):
            orientation = PORTRAIT
        elif arg in ("--landscape", "--horizontal"):
            orientation = LANDSCAPE
        elif arg == "--auto":
            orientation = "auto"
        elif arg == "--fullscreen":
            fullscreen = True
        elif arg == "--windowed":
            fullscreen = False
    return orientation, fullscreen


class Display:
    """
    Owns the real window.  The game always draws to `canvas`, which is
    exactly SCREEN_WIDTH x SCREEN_HEIGHT; present() scales it to fit the
    window (keeping its shape, with dark bars if the window is a different
    shape) and to_game() converts mouse positions back the other way.
    """

    def __init__(self, fullscreen=False):
        self.fullscreen = fullscreen
        self.window = None
        self.canvas = None
        self.scale = 1.0
        self.offset = (0, 0)
        self.windowed_size = None
        self.apply()

    def _fit_windowed_size(self):
        """Biggest window with the game's shape that fits on the desktop."""
        desk_w, desk_h = desktop_size()
        # leave room for the taskbar and title bar
        max_w, max_h = int(desk_w * 0.92), int(desk_h * 0.85)
        scale = min(max_w / SCREEN_WIDTH, max_h / SCREEN_HEIGHT)
        scale = min(scale, 2.0) if scale >= 1 else scale
        return max(320, int(SCREEN_WIDTH * scale)), max(240, int(SCREEN_HEIGHT * scale))

    def apply(self):
        """(Re)create the window after a fullscreen or orientation change."""
        if self.fullscreen and sys.platform == "darwin":
            # macOS: real FULLSCREEN moves the game to its own Space, which can
            # close it straight away on some Macs. So use a borderless window -
            # but the menu bar and Dock draw on top of it, so it fills only the
            # area between them (otherwise the HUD and bottom holes are hidden).
            x, y, w, h = usable_area()
            if x is None:
                os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
                os.environ["SDL_VIDEO_CENTERED"] = "1"
                self.window = _set_mode((w, h), pygame.NOFRAME)
            else:
                # SDL only uses the position when it CREATES a window, so after an
                # F11 toggle start a fresh window. (Moving it with a temporary
                # pygame._sdl2 Window object destroys the window when that object
                # is cleaned up, which crashed the game.)
                if pygame.display.get_surface() is not None:
                    pygame.display.quit()
                    pygame.display.init()
                os.environ.pop("SDL_VIDEO_CENTERED", None)
                os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
                self.window = pygame.display.set_mode((w, h), pygame.NOFRAME)
        elif self.fullscreen:
            self.window = _set_mode((0, 0), pygame.FULLSCREEN)
        else:
            os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
            os.environ["SDL_VIDEO_CENTERED"] = "1"
            self.windowed_size = self._fit_windowed_size()
            self.window = _set_mode(self.windowed_size, pygame.RESIZABLE)
        self.canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self._update_fit()

    def on_resize(self):
        self.window = pygame.display.get_surface()
        self._update_fit()

    def _update_fit(self):
        win_w, win_h = self.window.get_size()
        self.scale = min(win_w / SCREEN_WIDTH, win_h / SCREEN_HEIGHT)
        out_w, out_h = int(SCREEN_WIDTH * self.scale), int(SCREEN_HEIGHT * self.scale)
        self.offset = ((win_w - out_w) // 2, (win_h - out_h) // 2)
        self.out_size = (out_w, out_h)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.apply()

    def to_game(self, pos):
        """Window pixel -> game (canvas) pixel."""
        x = (pos[0] - self.offset[0]) / self.scale
        y = (pos[1] - self.offset[1]) / self.scale
        return (int(round(clamp(x, 0, SCREEN_WIDTH - 1))), int(round(clamp(y, 0, SCREEN_HEIGHT - 1))))

    def to_window(self, pos):
        """Game (canvas) pixel -> window pixel (used by play_with_sensors.py)."""
        return (int(round(pos[0] * self.scale + self.offset[0])),
                int(round(pos[1] * self.scale + self.offset[1])))

    def present(self, shake=(0, 0)):
        self.window.fill((0, 0, 0))
        if self.out_size == (SCREEN_WIDTH, SCREEN_HEIGHT):
            frame = self.canvas
        else:
            frame = pygame.transform.smoothscale(self.canvas, self.out_size)
        dx = int(shake[0] * self.scale)
        dy = int(shake[1] * self.scale)
        self.window.blit(frame, (self.offset[0] + dx, self.offset[1] + dy))
        pygame.display.flip()


# The active Display, so play_with_sensors.py can convert sensor positions.
ACTIVE_DISPLAY = None


def game_to_window(pos):
    """Game pixel -> window pixel.  Identity before the window exists."""
    return ACTIVE_DISPLAY.to_window(pos) if ACTIVE_DISPLAY else pos


def window_to_game(pos):
    """Window pixel -> game pixel.  Identity before the window exists."""
    return ACTIVE_DISPLAY.to_game(pos) if ACTIVE_DISPLAY else pos


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------
STAGE_TITLE = "title"
STAGE_CALIBRATION = "calibration"
STAGE_LEVEL_TRANSITION = "level_transition"
STAGE_PLAYING = "playing"
STAGE_GAME_OVER = "game_over"


def run_game(orientation=None, fullscreen=None):
    """
    orientation: "landscape", "portrait" or "auto".  None = use the command
    line flags (--portrait / --landscape) or the ORIENTATION setting.
    """
    global ACTIVE_DISPLAY

    cli_orientation, cli_fullscreen = parse_command_line(sys.argv[1:])
    if orientation is None:
        orientation = cli_orientation
    if fullscreen is None:
        fullscreen = cli_fullscreen

    pygame.init()
    print(f"[game] screens found: {_screen_sizes()} -> using screen {chosen_display()} "
          f"(--display N to choose)")
    print(f"[game] starting - screen {desktop_size()}, "
          f"{'full screen' if fullscreen else 'window'}, ESC quits")
    fit_canvas_to_monitor(*usable_area()[2:])
    configure_layout(resolve_orientation(orientation))
    display = Display(fullscreen=fullscreen)
    ACTIVE_DISPLAY = display
    render_target = display.canvas   # everything is drawn here, then scaled to the window
    pygame.display.set_caption("Whack-a-Mole - ENGG3000 Multi-Level Prototype")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("arial", 28)
    font_small = pygame.font.SysFont("arial", 20)
    font_big = pygame.font.SysFont("arial", 48, bold=True)
    font_title = pygame.font.SysFont("arial", 44, bold=True)
    font_popup = pygame.font.SysFont("arial", 24, bold=True)
    alarm = SafetyAlarm()

    def new_game_state():
        set_level_theme(0)
        return {
            "stage": STAGE_TITLE,
            "level": 0,
            "score": 0,
            "combo": 0,
            "hits_this_level": 0,
            "start_ticks": None,
            "level_transition_start": None,
            "time_bonus_seconds": 0.0,
            "last_reaction_seconds": None,
            "sensor_status": dict(DEFAULT_SENSOR_STATUS),
            "mole": Mole(
                LEVELS[0]["mole_timeout"],
                LEVELS[0]["movement_speed"]
            ),
            "hit_flash_until": 0,
            "hammer_effect": None,   # (pos, start_time) or None
            "shake_until": 0,
            "shake_strength": 0,
            "popups": [],
            "dust_puffs": [],
            "won": False,
        }

    state = new_game_state()

    def prepare_level_transition():
        level = LEVELS[state["level"]]
        set_level_theme(state["level"])
        state["hits_this_level"] = 0
        state["combo"] = 0
        state["time_bonus_seconds"] = 0.0
        state["level_transition_start"] = pygame.time.get_ticks()
        state["mole"] = Mole(level["mole_timeout"], level["movement_speed"])
        state["stage"] = STAGE_LEVEL_TRANSITION

    def begin_level_play():
        level = LEVELS[state["level"]]
        state["start_ticks"] = pygame.time.get_ticks()
        state["mole"] = Mole(level["mole_timeout"], level["movement_speed"])
        state["stage"] = STAGE_PLAYING

    def start_round():
        state["level"] = 0
        state["score"] = 0
        state["won"] = False
        state["stage"] = STAGE_CALIBRATION

    def complete_current_level():
        state["level"] += 1

        if state["level"] >= len(LEVELS):
            state["won"] = True
            state["stage"] = STAGE_GAME_OVER
        else:
            prepare_level_transition()

    running = True
    while running:
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                print("[game] closing: the window was closed (QUIT event)")
                running = False

            elif event.type == pygame.VIDEORESIZE:
                display.on_resize()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    print("[game] closing: ESC pressed")
                    running = False

                elif event.key == pygame.K_F11:
                    display.toggle_fullscreen()
                    render_target = display.canvas

                elif event.key == pygame.K_o and state["stage"] in (STAGE_TITLE, STAGE_CALIBRATION):
                    # Switch horizontal <-> vertical screen.  Only allowed
                    # before play starts, so no mole is mid-animation.
                    configure_layout(LANDSCAPE if is_portrait() else PORTRAIT)
                    display.apply()
                    render_target = display.canvas
                    level = LEVELS[state["level"]]
                    state["mole"] = Mole(level["mole_timeout"], level["movement_speed"])

                elif event.key == pygame.K_r and state["stage"] == STAGE_GAME_OVER:
                    state = new_game_state()

                elif event.key == pygame.K_SPACE and state["stage"] == STAGE_TITLE:
                    start_round()

                elif state["stage"] == STAGE_CALIBRATION:
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                        sensor_id = int(event.unicode)
                        state["sensor_status"][sensor_id] = not state["sensor_status"][sensor_id]
                    elif event.key == pygame.K_SPACE and sensors_ready(state["sensor_status"]):
                        prepare_level_transition()

                elif event.key == pygame.K_SPACE and state["stage"] == STAGE_LEVEL_TRANSITION:
                    begin_level_play()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Temporary prototype control: ONE left-click = one whack.
                # Later this block can be triggered by the ESP32/sensor hit event.
                if event.button != 1:
                    continue

                if state["stage"] == STAGE_TITLE:
                    start_round()
                    continue

                if state["stage"] != STAGE_PLAYING:
                    continue

                click_pos = window_to_game(event.pos)
                state["hit_flash_until"] = now + 150
                state["hammer_effect"] = (click_pos, now)
                mole = state["mole"]

                if mole.contains(click_pos):
                    mole.register_hit(now)
                    reaction = mole.reaction_time_seconds(now)
                    state["last_reaction_seconds"] = reaction

                    # Red mole is a hazard: it costs points and breaks the combo.
                    if mole.mole_type == "red":
                        state["score"] = max(0, state["score"] + mole.base_points())
                        state["combo"] = 0
                        popup_text = f"{mole.base_points()} AVOID RED!"
                        popup_color = COLOR_WARNING
                    else:
                        state["hits_this_level"] += 1
                        state["combo"] += 1

                        if reaction <= REACTION_FAST_SECONDS:
                            reaction_bonus = REACTION_FAST_BONUS
                            reaction_label = "FAST!"
                        elif reaction <= REACTION_GOOD_SECONDS:
                            reaction_bonus = REACTION_GOOD_BONUS
                            reaction_label = "QUICK!"
                        else:
                            reaction_bonus = 0
                            reaction_label = ""

                        if state["combo"] >= COMBO_X3_AT:
                            multiplier = 3
                        elif state["combo"] >= COMBO_X2_AT:
                            multiplier = 2
                        else:
                            multiplier = 1

                        gained = (mole.base_points() + reaction_bonus) * multiplier
                        state["score"] += gained

                        if mole.mole_type == "blue":
                            state["time_bonus_seconds"] += 3.0

                        extras = []
                        if reaction_label:
                            extras.append(reaction_label)
                        if multiplier > 1:
                            extras.append(f"x{multiplier}")
                        if mole.mole_type == "blue":
                            extras.append("+3s")
                        popup_text = f"+{gained}" + (" " + " ".join(extras) if extras else "")
                        popup_color = COLOR_POPUP

                    state["popups"].append(
                        FloatingText(mole.position, popup_text, popup_color, font_popup, life_ms=850)
                    )
                    state["dust_puffs"].append(DustPuff(mole.position))
                    state["shake_until"] = now + 120
                    state["shake_strength"] = 5

                    level = LEVELS[state["level"]]
                    if state["hits_this_level"] >= level["hits_required"]:
                        complete_current_level()

        # This remains mouse-driven for now. Later, replace the body of
        # get_player_position() with the UDP / XYZ sensor position.
        cursor_pos = get_player_position(window_to_game(pygame.mouse.get_pos()))

        # Dead-zone check every frame, on every screen: red warning + alarm.
        too_close = player_is_too_close_to_screen(cursor_pos)
        alarm.update(too_close, now)

        def finish_frame(shake=(0, 0)):
            if too_close:
                draw_safety_warning(render_target, font, now)
            display.present(shake)

        if state["stage"] == STAGE_TITLE:
            draw_title_screen(render_target, now, font_title, font_small)
            finish_frame()

        elif state["stage"] == STAGE_CALIBRATION:
            draw_sensor_calibration(
                render_target, now, font_big, font_small, state["sensor_status"]
            )
            finish_frame()

        elif state["stage"] == STAGE_LEVEL_TRANSITION:
            level = LEVELS[state["level"]]
            draw_level_transition(
                render_target, now, font_big, font_small, state["level"] + 1, level
            )
            finish_frame()

            if (now - state["level_transition_start"]) >= LEVEL_TRANSITION_MS:
                begin_level_play()

        elif state["stage"] == STAGE_PLAYING:
            level = LEVELS[state["level"]]
            elapsed = (now - state["start_ticks"]) / 1000.0
            time_remaining = level["time"] + state["time_bonus_seconds"] - elapsed

            if time_remaining <= 0:
                state["won"] = False
                state["stage"] = STAGE_GAME_OVER
            else:
                mole = state["mole"]
                old_state = mole.state
                mole.update(now)

                if (old_state != Mole.MISSED and mole.state == Mole.MISSED
                        and mole.mole_type != "red"):
                    state["combo"] = 0  # escaped mole breaks the combo (dodging a red one doesn't)

                if mole.should_remove():
                    state["mole"] = Mole(
                        level["mole_timeout"],
                        level["movement_speed"]
                    )

            state["popups"] = [p for p in state["popups"] if not p.is_dead(now)]
            state["dust_puffs"] = [d for d in state["dust_puffs"] if not d.is_dead(now)]

            draw_background(render_target, now)
            draw_holes(render_target)
            state["mole"].draw(render_target, now)

            for dust in state["dust_puffs"]:
                dust.draw(render_target, now)
            for popup in state["popups"]:
                popup.draw(render_target, now)

            if state["hammer_effect"] is not None:
                pos, start = state["hammer_effect"]
                t = (now - start) / 150.0
                if t >= 1.0:
                    state["hammer_effect"] = None
                else:
                    draw_hammer_hit(render_target, pos, t)


            hit_flash = now < state["hit_flash_until"]
            draw_cursor(render_target, cursor_pos, hit_flash)

            draw_hud(
                render_target,
                font,
                font_small,
                state["score"],
                time_remaining,
                state["combo"],
                state["level"] + 1,
                level["name"],
                state["hits_this_level"],
                level["hits_required"],
                level["time"],
            )


            if now < state["shake_until"]:
                strength = state["shake_strength"]
                offset = (
                    random.randint(-strength, strength),
                    random.randint(-strength, strength)
                )
            else:
                offset = (0, 0)

            finish_frame(offset)

        else:  # STAGE_GAME_OVER
            draw_game_over(
                render_target,
                now,
                font_big,
                font,
                state["score"],
                state["won"],
            )
            finish_frame()

        clock.tick(FPS)

    pygame.quit()
    sys.exit()


def _prepare_layout_for_this_screen():
    """
    Pick the canvas shape and hole layout as soon as the game is loaded, so
    play_with_sensors.py sees the final HOLE_POSITIONS / SCREEN_WIDTH when it
    hooks in (it reads them before calling run_game()).
    """
    try:
        pygame.display.init()
        fit_canvas_to_monitor(*usable_area()[2:])
        configure_layout(resolve_orientation(parse_command_line(sys.argv[1:])[0]))
    except pygame.error:
        pass


_prepare_layout_for_this_screen()


if __name__ == "__main__":
    run_game()