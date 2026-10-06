from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402
from config import TestConfig  # noqa: E402


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        for email, role in (("admin@test.com", "admin"), ("analyst@test.com", "analyst")):
            user = User(email=email, name=role.title(), role=role)
            user.set_password("Correct-Pass1")
            db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email="admin@test.com", password="Correct-Pass1"):
    return client.post("/login", data={"email": email, "password": password})
