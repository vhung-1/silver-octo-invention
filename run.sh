#!/usr/bin/env bash
# Usage: KENSHO_REFRESH_TOKEN=<your_token> ./run.sh
set -e
cd "$(dirname "$0")"
pip install -r requirements.txt -q
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
