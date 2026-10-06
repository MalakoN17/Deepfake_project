from __future__ import annotations
"""Face detection (OpenCV DNN, ResNet-10 SSD) and face embeddings (OpenFace)
for identity verification. Both run on CPU through cv2.dnn - no GPU needed."""
import threading
from pathlib import Path

import cv2
import numpy as np

from .cv_io import opencv_path, read_buffer


class FaceAnalyzer:
    def __init__(self, model_dir: Path, min_confidence=0.6):
        self.min_confidence = min_confidence
        self._lock = threading.Lock()  # cv2.dnn nets are not thread-safe
        for name in ("face_detector.prototxt", "face_detector.caffemodel", "openface_nn4.small2.v1.t7"):
            if not (model_dir / name).exists():
                raise FileNotFoundError(f"Model file missing: ml_models/{name} - run: python scripts/download_models.py")
        # Loaded from memory buffers, so non-English folder names cannot break it
        self.detector = cv2.dnn.readNetFromCaffe(read_buffer(model_dir / "face_detector.prototxt"),
                                                 read_buffer(model_dir / "face_detector.caffemodel"))
        t7 = model_dir / "openface_nn4.small2.v1.t7"
        try:
            self.embedder = cv2.dnn.readNetFromTorch(opencv_path(t7))  # Torch format has no buffer loader
        except cv2.error as exc:
            raise RuntimeError(
                f"OpenCV could not open {t7}. If the folder path contains Hebrew or other non-English "
                "characters, move the project to a path like C:\\projects\\deepfake-detection-system") from exc

    def detect(self, frame_bgr):
        """Return a list of (confidence, (x1, y1, x2, y2)) sorted by face size (largest first)."""
        h, w = frame_bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame_bgr, (300, 300)), 1.0, (300, 300), (104, 177, 123))
        with self._lock:
            self.detector.setInput(blob)
            out = self.detector.forward()[0, 0]
        faces = []
        for det in out:
            conf = float(det[2])
            if conf < self.min_confidence:
                continue
            x1, y1, x2, y2 = (det[3:7] * [w, h, w, h]).astype(int)
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
            if x2 - x1 > 10 and y2 - y1 > 10:
                faces.append((conf, (x1, y1, x2, y2)))
        return sorted(faces, key=lambda f: (f[1][2] - f[1][0]) * (f[1][3] - f[1][1]), reverse=True)

    def embed(self, frame_bgr, box):
        """128-d L2-normalised embedding of the face inside box."""
        x1, y1, x2, y2 = box
        face = frame_bgr[y1:y2, x1:x2]
        blob = cv2.dnn.blobFromImage(face, 1 / 255.0, (96, 96), (0, 0, 0), swapRB=True)
        with self._lock:
            self.embedder.setInput(blob)
            vec = self.embedder.forward()[0].astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-9)


def crop_face(frame_bgr, box, margin=0.5, size=256):
    """Square crop around the face. margin=0.5 -> the crop is 2x the detected face box,
    which matches the loose crops MesoNet was trained on (hair, ears and some background).
    Parts outside the frame are filled by repeating the edge, so the face is never stretched."""
    x1, y1, x2, y2 = box
    side = int(max(x2 - x1, y2 - y1) * (1 + 2 * margin))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    left, top = cx - side // 2, cy - side // 2
    h, w = frame_bgr.shape[:2]
    pad = max(0, -left, -top, left + side - w, top + side - h)
    if pad:
        frame_bgr = cv2.copyMakeBorder(frame_bgr, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        left, top = left + pad, top + pad
    return cv2.resize(frame_bgr[top:top + side, left:left + side], (size, size), interpolation=cv2.INTER_AREA)


def quality_score(frame_bgr, box):
    """0-100 estimate of how usable the face region is.
    Combines face size, sharpness (variance of Laplacian) and exposure.
    Low quality -> the system lowers its confidence (see risk engine)."""
    x1, y1, x2, y2 = box
    face = cv2.cvtColor(frame_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    size_s = min((x2 - x1) / 120.0, 1.0)                       # >=120px face = full score
    sharp_s = min(cv2.Laplacian(face, cv2.CV_64F).var() / 150.0, 1.0)
    brightness = float(face.mean())
    expo_s = 1.0 - min(abs(brightness - 125) / 125.0, 1.0)
    return round(100 * (0.45 * size_s + 0.35 * sharp_s + 0.20 * expo_s), 1)


def identity_match_score(similarity):
    """Map cosine similarity of two OpenFace embeddings to 0-100.
    Measured on sample images: same person 0.67-0.99 (blur, JPEG, scale, lighting),
    different people ~0.53. These bounds are initial values - calibrate them with
    your own reference photos and webcam (see README, "Calibrating identity")."""
    low, high = 0.50, 0.80
    return round(float(np.clip((similarity - low) / (high - low), 0, 1) * 100), 1)
