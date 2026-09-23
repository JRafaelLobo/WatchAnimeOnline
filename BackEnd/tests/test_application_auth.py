"""Application-level JWT/error/HTTP contracts with all startup I/O replaced."""

from datetime import timedelta
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from flask import Blueprint
from flask_jwt_extended import create_access_token
from werkzeug.exceptions import ServiceUnavailable, Unauthorized

from tests import support  # noqa: F401
from routes import auth


class ApplicationAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Unrelated catalogue/media adapters import Mongo/HTTP dependencies.
        # Keep the real application factory and authentication blueprints.
        anime_module = ModuleType("routes.anime")
        anime_module.anime_bp = Blueprint("anime_stub", __name__)
        media_module = ModuleType("routes.media")
        media_module.media_bp = Blueprint("media_stub", __name__)
        spec = importlib.util.spec_from_file_location(
            "isolated_application_auth", Path(__file__).resolve().parents[1] / "app.py"
        )
        cls.application = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"routes.anime": anime_module, "routes.media": media_module}):
            spec.loader.exec_module(cls.application)

    def setUp(self):
        self.enterContext(
            patch.dict(os.environ, {"JWT_SECRET": "application-tests-secret-at-least-32-characters"})
        )
        self.initialize_database = self.enterContext(
            patch.object(self.application, "initialize_database")
        )
        self.app = self.application.create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.account = {
            "id": 7,
            "nombre": "animefan",
            "email": "fan@example.test",
            "fechaCreacion": "2026-01-02T03:04:05",
            "profile": {"userId": 902, "username": "animefan", "meanScore": 8.1, "reviewCount": 12},
        }
        self.current_user = self.enterContext(
            patch.object(auth, "get_current_user", return_value=self.account)
        )
        with self.app.app_context():
            self.token = create_access_token(identity="7")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_missing_invalid_and_expired_tokens_return_json_401(self):
        with self.app.app_context():
            expired = create_access_token(identity="7", expires_delta=timedelta(seconds=-1))
        for headers in (
            {},
            {"Authorization": "Bearer not-a-jwt"},
            {"Authorization": f"Bearer {expired}"},
        ):
            with self.subTest(headers_present=bool(headers)):
                response = self.client.get("/api/auth/me", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertIsInstance(response.json["error"], str)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.current_user.assert_not_called()

    def test_account_errors_keep_json_contract_and_status(self):
        for error in (Unauthorized("Account unavailable"), ServiceUnavailable("SQL unavailable")):
            with self.subTest(status=error.code):
                self.current_user.side_effect = error
                response = self.client.get("/api/auth/me", headers=self.headers)
                self.assertEqual(response.status_code, error.code)
                self.assertEqual(response.json, {"error": error.description})

    def test_registration_is_absent_from_routes_and_public_api_contract(self):
        response = self.client.post("/api/auth/register", json={})

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json)
        spec = self.client.get("/openapi.json").json
        self.assertNotIn("/api/auth/register", spec["paths"])
        self.assertNotIn("RegisterRequest", spec["components"]["schemas"])

    def test_login_then_me_has_consistent_bare_account_shape_for_frontend(self):
        with patch.object(auth, "authenticate_user", return_value=self.account):
            login = self.client.post(
                "/api/auth/login", json={"email": "fan@example.test", "password": "secret"}
            )
        self.assertEqual(login.status_code, 200)
        me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {login.json['accessToken']}"},
        )

        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json, login.json["user"])
        self.assertEqual(me.json["profile"]["userId"], 902)
        self.assertNotIn("user", me.json)


if __name__ == "__main__":
    unittest.main()
