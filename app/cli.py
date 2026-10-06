from __future__ import annotations
"""Command line helpers:
    flask --app run doctor         (checks that models, folders and the database work)
    flask --app run create-user --email admin@globaltech.com --name "Admin" --role admin
    flask --app run seed-demo      (demo users + sample data for the presentation)
"""
import random
from datetime import timedelta

import click

from .extensions import db
from .models import Alert, Analysis, Meeting, User, utcnow


def register_cli(app):
    @app.cli.command("doctor")
    def doctor():
        """Check the installation step by step and print what is wrong."""
        import os
        import platform
        import sys
        from pathlib import Path

        import cv2
        import numpy as np

        from .services.cv_io import imwrite, opencv_path, path_is_safe, read_buffer
        from .services.detector import MesoNetDetector
        from .services.faces import FaceAnalyzer

        cfg = app.config
        failures = 0

        def check(name, func):
            nonlocal failures
            try:
                detail = func()
                click.echo(f"OK    {name}" + (f"  ({detail})" if detail else ""))
            except Exception as exc:
                failures += 1
                click.echo(f"FAIL  {name}\n      -> {type(exc).__name__}: {exc}")

        def project_path():
            if not path_is_safe(cfg["MODEL_DIR"]):
                raise RuntimeError(f"'{cfg['MODEL_DIR'].parent}' contains non-English characters. "
                                   "Move the project to e.g. C:\\projects\\deepfake-detection-system")
            return str(cfg["MODEL_DIR"].parent)

        def secret():
            if not os.getenv("SECRET_KEY"):
                raise RuntimeError("SECRET_KEY is not set - run: python scripts/init_env.py")

        def faces_models():
            fa = FaceAnalyzer(cfg["MODEL_DIR"], cfg["FACE_CONFIDENCE"])
            img = np.full((300, 300, 3), 128, np.uint8)
            fa.detect(img)
            vec = fa.embed(img, (50, 50, 250, 250))
            return f"embedding size {vec.size}"

        def meso():
            p = MesoNetDetector(cfg["MODEL_DIR"] / "meso4_df.onnx").predict(np.full((256, 256, 3), 128, np.uint8))
            return f"test output {p:.3f}"

        def image_io():
            target = cfg["REFERENCE_DIR"] / "doctor_test.jpg"
            imwrite(target, np.zeros((64, 64, 3), np.uint8))
            ok = cv2.imdecode(read_buffer(target), cv2.IMREAD_COLOR) is not None
            target.unlink()
            if not ok:
                raise RuntimeError("image written but could not be read back")

        def video_io():
            target = Path(opencv_path(cfg["UPLOAD_DIR"])) / "doctor_test.mp4"
            writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
            for i in range(10):
                writer.write(np.full((120, 160, 3), i * 20, np.uint8))
            writer.release()
            cap = cv2.VideoCapture(opencv_path(target))
            ok, _ = cap.read()
            cap.release()
            target.unlink(missing_ok=True)
            if not ok:
                raise RuntimeError("OpenCV could not write/read a test video in instance/uploads")

        def database():
            return f"{User.query.count()} users, {Analysis.query.count()} analyses"

        click.echo(f"Python {sys.version.split()[0]} | OpenCV {cv2.__version__} | {platform.system()} {platform.release()}")
        for name, func in [("Project folder path", project_path), ("SECRET_KEY in .env", secret),
                           ("Face detection + identity models", faces_models), ("Deepfake model (MesoNet)", meso),
                           ("Save / read images (reference photos)", image_io),
                           ("Save / read videos (uploads)", video_io), ("Database", database)]:
            check(name, func)
        click.echo("\nAll checks passed." if not failures else f"\n{failures} check(s) failed - see above.")

    @app.cli.command("create-user")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    @click.option("--role", type=click.Choice(["admin", "analyst"]), default="analyst")
    @click.password_option()
    def create_user(email, name, role, password):
        if User.query.filter_by(email=email.lower()).first():
            raise click.ClickException("A user with this email already exists.")
        user = User(email=email.lower(), name=name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} {email}")

    @app.cli.command("seed-demo")
    @click.option("--password", default="Demo1234!", help="Password for the demo accounts")
    def seed_demo(password):
        """Create demo accounts and ~25 historical analyses so the dashboard is not empty."""
        users = []
        for email, name, role in [("admin@globaltech.com", "Security Admin", "admin"),
                                  ("analyst@globaltech.com", "SOC Analyst", "analyst")]:
            user = User.query.filter_by(email=email).first() or User(email=email, name=name, role=role)
            user.set_password(password)
            db.session.add(user)
            users.append(user)
        db.session.commit()
        if Analysis.query.count():
            click.echo("Demo users updated (sample data already exists).")
            return
        rng = random.Random(7)
        names = ["Board meeting Q3", "Finance approval call", "Vendor onboarding", "CEO all-hands",
                 "Wire transfer review", "Partner sync", "IT access request"]
        for i in range(25):
            when = utcnow() - timedelta(days=rng.uniform(0, 14), hours=rng.uniform(0, 8))
            meeting = Meeting(user=rng.choice(users), meeting_name=rng.choice(names),
                              platform=rng.choice(["Zoom", "Teams", "Upload"]), source_type="upload",
                              start_time=when, end_time=when + timedelta(seconds=40), status="completed",
                              first_score_ms=rng.uniform(900, 2500))
            risk = rng.choice([rng.uniform(3, 28)] * 4 + [rng.uniform(35, 65), rng.uniform(72, 96)])
            result = "Rejected" if risk >= 70 else "Suspicious" if risk >= 31 else "Approved"
            a = Analysis(meeting=meeting, timestamp=when, frames_analyzed=20, faces_detected=20,
                         deepfake_score=round(risk, 1), quality_score=round(rng.uniform(55, 90), 1),
                         trust_score=round((100 - risk) * 0.95, 1), result=result,
                         reasons="Sample data", processing_time_ms=round(rng.uniform(1200, 3800), 1),
                         capture_ms=120, face_ms=700, inference_ms=450, model_name="sample-data")
            db.session.add(a)
            if result != "Approved":
                db.session.add(Alert(analysis=a, timestamp=when,
                                     severity="High" if result == "Rejected" else "Warning",
                                     message=f"Sample alert - risk {risk:.0f}% in {meeting.meeting_name}",
                                     status=rng.choice(["Open", "Resolved", "Acknowledged"])))
        db.session.commit()
        click.echo(f"Demo data created. Log in with admin@globaltech.com / {password}")
