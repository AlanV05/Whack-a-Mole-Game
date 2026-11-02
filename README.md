# ENGG3000 Whack-a-Mole Game

A Whack-a-Mole game developed in Python using Pygame as part of the ENGG3000 project.

## Requirements

Before running the game, make sure you have:

- Python 3
- Pygame

## Install Pygame

If Pygame is not installed, run:

```bash
python3 -m pip install pygame
```

## Compile / Check for Syntax Errors

Before running the game, check the Python file for syntax errors:

```bash
python3 -m py_compile whack_a_mole.py
```

If no error message appears, the code has passed the syntax check.

## Run the Game

Run the game using:

```bash
python3 whack_a_mole.py
```

## How to Play

1. Start the game by running `whack_a_mole.py`.
2. Wait for the mole to appear from one of the holes.
3. Move the hammer over the mole.
4. Double-click the mole to hit it.
5. Each successful hit increases your score.
6. The mole will continue appearing at different positions.
7. Try to hit as many moles as possible before the timer reaches zero.
8. When the game ends, press `R` to restart.
9. Press `ESC` to quit the game.

## Main Game Features

- 3 × 3 Whack-a-Mole grid
- Random mole spawning
- Animated mole movement
- Hammer mouse cursor
- Hammer hit animation
- Soil particle effects when the mole appears
- Score tracking
- Countdown timer
- Double-click hit detection
- Game-over screen
- Restart functionality
- Custom mole and background images

## Levels 

- Manual level advance: press N during play to jump to the next level (up to 3). HUD shows "Level X/3 - N for next level" when you're not mid-combo.

Level 1: unchanged, standard single mole.

Level 2: build a 5-combo and the next mole that spawns is a Big Mole golden, ~1.7x size, only up for 0.9s (shorter window than normal, so it's a timing test, not a "wait for it" test). There's a half-second "BIG MOLE INCOMING!" telegraph with an empty field right before it appears so it doesn't feel like a cheap surprise. Landing it gives a flat +5 bonus (matches your "5 combo → x5" idea) and always resets the combo, hit or miss.

Level 3: shorter mole timeout (1.1s vs 2s) and a 35% chance each wave that two moles pop in different holes at once. Big Mole logic carries over from level 2 since nothing you said suggested dropping it.


## Project Files

```text
ENGG3000-Whack-a-Mole-Game-/
├── whack_a_mole.py
├── background.png.jpg
├── mole.png
├── hammer.png
├── README.md
└── .gitignore
```

### `whack_a_mole.py`

Contains the main game logic, including:

- Game loop
- Mole movement
- Mole spawning
- Hit detection
- Hammer cursor
- Soil particle animation
- Score system
- Timer
- Game-over and restart functionality

### `background.png.jpg`

Contains the background image used for the game.

### `mole.png`

Contains the mole character image.

### `hammer.png`

Contains the hammer image used as the custom mouse cursor.

## Controls

| Control | Action |
| --- | --- |
| Mouse Movement | Move the hammer |
| Double-click | Hit the mole |
| `R` | Restart the game after time runs out |
| `ESC` | Quit the game |

## Quick Start

```bash
python3 -m pip install pygame
python3 -m py_compile whack_a_mole.py
python3 whack_a_mole.py
```

## Technologies Used

- Python
- Pygame
- Git
- GitHub

## Author

Rikita Shil

Software Engineering  
Macquarie University

---

## Final product (Sprint 3): playing with the ultrasonic sensors

**Windows (no Python needed):** run `WhackAMole_Setup.exe` (built automatically by GitHub Actions:
Actions tab -> "Build Windows installer" -> Artifacts). The first time it runs, allow it on
**Private and Public** networks when Windows asks.

**From the code (Mac / Windows):**
```bash
pip install pygame-ce python-osc
python whack_a_mole_app.py              # tracker + game in one program
python whack_a_mole_app.py --display 1  # game on the TV (screen 1)
```

| File | What it does |
|---|---|
| `sensor_esp32_wifi_zoned/` | ESP32 firmware. Boards find the PC by UDP broadcast, so no IP address to set. |
| `sensor_to_processing_zoned.py` | Tracker: fires the 4 boards in turn, filters, works out the player's position. |
| `play_with_sensors.py` | Runs the team's game with the sensors instead of the mouse. |
| `sensor_ui.py` | Setup guide (H), calibration check, sensor status, reduced-coverage banner. |
| `game_settings.py` / `whack_settings.json` | Tuning values you can change without editing code. |
| `whack_a_mole_app.py` | One program: tracker + game. Entry point for the Windows build. |
| `WhackAMole.spec`, `installer.iss`, `build_windows.bat`, `.github/workflows/build-windows.yml` | Windows packaging. |

**Before play:** press **H** on the title screen for where the boxes go. On the Sensor Check screen,
stand on the centre X until every box shows a tick, then press SPACE
(C = skip the standing check, F = play on 3 sensors if one box is missing, R = redo).
