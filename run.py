from __future__ import annotations
"""Entry point.

Development (your PC):   python run.py            -> http://127.0.0.1:5000
Server (Linux/Windows):  waitress-serve --host 0.0.0.0 --port 8000 --threads 8 run:app
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True is only for local development. NEVER enable it on a shared
    # server: the debug page lets anyone who can reach it run code.
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG") == "1")
