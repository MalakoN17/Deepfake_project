from __future__ import annotations
"""Download the face detection / recognition models into ml_models/ (if they are missing).
The deepfake model (meso4_df.onnx) is small and already included in the repository.

Usage:  python scripts/download_models.py
"""
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml_models"
FILES = {
    "face_detector.prototxt":
        "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/dnn/face_detector/deploy.prototxt",
    "face_detector.caffemodel":
        "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20180205_fp16/"
        "res10_300x300_ssd_iter_140000_fp16.caffemodel",
    "openface_nn4.small2.v1.t7":
        "https://raw.githubusercontent.com/pyannote/pyannote-data/master/openface.nn4.small2.v1.t7",
}

if __name__ == "__main__":
    MODEL_DIR.mkdir(exist_ok=True)
    for name, url in FILES.items():
        target = MODEL_DIR / name
        if target.exists() and target.stat().st_size > 1000:
            print(f"ok       {name}")
            continue
        print(f"download {name} ...")
        urllib.request.urlretrieve(url, target)
        print(f"saved    {name} ({target.stat().st_size / 1e6:.1f} MB)")
