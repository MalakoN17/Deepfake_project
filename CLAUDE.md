# Instructions for Claude Code

## Who I am and how to work with me
- Final-year cyber security student (academic final project). I work alone on the code. Explain in Hebrew.
- Windows + CMD, Python 3.10, venv in `venv/`. Give exact CMD commands.
- One change at a time: explain what and why, show the code, tell me how to test it, wait for my OK.
- Run `pytest -q` before suggesting a commit; suggest a clear commit message after each working change.
- Never commit `.env`, `instance/`, `venv/`, videos or reference photos. Never enable `debug=True` on a server.

## Project
AI-Based Deepfake Detection System for Organizational Video Meetings (fictional org: GlobalTech Solutions).
Flask information system + CPU-only AI pipeline. Classes are always Approved / Suspicious / Rejected
(as promised in the Problem Identification document). It is a prototype: never claim 100% detection.

## Where things are
- `config.py` - every threshold and setting (risk, identity, quality, sampling, lockout)
- `app/services/pipeline.py` - frame -> face -> model -> identity -> quality, with timing
- `app/services/risk.py` - risk engine (rules + smoothing); `records.py` - saving analyses, alerts, audit
- `app/services/detector.py` - pluggable deepfake model (interface: `predict(face_bgr_256) -> P(fake)`)
- `app/routes/analysis.py` - upload + live API (browser sends ~1 frame/s); live state is in memory (1 process)
- `docs/ERD.md` - database design; `PROGRESS.md` - status and next steps

## Rules
- Keep thresholds in `config.py`, not hard-coded. Keep all JS/CSS local (CSP is `'self'` only, no inline scripts).
- Every new POST endpoint must be CSRF-protected and `@login_required`; admin pages use `@admin_required`.
- Add or update a test in `tests/test_app.py` for every behaviour change.
