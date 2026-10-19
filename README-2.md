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
python3 v2.py              # mouse
python3 play_with_sensors.py   # ESP32 sensors
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

## Playing with the ESP32 sensors

The three sensor boxes stand on the wall under the screen (Box 1 left, Box 2
middle, Box 3 right) facing the player. Each one sends its distance to the PC
over Wi-Fi/UDP.

- **Column** = which sensor sees the player
- **Row** = how far they are from the wall (60–200 cm, split into 3 rows)
- **Whack** = step into a hole's zone and hold still for ~0.35 s (step out and
  back in to whack the same hole again)
- **Closer than 60 cm** = warning on screen + buzzer on Box 2

### Setup

1. Open `esp32/sensor_box/sensor_box.ino`, set `WIFI_SSID`, `WIFI_PASSWORD`
   and `PC_IP` (run `ipconfig` on the PC), then upload it to each board with
   `SENSOR_ID` set to 1, 2 and 3.
2. Put the PC and all three boxes on the same Wi-Fi network. Allow Python
   through Windows Firewall the first time it asks.
3. Run:

```
python play_with_sensors.py --fullscreen
```

4. The Sensor Check screen shows each box's live distance. Press SPACE when
   all three are connected.

**Press `M` at any time to switch to the mouse** (demo backup if Wi-Fi drops),
and `M` again to go back to the sensors.

All tuning values (ports, dead zone, which box has the buzzer, whack hold
time, sensor-to-column order) are at the top of `sensor_link.py`.

### Testing without hardware

```
python play_with_sensors.py
python tools/fake_sensors.py              # in a second terminal
python -m unittest discover tests         # logic tests
```

`fake_sensors.py` walks a pretend player through all 9 holes and into the
dead zone. `--fixed 100 200 300` sends fixed values instead.

## Technologies Used

- Python
- Pygame
- Git
- GitHub

## Author

Rikita Shil

Software Engineering  
Macquarie University
