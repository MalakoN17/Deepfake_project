from __future__ import annotations
"""Entry point.

Development (your PC):   python run.py            -> http://<host>:5005 (HOST/PORT in .env)
Server (Linux/Windows):  waitress-serve --host 0.0.0.0 --port 8000 --threads 8 run:app
"""
import os

from app import create_app
from config import server_address

app = create_app()

if __name__ == "__main__":
    # debug=True is only for local development. NEVER enable it on a shared
    # server: the debug page lets anyone who can reach it run code.
    debug = os.getenv("FLASK_DEBUG") == "1"
    host, port = server_address(debug)
    app.run(host=host, port=port, debug=debug)
