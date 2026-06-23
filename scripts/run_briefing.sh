#!/usr/bin/env bash
# Daily briefing wrapper script for launchd.
#
# Guards:
#   - Skips if the briefing already ran today in the evening (after 18:00).
#     This prevents a double-run if launchd fires at 9pm after a morning catch-up run.
#   - A catch-up run (e.g. machine was off at 9pm, wakes at 8am) DOES run,
#     and does NOT block the scheduled 9pm run later that day.
#
# State file: ~/.wapi_bs_last_run  (epoch timestamp of last successful run)
# Logs:       ~/Library/Logs/wapi-bs/briefing.log

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="/Users/seowyanyi/.local/bin/uv"
STATE_FILE="$HOME/.wapi_bs_last_run"
LOG_DIR="$HOME/Library/Logs/wapi-bs"

mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/briefing.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
}

# Skip only if there was an evening run (hour >= 18) already today.
# A morning catch-up run (hour < 18) does not block the evening run.
if [[ -f "$STATE_FILE" ]]; then
  last_epoch=$(cat "$STATE_FILE")
  last_date=$(date -r "$last_epoch" '+%Y-%m-%d')
  last_hour=$(date -r "$last_epoch" '+%H')
  today=$(date '+%Y-%m-%d')

  if [[ "$last_date" == "$today" && "$last_hour" -ge 18 ]]; then
    log "Skipping: already ran this evening at $(date -r "$last_epoch" '+%H:%M')."
    exit 0
  fi
fi

log "Starting daily briefing..."

cd "$PROJECT_DIR"

if "$UV" run python main.py >> "$LOGFILE" 2>&1; then
  date +%s > "$STATE_FILE"
  log "Briefing completed successfully."
else
  exit_code=$?
  log "Briefing FAILED (exit $exit_code). Check $LOGFILE for details."
  exit "$exit_code"
fi
