from __future__ import annotations
"""Flask extensions are created here (without an app) to avoid circular imports."""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Sign in to continue."
login_manager.login_message_category = "info"
