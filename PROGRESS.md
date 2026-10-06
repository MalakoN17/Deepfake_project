# Progress

Deadline: 22/09/2026. Demo on the lab server (Linux).

## Done (working prototype, 41 tests passing on Python 3.10)
- [x] Environment, requirements pinned for Python 3.10 (Windows + Linux)
- [x] Flask basics: home page, `/user/<name>` with Jinja2, custom error pages
- [x] Database (6 entities) + ERD (`docs/ERD.md`)
- [x] Login / logout, password hashing, roles, lockout, audit log
- [x] Dashboard (auto-refresh), Logs (filters, search, CSV export), Alerts (workflow)
- [x] Video upload with validation, OpenCV frame sampling, face detection
- [x] Deepfake model (MesoNet -> ONNX, CPU), identity verification (OpenFace), quality score
- [x] Risk engine with smoothing; alerts with severity and cooldown
- [x] Live analysis from the browser: camera and shared Zoom/Teams window
- [x] Latency, CPU and RAM measured and stored per analysis
- [x] Evaluation script (confusion matrix, TPR/FPR, compression test)

## Fixed
- [x] v1.1: 500 error when adding a reference photo - OpenCV on Windows cannot open paths with non-English
      characters. Models now load from memory, images are saved with Python, errors are shown on the page,
      and `flask --app run doctor` checks the installation.

- [x] v1.2: genuine webcam face scored 92% deepfake risk (quality 98, identity 100%). Cause: the face crop
      (box + 20%) was tighter than the crops MesoNet was trained on. With box x 2 (FACE_CROP_MARGIN=0.5),
      false positives on 14 real photos dropped from 4/14 to 1/14. Effect on real deepfakes still to be measured.
      Also: webcam fallback to default resolution + clear camera error messages.

- [x] v1.3: `pip install` failed on Python 3.14 (numpy had no wheel for the pinned version).
      requirements.txt now uses version ranges and installs on Python 3.10-3.14; the exact tested
      versions moved to requirements-lock.txt. All 41 tests pass on both 3.10 and 3.14.

## Next
- [ ] Run locally on my PC, add my own reference photo, calibrate identity thresholds (record values)
- [ ] Collect a small test set (real + fake videos) and run `scripts/evaluate.py` (normal + `--jpeg 30 --scale 0.5`)
- [ ] Push to GitHub with meaningful commits
- [ ] Lab server: install, HTTPS (camera needs it), demo accounts for classmates, `SESSION_COOKIE_SECURE=true`
- [ ] Report chapters: process tree, UML (use case, sequence, activity), screens, Gantt (planned vs actual), cost analysis, alternatives
- [ ] Record the demo scenario and screenshots
