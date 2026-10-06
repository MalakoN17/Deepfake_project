from __future__ import annotations
"""Video upload analysis and live (webcam / screen share) analysis."""
import time
import uuid

import cv2
import numpy as np
from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..extensions import db
from ..forms import PLATFORMS, UploadForm
from ..models import Meeting, ReferenceIdentity, utcnow
from ..services import live
from ..services.pipeline import analyze_frame, analyze_video, is_readable_video
from ..services.records import audit, save_analysis
from ..services.risk import evaluate

bp = Blueprint("analysis", __name__, url_prefix="/analysis")


def identity_choices():
    return [(0, "No claimed identity")] + [
        (i.identity_id, f"{i.full_name} - {i.job_title}")
        for i in ReferenceIdentity.query.order_by(ReferenceIdentity.full_name)]


@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = UploadForm()
    form.claimed_identity.choices = identity_choices()
    if form.validate_on_submit():
        file = form.video.data
        ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower()
        if ext not in current_app.config["ALLOWED_VIDEO_EXTENSIONS"]:
            flash("Only MP4, AVI or MOV videos are allowed.", "error")
            return render_template("upload.html", form=form), 400
        # Random server-side name: the user's filename is never used as a path
        path = current_app.config["UPLOAD_DIR"] / f"{uuid.uuid4().hex}.{ext}"
        file.save(path)
        try:
            if not is_readable_video(path):
                flash("The file could not be decoded as a video. Upload a valid MP4, AVI or MOV file.", "error")
                return render_template("upload.html", form=form), 400
            identity = db.session.get(ReferenceIdentity, form.claimed_identity.data) \
                if form.claimed_identity.data else None
            meeting = Meeting(user_id=current_user.user_id, meeting_name=form.meeting_name.data.strip(),
                              platform=form.platform.data, source_type="upload", claimed_identity=identity)
            db.session.add(meeting)
            db.session.commit()
            window, total_ms = analyze_video(path, identity.get_embedding() if identity else None)
            meeting.first_score_ms, meeting.end_time, meeting.status = round(total_ms, 1), utcnow(), "completed"
            analysis, alert = save_analysis(meeting, window, total_ms)
            audit("analysis_upload", f"meeting_id={meeting.meeting_id} result={analysis.result}")
            db.session.commit()
            flash(f"Analysis complete: {analysis.result} (risk {analysis.deepfake_score:.0f}%).",
                  "error" if alert and alert.severity != "Warning" else "warn" if alert else "info")
            return redirect(url_for("analysis.detail", meeting_id=meeting.meeting_id))
        finally:
            if not current_app.config["KEEP_UPLOADED_VIDEOS"]:
                path.unlink(missing_ok=True)   # privacy: do not keep meeting recordings
    return render_template("upload.html", form=form)


@bp.route("/<int:meeting_id>")
@login_required
def detail(meeting_id):
    meeting = db.get_or_404(Meeting, meeting_id)
    return render_template("analysis_detail.html", meeting=meeting)


@bp.route("/live")
@login_required
def live_page():
    return render_template("live.html", identities=identity_choices(), platforms=PLATFORMS)


@bp.route("/api/live/start", methods=["POST"])
@login_required
def live_start():
    data = request.get_json(silent=True) or {}
    name = str(data.get("meeting_name", "")).strip()[:150] or f"Live session {utcnow():%d/%m %H:%M}"
    platform = data.get("platform") if data.get("platform") in dict(PLATFORMS) else "Other"
    source = "screen" if data.get("source") == "screen" else "webcam"
    try:
        identity_id = int(data.get("identity_id") or 0)
    except (TypeError, ValueError):
        identity_id = 0
    identity = db.session.get(ReferenceIdentity, identity_id) if identity_id else None
    meeting = Meeting(user_id=current_user.user_id, meeting_name=name, platform=platform,
                      source_type=source, claimed_identity=identity)
    db.session.add(meeting)
    audit("live_started", f"platform={platform} source={source}")
    db.session.commit()
    live.start(meeting.meeting_id, identity.get_embedding() if identity else None,
               current_app.config["SMOOTHING_WINDOW"])
    return jsonify({"meeting_id": meeting.meeting_id})


