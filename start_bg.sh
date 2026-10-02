#!/usr/bin/env bash
set -e
PORT="${MEETING_PORT:-7720}"
URL="http://127.0.0.1:$PORT/"
if curl -fs -o /dev/null "${URL}api/rooms"; then echo "already running: $URL"; exit 0; fi
PY="$(command -v python3 || command -v python)"
[ -z "$PY" ] && { echo "Python 3.9+ not found" >&2; exit 1; }
HOME_DIR="${MEETING_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/ai-meeting-room}"
mkdir -p "$HOME_DIR"
nohup "$PY" -u "$(cd "$(dirname "$0")" && pwd)/hub.py" >"$HOME_DIR/hub.log" 2>"$HOME_DIR/hub.err.log" &
for _ in $(seq 40); do
  sleep 0.5
  if curl -fs -o /dev/null "${URL}api/rooms"; then echo "started: $URL"; exit 0; fi
done
echo "did not start in time; see $HOME_DIR/hub.err.log" >&2
exit 1
