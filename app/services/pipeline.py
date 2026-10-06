from __future__ import annotations
"""The analysis pipeline:

frame -> face detection -> face crop -> deepfake model -> identity check -> quality
      -> (aggregate several frames) -> risk engine -> Analysis record (+ Alert)

Every stage is timed so the real-time requirement is backed by measurements.
"""
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import psutil
from flask import current_app

from .cv_io import opencv_path
from .detector import load_detector
from .faces import FaceAnalyzer, crop_face, identity_match_score, quality_score

_models = {}
_process = psutil.Process()


def get_models():
    """Load the models once per process (loading takes ~1s, inference a few ms)."""
    if "faces" not in _models:
        cfg = current_app.config
        _models["faces"] = FaceAnalyzer(cfg["MODEL_DIR"], cfg["FACE_CONFIDENCE"])
        _models["detector"] = load_detector(cfg)
    return _models["faces"], _models["detector"]


@dataclass
class FrameResult:
    face_found: bool
    deepfake_prob: float = 0.0
    identity_match: float | None = None
    quality: float = 0.0
    box: tuple | None = None
    face_ms: float = 0.0
    inference_ms: float = 0.0


def analyze_frame(frame_bgr, reference_embedding=None):
    faces, detector = get_models()
    t0 = time.perf_counter()
    detected = faces.detect(frame_bgr)
    t1 = time.perf_counter()
    if not detected:
        return FrameResult(False, face_ms=(t1 - t0) * 1000)
    _, box = detected[0]  # largest face = the main participant
    prob = detector.predict(crop_face(frame_bgr, box, current_app.config["FACE_CROP_MARGIN"]))
    match = None
    # Identity is only compared when the face is large enough to give a reliable embedding;
    # otherwise it stays None and the risk engine refuses to approve (see risk.evaluate)
    if reference_embedding is not None and box[2] - box[0] >= current_app.config["MIN_FACE_FOR_IDENTITY"]:
        sim = float(faces.embed(frame_bgr, box) @ reference_embedding)
        match = identity_match_score(sim)
    t2 = time.perf_counter()
    return FrameResult(True, prob, match, quality_score(frame_bgr, box), box,
                       (t1 - t0) * 1000, (t2 - t1) * 1000)


@dataclass
class WindowSummary:
    """Aggregated result of several frames - what gets stored as one Analysis."""
    frames: int = 0
    faces: int = 0
    probs: list = field(default_factory=list)
    matches: list = field(default_factory=list)
    qualities: list = field(default_factory=list)
    capture_ms: float = 0.0
    face_ms: float = 0.0
    inference_ms: float = 0.0

    def add(self, fr: FrameResult, capture_ms=0.0):
        self.frames += 1
        self.capture_ms += capture_ms
        self.face_ms += fr.face_ms
        self.inference_ms += fr.inference_ms
        if fr.face_found:
            self.faces += 1
            self.probs.append(fr.deepfake_prob)
            self.qualities.append(fr.quality)
            if fr.identity_match is not None:
                self.matches.append(fr.identity_match)

    @property
    def deepfake_prob(self):
        # Temporal aggregation: mean over the window, so one odd frame cannot dominate
        return float(np.mean(self.probs)) if self.probs else 0.0

    @property
    def identity_match(self):
        return float(np.median(self.matches)) if self.matches else None

    @property
    def quality(self):
        return float(np.mean(self.qualities)) if self.qualities else 0.0


def system_usage():
    return _process.cpu_percent(interval=None), _process.memory_info().rss / (1024 * 1024)


def sample_video(path, sample_fps, max_frames):
    """Yield (frame, capture_ms) for frames sampled evenly - analysing every frame
    of a 30 FPS video is unnecessary; 2 frames per second is enough for scoring."""
    cap = cv2.VideoCapture(opencv_path(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        step = max(int(round(fps / sample_fps)), 1)
        if total and total / step > max_frames:
            step = max(total // max_frames, 1)
        index, produced = 0, 0
        while produced < max_frames:
            t0 = time.perf_counter()
            if not cap.grab():
                break
            if index % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                produced += 1
                yield frame, (time.perf_counter() - t0) * 1000
            index += 1
    finally:
        cap.release()


def analyze_video(path, reference_embedding=None):
    cfg = current_app.config
    start = time.perf_counter()
    system_usage()  # prime the CPU counter
    window = WindowSummary()
    for frame, capture_ms in sample_video(path, cfg["SAMPLE_FPS"], cfg["MAX_SAMPLED_FRAMES"]):
        window.add(analyze_frame(frame, reference_embedding), capture_ms)
    return window, (time.perf_counter() - start) * 1000


def is_readable_video(path):
    """Content check (not only the extension): OpenCV must be able to decode a frame."""
    cap = cv2.VideoCapture(opencv_path(path))
    ok, frame = cap.read()
    cap.release()
    return bool(ok and frame is not None)
