"""Authentication contract tests; SQL is replaced with a transactional fake.

Run from BackEnd: python -m pytest tests/test_auth.py
No SQL Server, MongoDB, Spark or external HTTP service is required.
"""
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pyodbc
import pytest
from flask_jwt_extended import create_access_token, decode_token
from werkzeug.security import check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as application
from routes import auth, media
from services import recommender


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.closed = False
        self.result = None

    def execute(self, statement, *parameters):
        self.connection.database.statements.append((statement, parameters))
        if self.connection.database.query_error:
            raise self.connection.database.query_error
        if "INSERT INTO auth_users" in statement:
            if self.connection.database.insert_error:
                raise self.connection.database.insert_error
            name, email, password_hash = parameters
            user_id = len(self.connection.database.users) + 1
            self.connection.pending = SimpleNamespace(
                id=user_id, nombre=name, email=email, password_hash=password_hash,
                fecha_creacion=datetime(2026, 9, 23, 12, 0),
            )
            self.result = (user_id,)
        elif "WHERE email = ?" in statement:
            self.result = next((user for user in self.connection.database.users.values()
                                if user.email == parameters[0]), None)
        elif "WHERE id = ?" in statement:
            self.result = self.connection.database.users.get(parameters[0])
        else:
            raise AssertionError(f"Unexpected SQL: {statement}")
        return self

    def fetchone(self):
        return self.result

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, database):
        self.database = database
        self.closed = False
        self.pending = None
        self.committed = False
        self.rolled_back = False
        self.active_cursor = FakeCursor(self)

    def cursor(self):
        if self.database.cursor_error:
            raise self.database.cursor_error
        return self.active_cursor

    def commit(self):
        if self.database.commit_error:
            raise self.database.commit_error
        self.database.users[self.pending.id] = self.pending
        self.committed = True

    def rollback(self):
        self.pending = None
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeDatabase:
    def __init__(self):
        self.users = {}
        self.connections = []
        self.statements = []
        self.connect_error = self.cursor_error = None
        self.query_error = self.insert_error = self.commit_error = None

    def connect(self):
        if self.connect_error:
            raise self.connect_error
        connection = FakeConnection(self)
        self.connections.append(connection)
        return connection


@pytest.fixture
def database(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(auth, "get_connection", database.connect)
    return database


@pytest.fixture
def app(monkeypatch, database):
    monkeypatch.setenv("JWT_SECRET", "test-secret-only-for-auth-tests-32-characters")
    monkeypatch.delenv("JWT_COOKIE_SECURE", raising=False)
    monkeypatch.setattr(application, "initialize_database", lambda: None)
    app = application.create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, **overrides):
    return client.post("/api/auth/register", json={
        "nombre": "  Akira  ", "email": "  AKIRA@EXAMPLE.COM ", "password": "my-password-123",
        **overrides,
    })


def test_registration_persists_normalized_credentials_and_starts_session(client, app, database):
    response = register(client)
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["user"] == {"id": 1, "nombre": "Akira", "email": "akira@example.com"}
    user = database.users[1]
    assert user.password_hash != "my-password-123"
    assert check_password_hash(user.password_hash, "my-password-123")
    assert "password_hash" not in payload["user"]
    assert database.connections[0].committed
    assert database.connections[0].closed and database.connections[0].active_cursor.closed
    assert all("auth_users" in statement for statement, _ in database.statements)
    with app.app_context():
        token = decode_token(payload["accessToken"])
    assert token["sub"] == "1"
    assert payload["expiresAt"] == token["exp"]
    assert token["exp"] - token["iat"] == 8 * 60 * 60
    access = client.get_cookie("access_token_cookie", path="/api/")
    assert access.http_only and access.same_site == "Lax" and not access.secure
    csrf = client.get_cookie("csrf_access_token")
    assert csrf and not csrf.http_only
    assert response.headers["Cache-Control"] == "no-store"
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["nombre"] == "Akira"
    assert me.get_json()["expiresAt"] == payload["expiresAt"]
    assert database.connections[-1].closed and database.connections[-1].active_cursor.closed


