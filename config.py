from __future__ import annotations
"""Central configuration. Secrets and environment-specific values come from .env"""
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


class Config:
    # --- Security -------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)  # set it in .env!
    SESSION_COOKIE_HTTPONLY = True          # JavaScript cannot read the session cookie
    SESSION_COOKIE_SAMESITE = "Lax"         # basic CSRF protection at cookie level
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE")  # True when served over HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    WTF_CSRF_TIME_LIMIT = None              # token valid for the whole session
    LOGIN_MAX_ATTEMPTS = 5                  # failed logins before lockout
    LOGIN_LOCK_MINUTES = 5

    # --- Database -------------------------------------------------------
    INSTANCE_DIR = BASE_DIR / "instance"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'app.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Uploads --------------------------------------------------------
    UPLOAD_DIR = INSTANCE_DIR / "uploads"          # temporary, deleted after analysis
    REFERENCE_DIR = INSTANCE_DIR / "references"    # reference photos (biometric data!)
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov"}
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
    KEEP_UPLOADED_VIDEOS = env_bool("KEEP_UPLOADED_VIDEOS")  # privacy: delete by default

    # --- AI models ------------------------------------------------------
    MODEL_DIR = BASE_DIR / "ml_models"
    DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "mesonet")  # "mesonet" or "dummy"

    # --- Analysis parameters (initial values - tune after testing) ------
    SAMPLE_FPS = 2            # frames per second sampled from an uploaded video
    MAX_SAMPLED_FRAMES = 40   # upper bound per uploaded video
    LIVE_WINDOW_FRAMES = 5    # live: one Analysis record per 5 analysed frames
    SMOOTHING_WINDOW = 5      # moving average over the last N frame scores
    FACE_CONFIDENCE = 0.6     # minimum face detector confidence
    FACE_CROP_MARGIN = 0.5    # crop = face box x 2 (0.2 gave many false positives on real faces)

    # Risk engine thresholds (percent). Match the classes promised in the
    # Problem Identification document: Approved / Suspicious / Rejected.
    RISK_SUSPICIOUS = 31
    RISK_REJECTED = 70
    RISK_CRITICAL = 90
    IDENTITY_OK = 45          # identity match score needed for Approved
    IDENTITY_REJECT = 20      # below this the claimed identity is rejected
    QUALITY_MIN = 40          # below this an Approved result is downgraded
    MIN_FACE_FOR_IDENTITY = 60  # pixels; smaller faces are not compared with the reference
    ALERT_COOLDOWN_SECONDS = 30


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DETECTOR_BACKEND = "dummy"
