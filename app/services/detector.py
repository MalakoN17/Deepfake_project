from __future__ import annotations
"""Deepfake detection models.

All detectors share one interface:  predict(face_rgb_256) -> probability of FAKE (0..1)
so the model can be replaced (e.g. by a stronger EfficientNet/Xception ONNX model)
without touching the rest of the system.
"""
import threading

import cv2
import numpy as np

from .cv_io import read_buffer


class MesoNetDetector:
    """MesoNet Meso4 (Afchar et al., WIFS 2018) - a compact CNN designed for
    compressed video. ~28k parameters, a few milliseconds per face on a CPU.
    Weights: original Meso4_DF (Apache-2.0), converted to ONNX (scripts/convert_mesonet.py)."""
    name = "MesoNet-Meso4-DF"

    def __init__(self, model_path):
        self.net = cv2.dnn.readNetFromONNX(read_buffer(model_path))  # buffer: safe for any folder name
        self._lock = threading.Lock()

    def predict(self, face_bgr_256):
        rgb = cv2.cvtColor(face_bgr_256, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = rgb.transpose(2, 0, 1)[None]          # HWC -> NCHW
        with self._lock:
            self.net.setInput(blob)
            prob_real = float(self.net.forward()[0, 0])
        return 1.0 - prob_real                        # model outputs P(real)


class DummyDetector:
    """Deterministic stand-in used by the automated tests (no model files needed)."""
    name = "dummy"

    def predict(self, face_bgr_256):
        return float(np.clip(face_bgr_256.mean() / 255.0, 0, 1))


def load_detector(config):
    if config.get("DETECTOR_BACKEND") == "dummy":
        return DummyDetector()
    return MesoNetDetector(config["MODEL_DIR"] / "meso4_df.onnx")
