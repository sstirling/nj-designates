#!/usr/bin/env bash
# Backfill the NJ Legislature scrape for every session 2022 back to 2000.
# Runs sequentially (1 req/sec throughout) to be polite to the undocumented API.
# Writes a short per-session summary line to scripts/backfill_status.log so
# progress is legible at a glance. Detailed logs go to scripts/backfill.log.

set -u  # but NOT -e — we want one bad session not to abort the run.

cd "$(dirname "$0")/.."

SESSIONS=(2022 2020 2018 2016 2014 2012 2010 2008 2006 2004 2002 2000)
LOG=scripts/backfill.log
STATUS=scripts/backfill_status.log

: > "$LOG"
: > "$STATUS"

echo "backfill started $(date -Iseconds) — ${#SESSIONS[@]} sessions" | tee -a "$STATUS"

for s in "${SESSIONS[@]}"; do
  START=$(date +%s)
  echo "[$(date -Iseconds)] starting session $s" | tee -a "$STATUS"

  python -m scraper --verbose fetch --session "$s" >> "$LOG" 2>&1
  RC=$?

  ELAPSED=$(( $(date +%s) - START ))
  # The scraper's own INFO line has the session summary; lift it into the status log.
  LAST_SUMMARY=$(grep "session=$s:" "$LOG" | tail -1)
  if [[ $RC -eq 0 ]]; then
    echo "  finished session $s in ${ELAPSED}s — ${LAST_SUMMARY:-'(no summary line)'}" | tee -a "$STATUS"
  else
    echo "  FAILED session $s after ${ELAPSED}s (rc=$RC)" | tee -a "$STATUS"
  fi
done

echo "backfill done $(date -Iseconds)" | tee -a "$STATUS"
echo "running final build across all sessions..." | tee -a "$STATUS"
python -m scraper build --all >> "$LOG" 2>&1
BUILD_RC=$?
BUILT=$(grep "built .* bills across sessions" "$LOG" | tail -1)
echo "build finished rc=$BUILD_RC — ${BUILT}" | tee -a "$STATUS"
