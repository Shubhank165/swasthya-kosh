#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-$(pwd)}"
cd "$project_dir"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
echo "Installed MediKiosk in $project_dir/.venv"
echo "Copy .env.example to .env and add keys interactively; never commit .env."
