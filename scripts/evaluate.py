from __future__ import annotations
"""Offline evaluation of the detection pipeline - produces the numbers for the report.

Put test videos in two folders, e.g.  data/real/*.mp4  and  data/fake/*.mp4
(for example from FaceForensics++, Celeb-DF or DFDC, or recordings of yourselves - with consent).

    python scripts/evaluate.py --real data/real --fake data/fake
    python scripts/evaluate.py --real data/real --fake data/fake --jpeg 30 --scale 0.5   # compression test

Outputs a per-video CSV, a confusion matrix, TPR / FPR / accuracy and latency statistics.
A video counts as "detected fake" when its Deepfake Risk Score >= RISK_SUSPICIOUS.
"""
import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app  # noqa: E402
from app.services.pipeline import WindowSummary, analyze_frame, sample_video  # noqa: E402
from app.services.risk import evaluate as risk_evaluate  # noqa: E402

VIDEO_EXT = {".mp4", ".avi", ".mov"}


def degrade(frame, jpeg_quality, scale):
    """Simulate real-world meeting conditions: lower resolution + stronger compression."""
    if scale < 1:
        h, w = frame.shape[:2]
        frame = cv2.resize(cv2.resize(frame, (int(w * scale), int(h * scale))), (w, h))
    if jpeg_quality < 100:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", required=True, type=Path)
    ap.add_argument("--fake", required=True, type=Path)
    ap.add_argument("--jpeg", type=int, default=100, help="JPEG quality 1-100 (100 = no extra compression)")
    ap.add_argument("--scale", type=float, default=1.0, help="downscale factor, e.g. 0.5")
    ap.add_argument("--out", type=Path, default=Path("results/evaluation.csv"))
    args = ap.parse_args()

    app = create_app()
    cfg = app.config
    rows = []
    with app.app_context():
        for label, folder in (("real", args.real), ("fake", args.fake)):
            for video in sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT):
                window, start = WindowSummary(), time.perf_counter()
                for frame, cap_ms in sample_video(video, cfg["SAMPLE_FPS"], cfg["MAX_SAMPLED_FRAMES"]):
                    window.add(analyze_frame(degrade(frame, args.jpeg, args.scale)), cap_ms)
                total_ms = (time.perf_counter() - start) * 1000
                rr = risk_evaluate(window.deepfake_prob, None, window.quality, window.faces > 0, cfg)
                predicted = "fake" if rr.risk_score >= cfg["RISK_SUSPICIOUS"] else "real"
                rows.append({"video": video.name, "label": label, "predicted": predicted,
                             "risk": rr.risk_score, "result": rr.result, "quality": round(window.quality, 1),
                             "frames": window.frames, "faces": window.faces, "total_ms": round(total_ms, 1),
                             "ms_per_frame": round(total_ms / max(window.frames, 1), 1)})
                print(f"{label:4s} {video.name:40s} risk={rr.risk_score:5.1f}% -> {predicted:4s} ({rr.result})")

    if not rows:
        sys.exit("No videos found.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    tp = sum(r["label"] == "fake" and r["predicted"] == "fake" for r in rows)
    fn = sum(r["label"] == "fake" and r["predicted"] == "real" for r in rows)
    fp = sum(r["label"] == "real" and r["predicted"] == "fake" for r in rows)
    tn = sum(r["label"] == "real" and r["predicted"] == "real" for r in rows)
    print(f"\nConditions: JPEG quality {args.jpeg}, scale {args.scale}")
    print(f"Confusion matrix      predicted fake   predicted real")
    print(f"  actual fake         {tp:14d}   {fn:14d}")
    print(f"  actual real         {fp:14d}   {tn:14d}")
    print(f"TPR (detection rate)  {tp / max(tp + fn, 1):.1%}")
    print(f"FPR (false alarms)    {fp / max(fp + tn, 1):.1%}")
    print(f"Accuracy              {(tp + tn) / len(rows):.1%}")
    print(f"Latency per frame     median {statistics.median(r['ms_per_frame'] for r in rows):.0f} ms")
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
