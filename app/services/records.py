from __future__ import annotations
"""Persisting results: Analysis rows, Alerts (with cooldown) and the audit log."""
from datetime import timedelta

from flask import current_app, request
from flask_login import current_user

from ..extensions import db
from ..models import Alert, Analysis, AuditLog, utcnow
from . import risk
from .pipeline import get_models, system_usage


def audit(event, details="", user=None):
    uid = user.user_id if user else (current_user.user_id if current_user and current_user.is_authenticated else None)
    db.session.add(AuditLog(user_id=uid, event=event, details=details[:300],
                            ip_address=request.remote_addr if request else None))


def save_analysis(meeting, window, processing_ms):
    cfg = current_app.config
    rr = risk.evaluate(window.deepfake_prob, window.identity_match, window.quality, window.faces > 0, cfg,
                       identity_required=meeting.claimed_identity_id is not None)
    cpu, ram = system_usage()
    _, detector = get_models()
    analysis = Analysis(
        meeting=meeting, frames_analyzed=window.frames, faces_detected=window.faces,
        deepfake_score=rr.risk_score, identity_match_score=window.identity_match,
        quality_score=round(window.quality, 1), trust_score=rr.trust_score, result=rr.result,
        reasons="; ".join(rr.reasons), capture_ms=round(window.capture_ms, 1),
        face_ms=round(window.face_ms, 1), inference_ms=round(window.inference_ms, 1),
        processing_time_ms=round(processing_ms, 1), cpu_percent=round(cpu, 1),
        ram_mb=round(ram, 1), model_name=detector.name)
    db.session.add(analysis)
    alert = maybe_alert(meeting, analysis, rr)
    db.session.commit()
    return analysis, alert


def maybe_alert(meeting, analysis, rr):
    """Create an alert for Suspicious/Rejected results. In live sessions a cooldown
    prevents flooding the security team, unless the severity increases."""
    if rr.severity is None:
        return None
    order = {"Warning": 1, "High": 2, "Critical": 3}
    cooldown = timedelta(seconds=current_app.config["ALERT_COOLDOWN_SECONDS"])
    recent = (Alert.query.join(Analysis).filter(Analysis.meeting_id == meeting.meeting_id,
                                                Alert.timestamp >= utcnow() - cooldown)
              .order_by(Alert.timestamp.desc()).first()) if meeting.meeting_id else None
    if recent and order[recent.severity] >= order[rr.severity]:
        return None
    who = meeting.claimed_identity.full_name if meeting.claimed_identity else "participant"
    if rr.result == "Rejected":
        headline = "Potential deepfake detected" if rr.risk_score >= current_app.config["RISK_REJECTED"] \
            else "Identity mismatch detected"
    else:
        headline = "Suspicious video - additional verification recommended"
    message = f"{headline} ({who}, {meeting.meeting_name}). Risk {rr.risk_score:.0f}%. {rr.reasons[0]}"
    alert = Alert(analysis=analysis, severity=rr.severity, message=message[:300])
    db.session.add(alert)
    return alert
