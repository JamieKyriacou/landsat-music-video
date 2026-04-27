#!/usr/bin/env bash
# Universal launcher for landsat_words.py and landsat_video.py.
# Auto-creates and populates the venv on first run — no manual setup needed.
#
# Usage:
#   ./run.sh words "hello world"
#   ./run.sh video --song "Pink Floyd Wish You Were Here" --line "How I wish"
#   ./run.sh video --song "Pink Floyd Wish You Were Here"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
REQS="$SCRIPT_DIR/requirements.txt"

# ── bootstrap venv if missing ──────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python3" ]; then
  echo "Setting up virtual environment (one-time) …"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$REQS"
  echo "Done."
  echo
fi

# ── dispatch ───────────────────────────────────────────────────────────────────
CMD="${1:-}"
shift || true

case "$CMD" in
  words)
    exec "$VENV/bin/python3" "$SCRIPT_DIR/landsat_words.py" "$@"
    ;;
  video)
    exec "$VENV/bin/python3" "$SCRIPT_DIR/landsat_video.py" "$@"
    ;;
  *)
    echo "Usage:"
    echo "  ./run.sh words \"your sentence here\""
    echo "  ./run.sh video --song \"Artist Song Title\" [--line \"...\"]"
    exit 1
    ;;
esac