def test_registered_user_can_login_in_a_fresh_browser(client, app, database):
    register(client)
    browser = app.test_client()
    response = browser.post("/api/auth/login", json={
        "email": " AKIRA@example.com ", "password": "my-password-123",
    })
    assert response.status_code == 200
    assert response.get_json()["user"]["id"] == 1
    assert browser.get_cookie("access_token_cookie", path="/api/")
    assert browser.get("/api/auth/me").status_code == 200
    assert len(database.users) == 1


@pytest.mark.parametrize("password,email", [
    ("wrong-password", "akira@example.com"), ("my-password-123", "nobody@example.com"),
])
def test_login_rejects_wrong_credentials_without_issuing_cookies(client, password, email):
    register(client)
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.get_json()["error"] == "Correo o contraseña incorrectos"
    assert not response.headers.getlist("Set-Cookie")


@pytest.mark.parametrize("changes", [
    {"nombre": " "}, {"nombre": "a" * 101}, {"nombre": 123},
    {"email": "wrong"}, {"email": "a@b"}, {"email": "a b@example.com"},
    {"email": "a" * 250 + "@mail.com"}, {"email": None},
    {"password": "short"}, {"password": "a" * 129}, {"password": []},
])
def test_registration_rejects_invalid_fields_before_database_access(client, database, changes):
    response = register(client, **changes)
    assert response.status_code == 400
    assert response.get_json()["error"]
    assert database.connections == []


@pytest.mark.parametrize("body", ["[]", "null", "false", '"text"', "{invalid json"])
@pytest.mark.parametrize("path", ["/api/auth/register", "/api/auth/login"])
def test_invalid_json_shapes_do_not_crash(client, database, body, path):
    response = client.post(path, data=body, content_type="application/json")
    assert response.status_code == 400
    assert database.connections == []


def test_duplicate_email_is_reported_without_modifying_existing_user(client, database):
    register(client)
    response = register(client, nombre="Another name")
    assert response.status_code == 409
    assert len(database.users) == 1 and database.users[1].nombre == "Akira"
    assert database.connections[-1].closed and database.connections[-1].active_cursor.closed


def test_concurrent_duplicate_registration_rolls_back(client, database):
    database.insert_error = pyodbc.IntegrityError("23000", "Duplicate UNIQUE KEY (2627)")
    response = register(client)
    assert response.status_code == 409
    assert database.connections[-1].rolled_back
    assert database.connections[-1].closed and database.connections[-1].active_cursor.closed
    assert not database.users


@pytest.mark.parametrize("failure", ["connect_error", "cursor_error", "query_error", "commit_error"])
def test_registration_database_failures_are_json_and_cleanup(client, database, failure):
    setattr(database, failure, pyodbc.OperationalError("SQL unavailable"))
    response = register(client)
    assert response.status_code == 503
    assert response.get_json()["error"]
    assert not database.users
    for connection in database.connections:
        assert connection.closed and connection.rolled_back
        if failure != "cursor_error":
            assert connection.active_cursor.closed


@pytest.mark.parametrize("endpoint", ["login", "me"])
def test_login_and_session_database_failures_return_json(client, database, endpoint):
    register(client)
    database.connect_error = pyodbc.OperationalError("SQL unavailable")
    if endpoint == "login":
        response = client.post("/api/auth/login", json={"email": "akira@example.com", "password": "password"})
    else:
        response = client.get("/api/auth/me")
    assert response.status_code == 503
    assert response.get_json()["error"]


def test_deleted_user_cannot_restore_a_session(client, database):
    register(client)
    database.users.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert client.get_cookie("access_token_cookie", path="/api/") is None
    assert database.connections[-1].closed and database.connections[-1].active_cursor.closed


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/anime/top"), ("GET", "/api/anime/search?q=naruto"),
    ("GET", "/api/anime/season/now"), ("GET", "/api/anime/genres"), ("GET", "/api/anime/1"),
    ("GET", "/api/recommendations"), ("GET", "/api/recommendations/status"),
    ("GET", "/api/recommendations/1"), ("GET", "/api/recommendations/me"),
    ("POST", "/api/recommendations/train"), ("GET", "/api/media/1"),
    ("POST", "/api/media/1"), ("GET", "/api/media/1/image"),
    ("GET", "/api/media/file/123"), ("DELETE", "/api/media/file/123"), ("GET", "/api/auth/me"),
])
def test_application_endpoints_require_login(client, method, path):
    response = client.open(path, method=method)
    assert response.status_code == 401
    assert response.get_json()["error"] == "Inicia sesión para continuar"


