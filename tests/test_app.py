from __future__ import annotations
"""Automated tests - run with:  pytest -v
They cover the test plan of the project: login, protected routes, uploads,
live analysis, alerts, logging, the risk engine and security controls."""
import io

import cv2
import numpy as np
import pytest

from app.extensions import db
from app.models import Alert, Analysis, AuditLog, Meeting, User
from app.services.risk import Smoother, evaluate
from config import Config, TestConfig
from conftest import login

CFG = {k: getattr(TestConfig, k) for k in dir(TestConfig) if k.isupper()}


def make_video(path, frames=20, size=(320, 240)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, size)
    for i in range(frames):
        frame = np.full((size[1], size[0], 3), 40 + i * 5, np.uint8)
        writer.write(frame)
    writer.release()
    return path


# ---------- Flask basics (course requirements) ----------
def test_home_page(client):
    assert client.get("/").status_code == 200


def test_dynamic_route_escapes_input(client):
    html = client.get("/user/<img src=x onerror=alert(1)>").get_data(as_text=True)
    assert "&lt;img" in html and "<img src=x" not in html


def test_custom_404(client):
    res = client.get("/no-such-page")
    assert res.status_code == 404 and "Page not found" in res.get_data(as_text=True)


# ---------- Authentication and authorization ----------
@pytest.mark.parametrize("url", ["/dashboard", "/logs", "/alerts", "/analysis/upload", "/analysis/live", "/api/dashboard"])
def test_protected_routes_require_login(client, url):
    res = client.get(url)
    assert res.status_code == 302 and "/login" in res.location


def test_login_success(client):
    res = login(client)
    assert res.status_code == 302 and res.location.endswith("/dashboard")
    assert client.get("/dashboard").status_code == 200


def test_login_wrong_password(client):
    res = login(client, password="wrong")
    assert res.status_code == 200 and "Email or password is incorrect" in res.get_data(as_text=True)


def test_unknown_email_gets_same_message(client):
    res = login(client, email="nobody@test.com")
    assert "Email or password is incorrect" in res.get_data(as_text=True)


def test_password_is_hashed(app):
    user = User.query.filter_by(email="admin@test.com").first()
    assert "Correct-Pass1" not in user.password_hash and user.check_password("Correct-Pass1")


def test_lockout_after_repeated_failures(client, app):
    for _ in range(Config.LOGIN_MAX_ATTEMPTS):
        login(client, password="wrong")
    res = login(client)  # correct password, but the account is locked now
    assert res.status_code == 429
    assert AuditLog.query.filter_by(event="account_locked").count() == 1


def test_open_redirect_blocked(client):
    res = client.post("/login?next=https://evil.example.com", data={"email": "admin@test.com", "password": "Correct-Pass1"})
    assert res.location.endswith("/dashboard")


def test_analyst_cannot_open_admin_pages(client):
    login(client, email="analyst@test.com")
    assert client.get("/identities/").status_code == 403
    assert client.get("/audit").status_code == 403


def test_logout_requires_post(client):
    login(client)
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_security_headers(client):
    headers = client.get("/").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"


# ---------- Risk engine ----------
@pytest.mark.parametrize("prob,identity,quality,faces,expected", [
    (0.10, None, 80, True, "Approved"),
    (0.50, None, 80, True, "Suspicious"),
    (0.85, None, 80, True, "Rejected"),
    (0.10, 90, 80, True, "Approved"),
    (0.10, 30, 80, True, "Suspicious"),   # weak identity match
    (0.10, 5, 80, True, "Rejected"),      # identity mismatch
    (0.10, None, 20, True, "Suspicious"), # low quality never gives Approved
    (0.10, None, 80, False, "Suspicious"),# no face
])
def test_risk_engine_classes(prob, identity, quality, faces, expected):
    assert evaluate(prob, identity, quality, faces, CFG).result == expected


def test_identity_required_but_unverifiable_is_not_approved():
    assert evaluate(0.10, None, 80, True, CFG, identity_required=True).result == "Suspicious"


def test_critical_severity():
    assert evaluate(0.95, None, 80, True, CFG).severity == "Critical"


def test_trust_score_without_identity():
    assert evaluate(0.2, None, 100, True, CFG).trust_score == pytest.approx(80, abs=0.1)


def test_smoother_ignores_single_spike():
    s = Smoother(5)
    values = [s.add(v) for v in (0.20, 0.25, 0.87, 0.22)]
    assert max(values) < 0.70   # one 87% frame alone does not reach the Rejected threshold


# ---------- Video upload ----------
def upload(client, filename, content):
    return client.post("/analysis/upload", data={"meeting_name": "Test", "platform": "Zoom", "claimed_identity": "0",
                                                 "video": (content, filename)}, content_type="multipart/form-data")


def test_upload_rejects_wrong_extension(client):
    login(client)
    res = upload(client, "malware.exe", io.BytesIO(b"MZ..."))
    assert "Only MP4, AVI or MOV" in res.get_data(as_text=True)
    assert Meeting.query.count() == 0


def test_upload_rejects_fake_video_content(client):
    login(client)
    res = upload(client, "fake.mp4", io.BytesIO(b"this is not a video"))
    assert res.status_code == 400 and Meeting.query.count() == 0


