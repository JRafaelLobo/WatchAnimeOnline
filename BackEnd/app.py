import os

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from routes.anime import anime_bp
from routes.auth import auth_bp
from routes.media import media_bp
from routes.recommendations import recommendations_bp


def create_app():
    app = Flask(__name__)

    # ========================================================
    # CONFIG
    # ========================================================

    jwt_secret = os.getenv(
        "JWT_SECRET"
    )

    if not jwt_secret:
        raise RuntimeError(
            "JWT_SECRET no está configurado"
        )

    app.config["JWT_SECRET_KEY"] = jwt_secret

    # Máximo 10 MB por archivo.
    app.config["MAX_CONTENT_LENGTH"] = (
        10 * 1024 * 1024
    )

    # ========================================================
    # EXTENSIONS
    # ========================================================

    JWTManager(app)

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": [
                    "http://localhost:3000",
                    "http://localhost:5173"
                ]
            }
        }
    )

    # ========================================================
    # ROUTES
    # ========================================================

    app.register_blueprint(
        auth_bp,
        url_prefix="/api/auth"
    )

    app.register_blueprint(
        anime_bp,
        url_prefix="/api/anime"
    )

    app.register_blueprint(
        recommendations_bp,
        url_prefix="/api/recommendations"
    )

    app.register_blueprint(
        media_bp,
        url_prefix="/api/media"
    )

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "ok"
        }), 200