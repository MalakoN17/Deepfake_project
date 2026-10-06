from __future__ import annotations
"""Login / logout with password hashing, lockout after repeated failures and audit logging."""
from datetime import timedelta
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..forms import LoginForm
from ..models import User, utcnow
from ..services.records import audit

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        cfg = current_app.config
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.locked_until and user.locked_until > utcnow():
            audit("login_blocked_locked", f"email={user.email}", user)
            db.session.commit()
            flash(f"Too many failed attempts. The account is locked for {cfg['LOGIN_LOCK_MINUTES']} minutes.", "error")
            return render_template("login.html", form=form), 429
        if user and user.check_password(form.password.data):
            user.failed_logins, user.locked_until, user.last_login_at = 0, None, utcnow()
            session.clear()              # prevent session fixation
            login_user(user)
            session.permanent = True
            audit("login_success", user=user)
            db.session.commit()
            next_url = request.args.get("next", "")
            # Only allow relative redirects (prevents open-redirect attacks)
            if not next_url or urlparse(next_url).netloc or not next_url.startswith("/"):
                next_url = url_for("main.dashboard")
            return redirect(next_url)
        if user:
            user.failed_logins += 1
            if user.failed_logins >= cfg["LOGIN_MAX_ATTEMPTS"]:
                user.locked_until = utcnow() + timedelta(minutes=cfg["LOGIN_LOCK_MINUTES"])
                user.failed_logins = 0
                audit("account_locked", f"email={user.email}", user)
        audit("login_failed", f"email={form.email.data[:100]}", user)
        db.session.commit()
        # Same message for unknown email and wrong password (no user enumeration)
        flash("Email or password is incorrect.", "error")
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("logout")
    db.session.commit()
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
