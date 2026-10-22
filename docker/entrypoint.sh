#!/bin/sh
set -e
DATA="${DATA_DIR:-/app/data}"
mkdir -p "$DATA/pdfs" "$DATA/models"
# First start: make the demo PDF, then index it in the background (the web app is usable meanwhile).
if [ "${AUTO_DEMO:-1}" = "1" ] && [ ! -f "$DATA/pdfs/velmora-annual-review-2025.pdf" ]; then
    python -m deepdoc.cli generate || echo "demo PDF generation failed; continuing"
fi
if [ "${AUTO_DEMO:-1}" = "1" ] && [ ! -f "$DATA/index.sqlite3" ] && [ "$1" = "uvicorn" ]; then
    (python -m deepdoc.cli ingest > "$DATA/first-ingest.log" 2>&1 || true) &
fi
exec "$@"
