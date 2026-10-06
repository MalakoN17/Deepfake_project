from __future__ import annotations
"""Database entities (see docs/ERD.md for the diagram).

Users 1--* Meetings 1--* Analyses 1--* Alerts
ReferenceIdentities 1--* Meetings   (the identity the participant claims to be)
Users 1--* AuditLogs
"""
from datetime import datetime, timezone

import numpy as np
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="analyst")  # admin / analyst
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)

    meetings = db.relationship("Meeting", back_populates="user")

    def get_id(self):  # required by Flask-Login
        return str(self.user_id)

    def set_password(self, password):
        # Werkzeug stores a salted hash (scrypt/pbkdf2) - never the password itself
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class ReferenceIdentity(db.Model):
    """A known employee (e.g. the CEO) with a reference photo and face embedding."""
    __tablename__ = "reference_identities"
    identity_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    job_title = db.Column(db.String(100), nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    embedding = db.Column(db.LargeBinary, nullable=False)  # 128 float32 values
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def get_embedding(self):
        return np.frombuffer(self.embedding, dtype=np.float32)


class Meeting(db.Model):
    """One monitored session: an uploaded video or a live webcam / screen-share session."""
    __tablename__ = "meetings"
    meeting_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    claimed_identity_id = db.Column(db.Integer, db.ForeignKey("reference_identities.identity_id"))
    meeting_name = db.Column(db.String(150), nullable=False)
    platform = db.Column(db.String(30), nullable=False)      # Zoom / Teams / Webcam / Upload / Other
    source_type = db.Column(db.String(20), nullable=False)   # upload / webcam / screen
    start_time = db.Column(db.DateTime, default=utcnow, nullable=False)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="active", nullable=False)  # active / completed / failed
    first_score_ms = db.Column(db.Float)  # time until the first risk score was available

    user = db.relationship("User", back_populates="meetings")
    claimed_identity = db.relationship("ReferenceIdentity")
    analyses = db.relationship("Analysis", back_populates="meeting",
                               cascade="all, delete-orphan", order_by="Analysis.timestamp")


class Analysis(db.Model):
    """One analysed window of video (a whole upload, or N frames of a live session)."""
    __tablename__ = "analyses"
    analysis_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.meeting_id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    frames_analyzed = db.Column(db.Integer, default=0, nullable=False)
    faces_detected = db.Column(db.Integer, default=0, nullable=False)
    deepfake_score = db.Column(db.Float, nullable=False)   # 0-100, "Deepfake Risk Score"
    identity_match_score = db.Column(db.Float)             # 0-100, null when no claimed identity
    quality_score = db.Column(db.Float, nullable=False)    # 0-100, input quality
    trust_score = db.Column(db.Float, nullable=False)      # 0-100
    result = db.Column(db.String(20), nullable=False, index=True)  # Approved / Suspicious / Rejected
    reasons = db.Column(db.String(500))
    # Latency measurements (milliseconds) - evidence for the real-time requirement
    capture_ms = db.Column(db.Float)
    face_ms = db.Column(db.Float)
    inference_ms = db.Column(db.Float)
    processing_time_ms = db.Column(db.Float, nullable=False)
    cpu_percent = db.Column(db.Float)
    ram_mb = db.Column(db.Float)
    model_name = db.Column(db.String(50))

    meeting = db.relationship("Meeting", back_populates="analyses")
    alerts = db.relationship("Alert", back_populates="analysis", cascade="all, delete-orphan")

    @property
    def risk_score(self):
        return self.deepfake_score


class Alert(db.Model):
    __tablename__ = "alerts"
    alert_id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analyses.analysis_id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)
    severity = db.Column(db.String(20), nullable=False)   # Warning / High / Critical
    message = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(20), default="Open", nullable=False)  # Open / Acknowledged / Escalated / Resolved
    handled_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    handled_at = db.Column(db.DateTime)

    analysis = db.relationship("Analysis", back_populates="alerts")
    handler = db.relationship("User")


class AuditLog(db.Model):
    """Security audit trail: logins, failures, lockouts, alert handling..."""
    __tablename__ = "audit_logs"
    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    event = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(45))
    details = db.Column(db.String(300))

    user = db.relationship("User")