def own_live_meeting(meeting_id):
    meeting = db.get_or_404(Meeting, meeting_id)
    if meeting.user_id != current_user.user_id and not current_user.is_admin:
        abort(403)
    state = live.get(meeting_id)
    if state is None or meeting.status != "active":
        abort(409, description="Session is not active")
    return meeting, state


@bp.route("/api/live/<int:meeting_id>/frame", methods=["POST"])
@login_required
def live_frame(meeting_id):
    received = time.perf_counter()
    meeting, state = own_live_meeting(meeting_id)
    blob = request.files.get("frame")
    if blob is None:
        return jsonify({"error": "missing frame"}), 400
    raw = blob.read(3 * 1024 * 1024)                 # frames are small JPEGs; cap at 3 MB
    frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "invalid image"}), 400
    decode_ms = (time.perf_counter() - received) * 1000
    cfg = current_app.config

    with state.lock:
        fr = analyze_frame(frame, state.reference_embedding)
        state.frames_total += 1
        state.window.add(fr, decode_ms)
        smoothed_prob = state.smoother.add(fr.deepfake_prob) if fr.face_found else \
            (sum(state.smoother.values) / len(state.smoother.values) if state.smoother.values else 0.0)
        rr = evaluate(smoothed_prob, fr.identity_match, fr.quality, fr.face_found, cfg,
                      identity_required=state.reference_embedding is not None)
        if state.first_score_ms is None:
            state.first_score_ms = (time.perf_counter() - state.started) * 1000
            meeting.first_score_ms = round(state.first_score_ms, 1)
        saved = None
        if state.window.frames >= cfg["LIVE_WINDOW_FRAMES"]:
            window_ms = (time.perf_counter() - state.window_started) * 1000
            analysis, alert = save_analysis(meeting, state.window, window_ms)
            saved = {"analysis_id": analysis.analysis_id, "result": analysis.result,
                     "risk": analysis.deepfake_score,
                     "alert": {"severity": alert.severity, "message": alert.message} if alert else None}
            state.window = type(state.window)()
            state.window_started = time.perf_counter()
        else:
            db.session.commit()

    h, w = frame.shape[:2]
    box = None
    if fr.box:
        x1, y1, x2, y2 = fr.box
        box = [x1 / w, y1 / h, x2 / w, y2 / h]      # normalised for the browser overlay
    return jsonify({
        "face_found": fr.face_found, "box": box,
        "frame_risk": round(fr.deepfake_prob * 100, 1) if fr.face_found else None,
        "smoothed_risk": rr.risk_score, "trust": rr.trust_score, "result": rr.result,
        "reasons": rr.reasons, "identity_match": fr.identity_match, "quality": fr.quality,
        "server_ms": round((time.perf_counter() - received) * 1000, 1),
        "face_ms": round(fr.face_ms, 1), "inference_ms": round(fr.inference_ms, 1),
        "first_score_ms": round(state.first_score_ms, 1), "frames": state.frames_total, "saved": saved,
    })


@bp.route("/api/live/<int:meeting_id>/stop", methods=["POST"])
@login_required
def live_stop(meeting_id):
    meeting, state = own_live_meeting(meeting_id)
    with state.lock:
        if state.window.frames:
            save_analysis(meeting, state.window, (time.perf_counter() - state.window_started) * 1000)
        live.stop(meeting_id)
    meeting.status = "completed" if meeting.analyses else "failed"
    meeting.end_time = utcnow()
    audit("live_stopped", f"meeting_id={meeting_id} frames={state.frames_total}")
    db.session.commit()
    return jsonify({"redirect": url_for("analysis.detail", meeting_id=meeting_id)})