def test_upload_video_is_analysed_saved_and_deleted(client, app, tmp_path):
    login(client)
    video = make_video(tmp_path / "meeting.mp4")
    res = upload(client, "meeting.mp4", open(video, "rb"))
    assert res.status_code == 302
    analysis = Analysis.query.one()
    assert analysis.frames_analyzed > 0 and analysis.processing_time_ms > 0
    assert analysis.result == "Suspicious"          # synthetic video has no face
    assert Alert.query.count() == 1                 # suspicious -> alert
    assert list(app.config["UPLOAD_DIR"].glob("*")) == []   # file deleted (privacy)


# ---------- Live analysis ----------
def test_live_session_saves_windows(client, app):
    login(client)
    token = client.post("/analysis/api/live/start", json={"meeting_name": "Live", "platform": "Teams"}).get_json()
    meeting_id = token["meeting_id"]
    ok, jpg = cv2.imencode(".jpg", np.zeros((240, 320, 3), np.uint8))
    for _ in range(CFG["LIVE_WINDOW_FRAMES"] + 1):
        res = client.post(f"/analysis/api/live/{meeting_id}/frame",
                          data={"frame": (io.BytesIO(jpg.tobytes()), "f.jpg")}, content_type="multipart/form-data")
        data = res.get_json()
        assert res.status_code == 200 and "server_ms" in data and data["first_score_ms"] > 0
    assert client.post(f"/analysis/api/live/{meeting_id}/stop").status_code == 200
    assert Analysis.query.filter_by(meeting_id=meeting_id).count() == 2   # one full window + remainder
    assert db.session.get(Meeting, meeting_id).status == "completed"


def test_live_frame_rejects_invalid_image(client):
    login(client)
    meeting_id = client.post("/analysis/api/live/start", json={}).get_json()["meeting_id"]
    res = client.post(f"/analysis/api/live/{meeting_id}/frame",
                      data={"frame": (io.BytesIO(b"garbage"), "f.jpg")}, content_type="multipart/form-data")
    assert res.status_code == 400


# ---------- Alerts, logs, dashboard ----------
def test_alert_workflow_is_audited(client, app, tmp_path):
    login(client)
    upload(client, "meeting.mp4", open(make_video(tmp_path / "m.mp4"), "rb"))
    alert = Alert.query.one()
    client.post(f"/alerts/{alert.alert_id}/escalate")
    assert db.session.get(Alert, alert.alert_id).status == "Escalated"
    assert AuditLog.query.filter_by(event="alert_escalate").count() == 1


def test_dashboard_api_and_logs(client, tmp_path):
    login(client)
    upload(client, "meeting.mp4", open(make_video(tmp_path / "m.mp4"), "rb"))
    data = client.get("/api/dashboard").get_json()
    assert data["total"] == 1 and data["suspicious"] == 1 and data["open_alerts"] == 1
    assert "Test" in client.get("/logs?result=Suspicious").get_data(as_text=True)
    csv_text = client.get("/logs/export.csv").get_data(as_text=True)
    assert csv_text.startswith("analysis_id") and "Suspicious" in csv_text


# ---------- Real model files ----------
def test_mesonet_model_runs():
    from app.services.detector import MesoNetDetector
    detector = MesoNetDetector(Config.MODEL_DIR / "meso4_df.onnx")
    prob = detector.predict(np.full((256, 256, 3), 128, np.uint8))
    assert 0.0 <= prob <= 1.0


# ---------- Reference identities ----------
def test_identity_upload_without_face_shows_message(client, app):
    login(client)
    ok, png = cv2.imencode(".png", np.full((400, 400, 3), 200, np.uint8))
    res = client.post("/identities/", data={"full_name": "Test Person", "job_title": "CEO",
                                            "photo": (io.BytesIO(png.tobytes()), "photo.png")},
                      content_type="multipart/form-data")
    assert res.status_code == 200 and "No face was found" in res.get_data(as_text=True)


def test_identity_upload_error_is_reported_not_500(client, app, monkeypatch):
    import app.routes.identities as identities
    monkeypatch.setattr(identities, "get_models", lambda: (_ for _ in ()).throw(RuntimeError("model file broken")))
    login(client)
    ok, jpg = cv2.imencode(".jpg", np.full((400, 400, 3), 200, np.uint8))
    res = client.post("/identities/", data={"full_name": "Test", "job_title": "CEO",
                                            "photo": (io.BytesIO(jpg.tobytes()), "photo.jpg")},
                      content_type="multipart/form-data")
    assert res.status_code == 200 and "model file broken" in res.get_data(as_text=True)


def test_models_load_from_folder_with_hebrew_name(tmp_path):
    import shutil
    from app.services.detector import MesoNetDetector
    from app.services.faces import FaceAnalyzer
    folder = tmp_path / "שולחן העבודה" / "ml_models"
    shutil.copytree(Config.MODEL_DIR, folder)
    FaceAnalyzer(folder)
    assert 0 <= MesoNetDetector(folder / "meso4_df.onnx").predict(np.zeros((256, 256, 3), np.uint8)) <= 1
