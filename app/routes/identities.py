from __future__ import annotations
"""Reference identities (admin only): the known faces used for identity verification.
Reference photos are biometric data, so they are stored outside /static and served
only to logged-in admins."""
import uuid

import cv2
import numpy as np
from flask import Blueprint, current_app, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..decorators import admin_required
from ..extensions import db
from ..forms import IdentityForm
from ..models import ReferenceIdentity
from ..services.cv_io import imwrite
from ..services.pipeline import get_models
from ..services.records import audit

bp = Blueprint("identities", __name__, url_prefix="/identities")


@bp.route("/", methods=["GET", "POST"])
@login_required
@admin_required
def index():
    form = IdentityForm()
    if form.validate_on_submit():
        try:
            if add_identity(form):
                return redirect(url_for("identities.index"))
        except Exception as exc:  # show the reason instead of a blank 500 page
            db.session.rollback()
            current_app.logger.exception("Adding a reference identity failed")
            flash(f"The photo could not be processed: {exc}", "error")
    items = ReferenceIdentity.query.order_by(ReferenceIdentity.full_name).all()
    return render_template("identities.html", form=form, identities=items)


def add_identity(form):
    """Validate the photo, find exactly one face, store the photo and its embedding.
    Returns True when the identity was saved."""
    ext = secure_filename(form.photo.data.filename).rsplit(".", 1)[-1].lower()
    if ext == "jpeg":
        ext = "jpg"
    raw = form.photo.data.read()
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"] or image is None:
        flash("The file is not a valid JPG or PNG image.", "error")
        return False
    # Very large phone photos are scaled down: faster and no loss for face matching
    longest = max(image.shape[:2])
    if longest > 1600:
        scale = 1600 / longest
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    faces, _ = get_models()
    found = faces.detect(image)
    if not found:
        flash("No face was found in the photo. Use a clear, front-facing photo.", "error")
        return False
    if len(found) > 1 and found[1][0] > 0.9:
        flash("More than one face was found. Use a photo of one person only.", "error")
        return False
    filename = f"{uuid.uuid4().hex}.{ext}"
    imwrite(current_app.config["REFERENCE_DIR"] / filename, image)
    identity = ReferenceIdentity(full_name=form.full_name.data.strip(), job_title=form.job_title.data.strip(),
                                 image_filename=filename, embedding=faces.embed(image, found[0][1]).tobytes(),
                                 created_by=current_user.user_id)
    db.session.add(identity)
    audit("identity_added", f"name={identity.full_name}")
    db.session.commit()
    flash(f"{identity.full_name} was added as a reference identity.", "info")
    return True


@bp.route("/<int:identity_id>/photo")
@login_required
@admin_required
def photo(identity_id):
    identity = db.get_or_404(ReferenceIdentity, identity_id)
    return send_from_directory(current_app.config["REFERENCE_DIR"], identity.image_filename)


@bp.route("/<int:identity_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(identity_id):
    identity = db.get_or_404(ReferenceIdentity, identity_id)
    (current_app.config["REFERENCE_DIR"] / identity.image_filename).unlink(missing_ok=True)
    for meeting in identity_meetings(identity):
        meeting.claimed_identity_id = None
    db.session.delete(identity)
    audit("identity_deleted", f"name={identity.full_name}")
    db.session.commit()
    flash(f"{identity.full_name} and the reference photo were deleted.", "info")
    return redirect(url_for("identities.index"))


def identity_meetings(identity):
    from ..models import Meeting
    return Meeting.query.filter_by(claimed_identity_id=identity.identity_id).all()