def test_cookies_allow_protected_get_and_csrf_protects_mutations(client, monkeypatch):
    register(client)
    monkeypatch.setattr(recommender, "model_status", lambda: {"ready": True})
    train = Mock(return_value={"ready": True})
    monkeypatch.setattr(recommender, "train_model", train)
    response = client.get("/api/recommendations/status")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert client.post("/api/recommendations/train").status_code == 401
    train.assert_not_called()
    csrf = client.get_cookie("csrf_access_token").value
    response = client.post("/api/recommendations/train", headers={"X-CSRF-TOKEN": csrf})
    assert response.status_code == 200
    train.assert_called_once_with()


def test_cookie_session_loads_media_images_without_bearer_header(client, monkeypatch):
    register(client)
    monkeypatch.setattr(media, "db", SimpleNamespace(anime_media=SimpleNamespace(
        find_one=Mock(return_value={"fileId": "cached-file"}),
    )))
    image = BytesIO(b"cached-image-bytes")
    image.content_type = "image/png"
    monkeypatch.setattr(media, "fs", SimpleNamespace(get=Mock(return_value=image)))
    response = client.get("/api/media/1/image")
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.data == b"cached-image-bytes"
    assert response.headers["Cache-Control"] == "private, no-store"


def test_bearer_tokens_remain_compatible(app, client, monkeypatch):
    token = register(client).get_json()["accessToken"]
    monkeypatch.setattr(recommender, "model_status", lambda: {"ready": True})
    browser = app.test_client()
    response = browser.get("/api/recommendations/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_recommendations_remain_global_for_different_accounts(client, app, monkeypatch):
    expected = [{"movieId": 1, "title": "Anime", "predictedRating": 8.5}]
    generate = Mock(return_value=expected)
    monkeypatch.setattr(recommender, "generate_global_recommendations", generate)
    register(client)
    first = client.get("/api/recommendations?limit=1").get_json()
    second_browser = app.test_client()
    register(second_browser, email="second@example.com")
    second = second_browser.get("/api/recommendations?limit=1").get_json()
    assert first == second
    assert first["mode"] == "global" and first["recommendations"] == expected
    assert all(call.args == (1,) for call in generate.call_args_list)


def test_logout_clears_session_and_rejects_subsequent_protected_requests(client):
    register(client)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get_cookie("access_token_cookie", path="/api/") is None
    assert client.get_cookie("csrf_access_token") is None
    assert client.get("/api/recommendations/status").status_code == 401
    assert client.post("/api/auth/logout").status_code == 200


def test_expired_session_returns_spanish_error_and_can_logout(app, client):
    with app.app_context():
        token = create_access_token(identity="1", expires_delta=timedelta(seconds=-1))
    client.set_cookie("access_token_cookie", token, path="/api/")
    response = client.get("/api/recommendations/status")
    assert response.status_code == 401
    assert response.get_json()["error"] == "Tu sesión expiró. Inicia sesión de nuevo"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get_cookie("access_token_cookie", path="/api/") is None


def test_invalid_token_returns_spanish_json(client):
    response = client.get("/api/recommendations/status", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "La sesión no es válida. Inicia sesión de nuevo"


def test_cors_preflight_is_public_and_allows_credentials(client):
    response = client.options("/api/recommendations/train", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-CSRF-TOKEN,Content-Type",
    })
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "X-CSRF-TOKEN" in response.headers["Access-Control-Allow-Headers"]


@pytest.mark.parametrize("path", ["/api/health", "/health", "/docs", "/openapi.json"])
def test_health_and_docs_stay_public(client, path):
    assert client.get(path).status_code == 200


def test_openapi_documents_cookie_and_bearer_auth_and_logout(client):
    spec = client.get("/openapi.json").get_json()
    assert spec["paths"]["/api/auth/logout"]["post"]["security"] == []
    assert spec["paths"]["/api/recommendations"]["get"]["security"] == [
        {"bearerAuth": []}, {"cookieAuth": []},
    ]
    assert spec["paths"]["/api/recommendations/train"]["post"]["security"] == [
        {"bearerAuth": []}, {"cookieAuth": [], "csrfToken": []},
    ]
