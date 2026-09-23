import os

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config.sqlserver import initialize_database
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

    initialize_database()

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

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "ok"
        }), 200

    app.add_url_rule("/health", view_func=health_check)

    @app.get("/openapi.json")
    def openapi():
        return jsonify(OPENAPI_SPEC)

    @app.get("/docs")
    def swagger_ui():
        return (
            "<!doctype html><html><head><title>Anime API Swagger</title>"
            "<link rel='stylesheet' href='https://unpkg.com/swagger-ui-dist/swagger-ui.css'>"
            "</head><body><div id='swagger-ui'></div>"
            "<script src='https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js'></script>"
            "<script>SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui'});</script>"
            "</body></html>"
        ), 200

    return app


OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Anime Recommendation API", "version": "1.0.0"},
    "servers": [{"url": "/"}],
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        },
        "schemas": {
            "Error": {"type": "object", "properties": {"error": {"type": "string"}}},
            "Credentials": {"type": "object", "required": ["email", "password"], "properties": {
                "nombre": {"type": "string"}, "email": {"type": "string", "format": "email"},
                "password": {"type": "string", "format": "password", "minLength": 8}
            }},
            "AnimeResponse": {"type": "object", "additionalProperties": True}
        }
    },
    "paths": {
        "/api/health": {"get": {"summary": "Healthcheck", "responses": {"200": {"description": "OK"}}}},
        "/api/auth/register": {"post": {"summary": "Register", "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Credentials"}}}}, "responses": {"201": {"description": "Created"}, "400": {"description": "Invalid input"}, "409": {"description": "Duplicate email"}}}},
        "/api/auth/login": {"post": {"summary": "Login", "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Credentials"}}}}, "responses": {"200": {"description": "JWT issued"}, "401": {"description": "Invalid credentials"}}}},
        "/api/auth/me": {"get": {"security": [{"bearerAuth": []}], "responses": {"200": {"description": "Current user"}, "401": {"description": "Unauthorized"}}}},
        "/api/anime/search": {"get": {"parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}}, {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 25}}], "responses": {"200": {"description": "Jikan results"}, "400": {"description": "Missing query"}, "502": {"description": "External API error"}}}},
        "/api/anime/top": {"get": {"responses": {"200": {"description": "Top anime"}, "502": {"description": "External API error"}}}},
        "/api/anime/season/now": {"get": {"responses": {"200": {"description": "Current season"}, "502": {"description": "External API error"}}}},
        "/api/anime/genres": {"get": {"responses": {"200": {"description": "Genres"}, "502": {"description": "External API error"}}}},
        "/api/anime/{anime_id}": {"get": {"parameters": [{"name": "anime_id", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}}], "responses": {"200": {"description": "Anime detail"}, "502": {"description": "External API error"}}}},
        "/api/recommendations/status": {"get": {"responses": {"200": {"description": "Model status"}}}},
        "/api/recommendations/train": {"post": {"responses": {"200": {"description": "Model trained"}, "503": {"description": "Training unavailable"}}}},
        "/api/recommendations/me": {"get": {"security": [{"bearerAuth": []}], "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 50}}], "responses": {"200": {"description": "Recommendations"}, "503": {"description": "Model unavailable"}}}},
        "/api/recommendations/{user_id}": {"get": {"parameters": [{"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": {"200": {"description": "Recommendations"}}}},
        "/api/media/{anime_id}": {"get": {"parameters": [{"name": "anime_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": {"200": {"description": "Media list"}}}, "post": {"security": [{"bearerAuth": []}], "parameters": [{"name": "anime_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "requestBody": {"content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}}, "responses": {"201": {"description": "Stored"}, "400": {"description": "Invalid file"}}}},
        "/api/media/file/{file_id}": {"get": {"parameters": [{"name": "file_id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "File stream"}, "404": {"description": "Not found"}}}, "delete": {"security": [{"bearerAuth": []}], "parameters": [{"name": "file_id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Deleted"}, "404": {"description": "Not found"}}}}
    }
}


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)