from __future__ import annotations
"""Application factory: creates and configures the Flask app."""
from flask import Flask, render_template

from config import Config

from .extensions import csrf, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__, instance_path=str(config_class.INSTANCE_DIR))
    app.config.from_object(config_class)
    for folder in (app.config["INSTANCE_DIR"], app.config["UPLOAD_DIR"], app.config["REFERENCE_DIR"]):
        folder.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .routes.analysis import bp as analysis_bp
    from .routes.auth import bp as auth_bp
    from .routes.identities import bp as identities_bp
    from .routes.main import bp as main_bp
    for blueprint in (main_bp, auth_bp, analysis_bp, identities_bp):
        app.register_blueprint(blueprint)

    from .cli import register_cli
    register_cli(app)
    register_template_helpers(app)
    register_error_pages(app)

    @app.after_request
    def security_headers(response):
        # Defence in depth against XSS, clickjacking and MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(self), display-capture=(self), microphone=()"
        # All scripts, styles and fonts are served locally - nothing loads from other sites
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
        return response

    with app.app_context():
        db.create_all()

    from .services.cv_io import path_is_safe
    if not path_is_safe(app.config["MODEL_DIR"]):
        app.logger.warning("The project path contains non-English characters, which OpenCV on Windows "
                           "cannot always open. Recommended: move it to C:\\projects\\deepfake-detection-system")
    return app


def register_template_helpers(app):
    @app.template_filter("dt")
    def format_dt(value, fmt="%d/%m/%Y %H:%M:%S"):
        return value.strftime(fmt) if value else "-"

    @app.template_filter("ms")
    def format_ms(value):
        if value is None:
            return "-"
        return f"{value / 1000:.2f} s" if value >= 1000 else f"{value:.0f} ms"

    @app.context_processor
    def inject_globals():
        return {"org_name": "GlobalTech Solutions",
                "result_class": {"Approved": "ok", "Suspicious": "warn", "Rejected": "bad"},
                "severity_class": {"Warning": "warn", "High": "bad", "Critical": "crit"}}


def register_error_pages(app):
    for code, title, text in [
        (403, "Access denied", "Your role does not allow this page. Ask an administrator if you need access."),
        (404, "Page not found", "The address does not exist. Check the link or go back to the dashboard."),
        (413, "File too large", "The upload is bigger than the allowed limit. Trim the video and try again."),
        (500, "Something failed on the server", "The error was logged. Try again, and if it repeats check the server console."),
    ]:
        def handler(error, code=code, title=title, text=text):
            if code == 500:
                db.session.rollback()
            return render_template("error.html", code=code, title=title, text=text), code
        app.register_error_handler(code, handler)
