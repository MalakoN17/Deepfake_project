from __future__ import annotations
"""Unicode-safe file access for OpenCV.

On Windows, OpenCV's C++ file functions cannot open paths that contain non-English
characters - for example a Hebrew user name, or a project inside "שולחן העבודה" / OneDrive.
cv2.imread / cv2.imwrite / cv2.dnn.readNet* / cv2.VideoCapture then fail.
These helpers read and write the bytes with Python (which handles any path) instead.
"""
import os
from pathlib import Path

import cv2
import numpy as np


def read_buffer(path):
    """File contents as a uint8 array - works for any path on any OS."""
    return np.fromfile(str(path), dtype=np.uint8)


def opencv_path(path):
    """A path string OpenCV can open. On Windows, non-English paths are converted to the
    short 8.3 form (e.g. C:\\Users\\ABCD~1\\...), which contains only English characters."""
    p = str(path)
    if os.name != "nt" or p.isascii():
        return p
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024) and buf.value.isascii():
            return buf.value
    except Exception:
        pass
    return p


def path_is_safe(path):
    return os.name != "nt" or str(path).isascii() or opencv_path(path).isascii()


def imwrite(path, image):
    ok, encoded = cv2.imencode(Path(path).suffix or ".jpg", image)
    if not ok:
        raise ValueError("Could not encode the image")
    Path(path).write_bytes(encoded.tobytes())
