#!/usr/bin/env bash
# run_sscheduler_drone.sh
# Usage: run on drone (ssh dev@<drone-ip>), make executable: chmod +x scripts/run_sscheduler_drone.sh
# Prompts for 'r' to continue, activates virtualenv, sets envs and runs sscheduler/sdrone.py

set -euo pipefail

read -rp "Press 'r' to run sscheduler.sdrone (or Ctrl-C to cancel): " REPLY
if [ "$REPLY" != "r" ]; then
  echo "Cancelled."
  exit 1
fi

# Adjust this path to your virtualenv activate script
VENV="$HOME/cenv/bin/activate"
if [ -f "$VENV" ]; then
  # shellcheck disable=SC1090
  source "$VENV"
else
  echo "Virtualenv activate script not found at $VENV"
  echo "Run sscheduler without venv or edit this script to point to your venv." >&2
fi

export DRONE_HOST="$(hostname -I | awk '{print $1}')"
# Edit GCS_HOST below if needed
export GCS_HOST="192.168.0.100"

cd "$(dirname "$0")/.." || exit 1
cd sscheduler || exit 1

# Run sscheduler sdrone and keep output to a log
LOGDIR="$(pwd)/../logs/sscheduler/drone"
mkdir -p "$LOGDIR"
LOGFILE="$LOGDIR/sdrone_$(date -u +%Y%m%d-%H%M%SZ).log"

echo "Starting sscheduler.sdrone (log: $LOGFILE)"
python3 sdrone.py > "$LOGFILE" 2>&1 &
PID=$!
sleep 1
if ps -p "$PID" > /dev/null; then
  echo "sscheduler.sdrone started (PID $PID). Tail the log: tail -f $LOGFILE"
else
  echo "sscheduler.sdrone failed to start. See $LOGFILE"
  exit 1
fi

wait
