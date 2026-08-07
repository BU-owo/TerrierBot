#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/ven/bin/python}"
BOT_MAIN="${BOT_MAIN:-$ROOT_DIR/bot.py}"
WEBHOOK_URL="${DISCORD_ALERT_WEBHOOK:-}"
STATE_FILE="${ALERT_STATE_FILE:-$ROOT_DIR/data/pm2_restart_state.json}"
WINDOW_SECONDS="${PM2_RESTART_WINDOW_SECONDS:-300}"
REPEAT_THRESHOLD="${PM2_RESTART_ALERT_THRESHOLD:-5}"
EXPECTED_EXIT_CODES="${PM2_EXPECTED_EXIT_CODES:-0 130 143}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" "$BOT_MAIN"
exit_code=$?

unexpected_exit=1
for expected_code in $EXPECTED_EXIT_CODES; do
  if [[ "$exit_code" -eq "$expected_code" ]]; then
    unexpected_exit=0
    break
  fi
done

exit_ts="$(date -u +%s)"
mkdir -p "$(dirname "$STATE_FILE")"

repeat_count="$($PYTHON_BIN - "$STATE_FILE" "$exit_ts" "$WINDOW_SECONDS" "$unexpected_exit" <<'PY'
from __future__ import annotations
import json
import os
import sys

state_file, exit_ts_str, window_str, unexpected_exit_str = sys.argv[1:5]
exit_ts = int(exit_ts_str)
window = int(window_str)
unexpected_exit = unexpected_exit_str == "1"
cutoff = exit_ts - window

state: dict[str, list[int]] = {"timestamps": []}
if os.path.exists(state_file):
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("timestamps"), list):
                state = {"timestamps": [int(x) for x in loaded["timestamps"] if isinstance(x, int) or str(x).isdigit()]}
    except Exception:
        state = {"timestamps": []}

timestamps = [ts for ts in state["timestamps"] if ts >= cutoff]
  if unexpected_exit:
    timestamps.append(exit_ts)

with open(state_file, "w", encoding="utf-8") as f:
    json.dump({"timestamps": timestamps}, f)

print(len(timestamps))
PY
)"

if [[ -z "$WEBHOOK_URL" ]]; then
  exit "$exit_code"
fi

send_alert=0
priority="Alert"
repeat_line=""

if [[ "$unexpected_exit" -eq 1 ]]; then
  send_alert=1
fi

if [[ "$unexpected_exit" -eq 1 && "$repeat_count" -ge "$REPEAT_THRESHOLD" ]]; then
  send_alert=1
  priority="HIGH PRIORITY"
  repeat_line="TerrierBot restarted $repeat_count times within the last $WINDOW_SECONDS seconds."
fi

if [[ "$send_alert" -eq 1 ]]; then
  timestamp_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  message="PM2 $priority: TerrierBot exited with code $exit_code at $timestamp_utc."
  if [[ -n "$repeat_line" ]]; then
    message="$message $repeat_line"
  fi

  payload="$($PYTHON_BIN - "$message" <<'PY'
from __future__ import annotations
import json
import sys

message = sys.argv[1]
print(json.dumps({"content": message}))
PY
)"

  curl -fsS -m 10 -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL" >/dev/null 2>&1 || true
fi

exit "$exit_code"
