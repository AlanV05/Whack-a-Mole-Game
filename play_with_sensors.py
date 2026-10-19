"""
Run the Whack-a-Mole game using the three ESP32 ultrasonic sensor boxes.

    python play_with_sensors.py                 # sensors, auto screen layout
    python play_with_sensors.py --fullscreen    # demo mode
    python play_with_sensors.py --portrait      # TV turned on its side

Press M during the game to switch to the mouse if Wi-Fi drops (and back).
Settings (UDP port, dead zone, which box has the buzzer...) are at the top
of sensor_link.py.
"""

import v2

if __name__ == "__main__":
    v2.run_game(use_sensors=True)
