import os
from datetime import timedelta

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
    app.config.update(
        JWT_TOKEN_LOCATION=["headers", "cookies"],
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=8),
        JWT_ACCESS_COOKIE_PATH="/api/",
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_COOKIE_SAMESITE="Lax",
        JWT_COOKIE_SECURE=os.getenv("JWT_COOKIE_SECURE", "false").lower() in ("true", "1", "yes"),
    )

    initialize_database()

    # Máximo 10 MB por archivo.
    app.config["MAX_CONTENT_LENGTH"] = (
        10 * 1024 * 1024
    )

    # ========================================================
    # EXTENSIONS
    # ========================================================

    jwt = JWTManager(app)

    @jwt.unauthorized_loader
    def missing_session(reason):
        if "CSRF" in reason:
            return jsonify({"error": "No se pudo verificar tu sesión. Recarga la página e intenta de nuevo"}), 401
        return jsonify({"error": "Inicia sesión para continuar"}), 401

    @jwt.expired_token_loader
    def expired_session(_header, _payload):
        return jsonify({"error": "Tu sesión expiró. Inicia sesión de nuevo"}), 401

    @jwt.invalid_token_loader
    def invalid_session(_reason):
        return jsonify({"error": "La sesión no es válida. Inicia sesión de nuevo"}), 401

    CORS(
        app,
        supports_credentials=True,
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
        response = jsonify(OPENAPI_SPEC)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/docs")
    def swagger_ui():
        response = (
            "<!doctype html><html><head><title>Anime API Swagger</title>"
            "<link rel='stylesheet' href='https://unpkg.com/swagger-ui-dist/swagger-ui.css'>"
            "</head><body><div id='swagger-ui'></div>"
            "<script src='https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js'></script>"
            "<script>SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui'});</script>"
            "</body></html>"
        )
        return response, 200, {"Cache-Control": "no-store"}

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
        "/api/recommendations": {"get": {"summary": "Global recommendations", "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}], "responses": {"200": {"description": "Recommendations aggregated from all user preferences"}, "503": {"description": "Insufficient training data"}}}},
        "/api/recommendations/status": {"get": {"responses": {"200": {"description": "Model status"}}}},
        "/api/recommendations/train": {"post": {"responses": {"200": {"description": "Model trained"}, "503": {"description": "Training unavailable"}}}},
        "/api/recommendations/me": {"get": {"security": [{"bearerAuth": []}], "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 50}}], "responses": {"200": {"description": "Recommendations"}, "503": {"description": "Model unavailable"}}}},
        "/api/recommendations/{user_id}": {"get": {"parameters": [{"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": {"200": {"description": "Recommendations"}}}},
        "/api/media/{anime_id}": {"get": {"parameters": [{"name": "anime_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "responses": {"200": {"description": "Media list"}}}, "post": {"security": [{"bearerAuth": []}], "parameters": [{"name": "anime_id", "in": "path", "required": True, "schema": {"type": "integer"}}], "requestBody": {"content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}}, "responses": {"201": {"description": "Stored"}, "400": {"description": "Invalid file"}}}},
        "/api/media/{anime_id}/image": {"get": {"summary": "Get or cache anime image", "parameters": [{"name": "anime_id", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}}], "responses": {"200": {"description": "Image from MongoDB/GridFS", "content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}, "404": {"description": "Image unavailable"}, "502": {"description": "External image unavailable"}, "503": {"description": "MongoDB storage unavailable"}}}},
        "/api/media/file/{file_id}": {"get": {"parameters": [{"name": "file_id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "File stream"}, "404": {"description": "Not found"}}}, "delete": {"security": [{"bearerAuth": []}], "parameters": [{"name": "file_id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Deleted"}, "404": {"description": "Not found"}}}}
    }
}


def _complete_openapi_spec():
    """Keep the hand-written contract aligned with the registered routes."""
    OPENAPI_SPEC["info"].update({
        "version": "1.2.0",
        "description": (
            "API REST para catálogo de anime, recomendaciones ALS, "
            "autenticación JWT y archivos MongoDB/GridFS."
        )
    })
    OPENAPI_SPEC["components"]["securitySchemes"].update({
        "cookieAuth": {
            "type": "apiKey", "in": "cookie", "name": "access_token_cookie",
            "description": "Cookie HttpOnly de sesión, emitida al ingresar o registrarse; vence en 8 horas."
        },
        "csrfToken": {
            "type": "apiKey", "in": "header", "name": "X-CSRF-TOKEN",
            "description": "Para modificar datos con cookies, copiar el valor de la cookie csrf_access_token."
        }
    })
    OPENAPI_SPEC["tags"] = [
        {"name": "System", "description": "Estado del servicio"},
        {"name": "Auth", "description": "Registro y autenticación JWT"},
        {"name": "Anime", "description": "Catálogo consultado mediante Jikan"},
        {"name": "Recommendations", "description": "Modelo ALS sobre Reviews de SQL Server"},
        {"name": "Media", "description": "Archivos almacenados en MongoDB/GridFS"}
    ]
    schemas = OPENAPI_SPEC["components"]["schemas"]
    schemas.update({
        "RegisterRequest": {
            "type": "object", "required": ["nombre", "email", "password"],
            "properties": {
                "nombre": {"type": "string", "minLength": 1, "maxLength": 100},
                "email": {"type": "string", "format": "email", "maxLength": 255},
                "password": {"type": "string", "format": "password", "minLength": 8, "maxLength": 128}
            }
        },
        "LoginRequest": {
            "type": "object", "required": ["email", "password"],
            "properties": {
                "email": {"type": "string", "format": "email", "maxLength": 255},
                "password": {"type": "string", "format": "password", "minLength": 1, "maxLength": 1024}
            }
        },
        "AuthUser": {
            "type": "object", "required": ["id", "nombre", "email"],
            "properties": {
                "id": {"type": "integer"}, "nombre": {"type": "string"},
                "email": {"type": "string", "format": "email"}
            }
        },
        "SessionResponse": {
            "type": "object", "required": ["user", "accessToken", "expiresAt"],
            "properties": {
                "message": {"type": "string"}, "accessToken": {"type": "string"},
                "expiresAt": {"type": "integer", "description": "Expiración de la sesión en segundos Unix"},
                "user": {"$ref": "#/components/schemas/AuthUser"}
            }
        },
        "ErrorResponse": {
            "type": "object", "required": ["error"],
            "properties": {"error": {"type": "string"}}
        },
        "HealthResponse": {
            "type": "object", "required": ["status"],
            "properties": {"status": {"type": "string", "example": "ok"}}
        },
        "Recommendation": {
            "type": "object",
            "properties": {
                "movieId": {"type": "integer", "description": "anime_id de Reviews"},
                "title": {"type": "string"},
                "predictedRating": {"type": "number", "format": "float"}
            }
        },
        "RecommendationsResponse": {
            "type": "object",
            "properties": {
                "userId": {"type": "integer"},
                "requestedLimit": {"type": "integer"},
                "returnedCount": {"type": "integer"},
                "message": {"type": "string"},
                "recommendations": {"type": "array", "items": {"$ref": "#/components/schemas/Recommendation"}}
            }
        },
        "MediaListResponse": {
            "type": "object",
            "properties": {
                "animeId": {"type": "integer"},
                "files": {"type": "array", "items": {"$ref": "#/components/schemas/MediaFile"}}
            }
        },
        "MediaFile": {
            "type": "object",
            "properties": {
                "id": {"type": "string"}, "animeId": {"type": "integer"},
                "fileId": {"type": "string"}, "filename": {"type": "string"},
                "contentType": {"type": "string"}, "url": {"type": "string"}
            }
        }
    })

    paths = OPENAPI_SPEC["paths"]
    paths["/api/auth/logout"] = {"post": {
        "summary": "Cerrar sesión", "security": [],
        "description": "Borra las cookies incluso cuando la sesión ya expiró.",
        "responses": {"200": {"description": "Sesión cerrada"}}
    }}
    tags_by_prefix = {
        "/api/health": "System", "/api/auth/": "Auth", "/api/anime/": "Anime",
        "/api/recommendations/": "Recommendations", "/api/media/": "Media"
    }
    for path, item in paths.items():
        tag = next((value for prefix, value in tags_by_prefix.items() if path.startswith(prefix)), "System")
        for method, operation in item.items():
            operation["tags"] = [tag]
            operation.setdefault("responses", {})["500"] = {"description": "Error interno"}
            if operation.get("security"):
                cookie_security = {"cookieAuth": []}
                if method in {"post", "put", "patch", "delete"}:
                    cookie_security["csrfToken"] = []
                operation["security"] = [{"bearerAuth": []}, cookie_security]
                operation["responses"]["401"] = {"description": "Sesión ausente, inválida o expirada"}

    paths["/api/health"]["get"].update({
        "operationId": "healthCheck",
        "responses": {"200": {"description": "Servicio disponible", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HealthResponse"}}}}}
    })
    paths["/api/auth/register"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/RegisterRequest"}
    paths["/api/auth/login"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/LoginRequest"}
    for path, status in (("/api/auth/register", "201"), ("/api/auth/login", "200")):
        paths[path]["post"]["responses"].update({
            status: {"description": "Sesión iniciada y cookies emitidas", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SessionResponse"}}}},
            "400": {"description": "Datos de formulario inválidos"},
            "503": {"description": "Base de datos no disponible"}
        })
    paths["/api/auth/register"]["post"]["responses"]["409"] = {"description": "Email ya registrado"}
    paths["/api/auth/register"]["post"]["responses"]["201"] = {
        "description": "Cuenta creada; requiere iniciar sesión por separado",
        "content": {"application/json": {"schema": {
            "type": "object", "required": ["message", "user"],
            "properties": {
                "message": {"type": "string"},
                "user": {"$ref": "#/components/schemas/AuthUser"}
            }
        }}}
    }
    paths["/api/auth/me"]["get"]["responses"].update({
        "200": {"description": "Usuario actual y expiración", "content": {"application/json": {"schema": {
            "allOf": [{"$ref": "#/components/schemas/AuthUser"}, {"type": "object", "properties": {
                "fechaCreacion": {"type": "string", "format": "date-time", "nullable": True},
                "expiresAt": {"type": "integer"}
            }}]
        }}}},
        "503": {"description": "Base de datos no disponible"}
    })
    for path in ("/api/anime/top", "/api/anime/season/now"):
        paths[path]["get"]["parameters"] = [
            {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
            {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 25, "default": 12}}
        ]
    paths["/api/anime/genres"]["get"]["responses"]["502"] = {"description": "Jikan no disponible"}
    paths["/api/recommendations/status"]["get"]["responses"]["200"] = {"description": "Estado del modelo", "content": {"application/json": {"schema": {"type": "object", "properties": {"ready": {"type": "boolean"}, "source": {"type": "string", "nullable": True, "enum": ["trained", "trained_and_saved", "persisted"]}, "modelPath": {"type": "string"}, "availableItems": {"type": "integer"}}}}}}
    paths["/api/recommendations/{user_id}"]["get"]["parameters"].append({"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}})
    paths["/api/recommendations/{user_id}"]["get"]["responses"].update({"200": {"description": "Recomendaciones generadas", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RecommendationsResponse"}}}}, "503": {"description": "Modelo no entrenado o no disponible"}})
    paths["/api/recommendations/me"]["get"]["responses"].update({"401": {"description": "JWT ausente o inválido"}})
    paths["/api/media/{anime_id}"]["get"]["responses"]["200"] = {"description": "Archivos del anime", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MediaListResponse"}}}}
    paths["/api/media/{anime_id}"]["post"]["responses"].update({"401": {"description": "JWT ausente o inválido"}, "500": {"description": "No se pudo guardar el archivo"}})
    paths["/api/media/file/{file_id}"]["delete"]["responses"].update({"400": {"description": "ID inválido"}, "401": {"description": "JWT ausente o inválido"}})


_complete_openapi_spec()


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
