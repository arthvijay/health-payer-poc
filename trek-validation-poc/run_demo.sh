#!/usr/bin/env bash
# One command: set up (first run only), regenerate data + script, verify, launch.
# Usage: ./run_demo.sh            (verify + launch)
#        ./run_demo.sh --skip-tests
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "▶ Creating virtualenv (first run needs internet; every run after is offline)…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "▶ Generating synthetic data + DEMO_SCRIPT.md"
.venv/bin/python -m src.data_generator
.venv/bin/python -m src.demo_script

if [ "${1:-}" != "--skip-tests" ]; then
  echo "▶ Running verification suite"
  .venv/bin/python -m pytest -q -p no:cacheprovider tests/verify_poc.py
fi

echo "▶ Launching http://localhost:8501  (Ctrl+C to stop)"
exec .venv/bin/streamlit run app.py
