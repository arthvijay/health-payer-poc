# 05 · Demo Format, Decisions & Open Items

## Context from the user (2026-10-22)
- **Audience:** an interviewer at a company that sells this same service (Trek Health, payer-performance platform).
  The demo is a small mock app of *their* product, pitched by the candidate.
- **Format:** a clickable web UI that also works as live slides. Screen-shared, **offline**, **5–10 minutes**.

## How the build meets that
| Need | Implementation |
|------|----------------|
| Slides | 🎞️ Live Slides mode: 9 slides with a title + one-line takeaway + live content each; jump nav; PageUp/PageDown (clicker-friendly); `?slide=N` deep link |
| Clickable / explorable | Every slide is the real app (hover charts, drag levers, sandbox, download, agent). 🧰 Workbench mode shows all 5 tabs if the interviewer wants to drive |
| Offline | Local Streamlit on `localhost`, system fonts, no telemetry, deterministic agent by default |
| 5–10 min | ~8–9 min full; 5-min cut = skip slides 2, 4, 7 |
| Speaker support | `DEMO_SCRIPT.md` (second screen) and an optional "Presenter notes" toggle (visible to the audience if you share that tab) |

## Open items for the user
1. **Check the personal claims** in the interview section of `DEMO_SCRIPT.md` (school, degree, Open Dental project, relocation).
   They came from the Gemini draft and are marked `[verify]`.
2. **Peer hospital names are fictional** on purpose. To use different names, edit `PEER_HOSPITALS` in `src/data_generator.py`
   and re-run `./run_demo.sh`.
3. **Live Claude mode has not been exercised against the real API.** Only its fallback path is tested. If you plan to show it,
   paste a key in the sidebar once before the interview. Otherwise stay offline; the deterministic mode is the demo-safe default.
4. "OpenPayer" policy cards are **simulated**. Say so if asked.
