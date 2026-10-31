#!/bin/bash
# Double-click to play. (First time only: in Terminal run  chmod +x start_game.command)
cd "$(dirname "$0")" || exit 1
if [ -f venv/bin/activate ]; then
  source venv/bin/activate
else
  echo "No venv folder here - create it first:  python3 -m venv venv && source venv/bin/activate && pip install pygame-ce python-osc"
  read -p "Press Enter to close"; exit 1
fi
python run.py "$@"
read -p "Press Enter to close this window"
