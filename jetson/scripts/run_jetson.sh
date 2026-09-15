#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-$(pwd)}"
cd "$project_dir"
exec .venv/bin/uvicorn medikiosk.app:app --host 127.0.0.1 --port 8000
