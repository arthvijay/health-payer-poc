# health-payer-poc

Interview demo: a mock of Trek Health's SE fee-schedule validation motion, presented as offline live slides (5–10 min).

- `docs/`: reference notes distilled from the user's Gemini corpus (01 corpus analysis, 02 glossary, 03 requirements, 04 architecture, 05 format & open items). Read 01 and 05 first.
- `trek-validation-poc/`: the app. `./run_demo.sh` sets up, verifies, and launches it. The venv lives at `trek-validation-poc/.venv` (Python 3.14).
- Talk-track numbers come from `src/demo_script.py`. After changing data or engine logic, run `.venv/bin/python -m src.demo_script` or the sync test fails.
- Verify with `.venv/bin/python tests/verify_poc.py` (33 checks, including a headless UI pass over every slide).
- Streamlit markdown renders `$…$` pairs as LaTeX: use `esc()` (markdown) or `esc_html()` (raw-HTML blocks) in `app.py` for any dynamic text containing dollars.
- DuckDB 2.0: always fully fetch results and go through `engine._df` / `engine._rows` (locked; the engine is shared across Streamlit threads).
