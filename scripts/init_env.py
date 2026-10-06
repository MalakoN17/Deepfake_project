from __future__ import annotations
"""Create .env from .env.example with a new random SECRET_KEY (run once).
Usage:  python scripts/init_env.py"""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
env, example = root / ".env", root / ".env.example"
if env.exists():
    print(".env already exists - nothing changed.")
else:
    env.write_text(example.read_text().replace("change-me-to-a-long-random-string", secrets.token_hex(32)))
    print("Created .env with a new SECRET_KEY.")
