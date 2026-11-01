"""
CycloSense — WSGI Production Server Entry Point
Compatible with Gunicorn, Render, Heroku, AWS, Docker.
"""
import os
import sys

# Ensure backend directory is on Python path
root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)

