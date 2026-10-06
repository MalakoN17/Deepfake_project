from __future__ import annotations
"""Home page, dynamic route, dashboard, logs, alerts and audit log."""
import csv
import io
from urllib.parse import urlencode
from datetime import datetime, timedelta

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from ..decorators import admin_required
from ..extensions import db
from ..models import Alert, Analysis, AuditLog, Meeting, User, utcnow
from ..services import live
from ..services.records import audit

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("index.html", title="Home Page")


@bp.route("/user/<name>")
def user(name):
    # Jinja2 escapes {{ name }} automatically, so /user/<script>... cannot inject code
    return render_template("user.html", name=name)


def dashboard_data():
    total = db.session.query(func.count(Analysis.analysis_id)).scalar()
    by_result = dict(db.session.query(Analysis.result, func.count()).group_by(Analysis.result).all())
    avg_risk = db.session.query(func.avg(Analysis.deepfake_score)).scalar() or 0
    avg_ms = db.session.query(func.avg(Analysis.processing_time_ms)).scalar() or 0
    open_alerts = Alert.query.filter(Alert.status.in_(["Open", "Escalated"])).count()
    recent = Analysis.query.order_by(Analysis.timestamp.desc()).limit(8).all()
    trend = list(reversed(Analysis.query.order_by(Analysis.timestamp.desc()).limit(30).all()))
    return {
        "total": total, "approved": by_result.get("Approved", 0),
        "suspicious": by_result.get("Suspicious", 0), "rejected": by_result.get("Rejected", 0),
        "avg_risk": round(avg_risk, 1), "avg_processing_ms": round(avg_ms), "open_alerts": open_alerts,
        "live_sessions": live.active_count(),
        "recent": [{"id": a.analysis_id, "meeting_id": a.meeting_id, "user": a.meeting.user.name,
                    "meeting": a.meeting.meeting_name, "risk": a.deepfake_score, "trust": a.trust_score,
                    "result": a.result, "processing_ms": a.processing_time_ms,
                    "timestamp": a.timestamp.strftime("%d/%m/%Y %H:%M:%S")} for a in recent],
        "trend": {"labels": [a.timestamp.strftime("%d/%m %H:%M") for a in trend],
                  "risk": [a.deepfake_score for a in trend]},
    }


@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", data=dashboard_data())


@bp.route("/api/dashboard")
@login_required
def api_dashboard():
    return jsonify(dashboard_data())


def filtered_logs():
    q = Analysis.query.join(Meeting).join(User)
    args = request.args
    if args.get("result"):
        q = q.filter(Analysis.result == args["result"])
    if args.get("min_risk"):
        try:
            q = q.filter(Analysis.deepfake_score >= float(args["min_risk"]))
        except ValueError:
            pass
    for key, op in (("date_from", "ge"), ("date_to", "le")):
        if args.get(key):
            try:
                day = datetime.strptime(args[key], "%Y-%m-%d")
                q = q.filter(Analysis.timestamp >= day) if op == "ge" else \
                    q.filter(Analysis.timestamp < day + timedelta(days=1))
            except ValueError:
                pass
    if args.get("q"):
        term = f"%{args['q'][:50]}%"   # SQLAlchemy binds parameters -> no SQL injection
        q = q.filter(or_(Meeting.meeting_name.ilike(term), User.name.ilike(term), Meeting.platform.ilike(term)))
    return q.order_by(Analysis.timestamp.desc())


@bp.route("/logs")
@login_required
def logs():
    page = filtered_logs().paginate(page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    return render_template("logs.html", page=page, args=request.args)


@bp.route("/logs/export.csv")
@login_required
def logs_csv():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["analysis_id", "timestamp", "user", "meeting", "platform", "deepfake_risk", "trust",
                     "identity_match", "quality", "result", "frames", "faces", "capture_ms", "face_ms",
                     "inference_ms", "processing_ms", "cpu_percent", "ram_mb", "model", "reasons"])
    for a in filtered_logs().limit(5000):
        writer.writerow([a.analysis_id, a.timestamp.isoformat(), a.meeting.user.name, a.meeting.meeting_name,
                         a.meeting.platform, a.deepfake_score, a.trust_score, a.identity_match_score,
                         a.quality_score, a.result, a.frames_analyzed, a.faces_detected, a.capture_ms,
                         a.face_ms, a.inference_ms, a.processing_time_ms, a.cpu_percent, a.ram_mb,
                         a.model_name, a.reasons])
    audit("logs_exported")
    db.session.commit()
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=analysis_logs.csv"})


ALERT_ACTIONS = {"acknowledge": "Acknowledged", "escalate": "Escalated", "resolve": "Resolved"}


@bp.route("/alerts")
@login_required
def alerts():
    status = request.args.get("status", "active")
    q = Alert.query
    if status == "active":
        q = q.filter(Alert.status.in_(["Open", "Acknowledged", "Escalated"]))
    elif status in ALERT_ACTIONS.values() or status == "Open":
        q = q.filter(Alert.status == status)
    order = db.case({"Critical": 0, "High": 1, "Warning": 2}, value=Alert.severity)
    items = q.order_by(order, Alert.timestamp.desc()).limit(200).all()
    return render_template("alerts.html", alerts=items, status=status)


@bp.route("/alerts/<int:alert_id>/<action>", methods=["POST"])
@login_required
def update_alert(alert_id, action):
    if action not in ALERT_ACTIONS:
        abort(404)
    alert = db.get_or_404(Alert, alert_id)
    alert.status, alert.handled_by, alert.handled_at = ALERT_ACTIONS[action], current_user.user_id, utcnow()
    audit("alert_" + action, f"alert_id={alert_id}")
    db.session.commit()
    if action == "escalate":
        flash("Alert escalated. Verify the participant through a second channel "
              "(phone call to a known number, MFA or in-person) before any sensitive action.", "warn")
    else:
        flash(f"Alert {alert_id} marked as {alert.status.lower()}.", "info")
    return redirect(request.referrer or url_for("main.alerts"))


@bp.route("/audit")
@login_required
@admin_required
def audit_log():
    items = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(300).all()
    return render_template("audit.html", items=items)


@bp.app_context_processor
def sidebar_counts():
    def open_alerts():
        return Alert.query.filter(Alert.status.in_(["Open", "Escalated"])).count() \
            if current_user.is_authenticated else 0
    def query_with_page(number):
        params = request.args.to_dict()
        params["page"] = number
        return urlencode(params)
    return {"open_alert_count": open_alerts, "query_with_page": query_with_page}
