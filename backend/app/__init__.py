"""
CycloSense — Flask Application Factory
"""

import os
import logging
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def create_app():
    """
    Create and configure the Flask application.
    - Loads all ML models once at startup.
    - Registers all Blueprints.
    - Enables CORS for frontend access.
    - Serves frontend static pages for complete full-stack deployment.
    """
    app = Flask(__name__)

    # ── Logging ───────────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger(__name__)

    # ── CORS (allow requests from any origin) ─────────────────────────────────
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── Load ML models asynchronously in background thread ──────────────────
    from app.services.model_loader import load_models_in_background
    load_models_in_background()
    logger.info("CycloSense background model loader initiated.")

    # ── Register Blueprints ───────────────────────────────────────────────────
    from app.routes.predict import predict_bp
    from app.routes.map import map_bp
    from app.routes.ai import ai_bp

    app.register_blueprint(predict_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(ai_bp)

    # ── Frontend Static Serving (Full-Stack Unified Hosting) ──────────────────
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

    @app.get("/")
    def serve_landing():
        landing_path = os.path.join(frontend_dir, "pages", "landing.html")
        if os.path.exists(landing_path):
            return send_from_directory(os.path.join(frontend_dir, "pages"), "landing.html")
        return jsonify({"service": "CycloSense API", "status": "active"}), 200

    @app.get("/dashboard")
    @app.get("/index.html")
    @app.get("/pages/index.html")
    def serve_dashboard():
        return send_from_directory(os.path.join(frontend_dir, "pages"), "index.html")

    @app.get("/landing.html")
    @app.get("/pages/landing.html")
    def serve_landing_alias():
        return send_from_directory(os.path.join(frontend_dir, "pages"), "landing.html")

    @app.get("/css/<path:filename>")
    def serve_css(filename):
        return send_from_directory(os.path.join(frontend_dir, "css"), filename)

    @app.get("/js/<path:filename>")
    def serve_js(filename):
        return send_from_directory(os.path.join(frontend_dir, "js"), filename)

    @app.get("/images/<path:filename>")
    def serve_images(filename):
        return send_from_directory(os.path.join(frontend_dir, "images"), filename)

    @app.get("/frontend/<path:filename>")
    def serve_frontend_generic(filename):
        return send_from_directory(frontend_dir, filename)

    # ── Cron Job / Uptime Keepalive Routes ────────────────────────────────────
    @app.get("/health")
    @app.get("/healthz")
    @app.get("/ping")
    @app.get("/api/health")
    @app.get("/api/cron/keepalive")
    def cron_health():
        """
        Ultra-lightweight keepalive endpoint for cron jobs (e.g. cron-job.org, UptimeRobot).
        Prevents Render free tier instances from sleeping without executing expensive operations.
        """
        import time
        from app.services.model_loader import are_models_loaded
        return jsonify({
            "status": "healthy",
            "service": "CycloSense",
            "uptime_check": "ok",
            "timestamp": time.time(),
            "models_loaded": are_models_loaded()
        }), 200

    # ── Root API Directory & Health ───────────────────────────────────────────
    @app.get("/api")
    def api_root():
        return jsonify({
            "service": "CycloSense API",
            "version": "1.0.0",
            "endpoints": {
                "health":      "GET  /api/predict/health",
                "test_models": "GET  /api/predict/test-models",
                "detect":      "POST /api/predict/detect",
                "classify":    "POST /api/predict/classify",
                "forecast":    "POST /api/predict/forecast",
                "full":        "POST /api/predict/full",
                "track_geo":   "POST /api/map/track",
                "impact":      "POST /api/map/impact",
                "basins":      "GET  /api/map/basins",
                "shelters":    "POST /api/map/nearest-shelters",
                "ai_status":   "GET  /api/ai/status",
                "ask_ai":      "POST /api/ai/ask",
                "scan_room":   "POST /api/ai/scan-room"
            }
        }), 200

    logger.info("CycloSense Flask app created successfully.")
    return app
