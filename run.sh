#!/usr/bin/env bash
# Usage: ./run.sh  (reads KENSHO_REFRESH_TOKEN from .env or environment)
set -e
cd "$(dirname "$0")"

# Load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

pip install -r requirements.txt -q
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
