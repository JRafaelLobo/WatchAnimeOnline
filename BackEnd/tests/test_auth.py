"""Existing-account login contract without starting application services."""

import json
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token, decode_token
from werkzeug.exceptions import ServiceUnavailable, Unauthorized

from tests import support  # noqa: F401
from routes import auth


class AuthRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="auth-tests-secret-at-least-32-characters",
        )
        JWTManager(self.app)
        self.app.register_blueprint(auth.auth_bp, url_prefix="/api/auth")
        self.client = self.app.test_client()
        self.account = {
            "id": 7,
            "nombre": "animefan",
            "email": "fan@example.test",
            "fechaCreacion": "2026-01-02T03:04:05",
            "profile": {
                "userId": 902,
                "username": "animefan",
                "meanScore": 8.1,
                "reviewCount": 12,
            },
        }
        self.authenticate = self.enterContext(
            patch.object(auth, "authenticate_user", return_value=self.account)
        )
        self.current_user = self.enterContext(
            patch.object(auth, "get_current_user", return_value=self.account)
        )

    def test_login_returns_account_profile_and_auth_account_jwt_subject(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": " FAN@EXAMPLE.TEST ", "password": " secret with spaces "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.json["user"], self.account)
        self.authenticate.assert_called_once_with("fan@example.test", " secret with spaces ")
        with self.app.app_context():
            claims = decode_token(response.json["accessToken"])
        self.assertEqual(claims["sub"], "7")
        self.assertNotIn("password", response.json["user"])
        self.assertNotIn("password_hash", response.json["user"])

    def test_invalid_json_payloads_are_rejected_before_account_lookup(self):
        invalid = [
            None,
            [],
            ["fan@example.test", "secret"],
            "credentials",
            17,
            True,
            {},
            {"email": "fan@example.test"},
            {"password": "secret"},
            {"email": "", "password": "secret"},
            {"email": "   ", "password": "secret"},
            {"email": "fan@example.test", "password": ""},
            {"email": ["fan@example.test"], "password": "secret"},
            {"email": "fan@example.test", "password": 12345678},
            {"email": "fan@example.test", "password": None},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/auth/login",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
        self.authenticate.assert_not_called()

    def test_malformed_or_non_json_requests_are_rejected(self):
        for body, content_type in (("{", "application/json"), ("email=fan", "text/plain")):
            with self.subTest(content_type=content_type):
                response = self.client.post(
                    "/api/auth/login", data=body, content_type=content_type
                )
                self.assertEqual(response.status_code, 400)
        self.authenticate.assert_not_called()

    def test_registration_is_not_available(self):
        response = self.client.post(
            "/api/auth/register",
            json={"nombre": "new", "email": "new@example.test", "password": "password123"},
        )

        self.assertIn(response.status_code, (404, 405))
        self.authenticate.assert_not_called()

    def test_login_database_outage_is_service_unavailable(self):
        self.authenticate.side_effect = ServiceUnavailable("SQL unavailable")

        response = self.client.post(
            "/api/auth/login", json={"email": "fan@example.test", "password": "secret"}
        )

        self.assertEqual(response.status_code, 503)

    def test_invalid_credentials_return_unauthorized_without_a_token(self):
        self.authenticate.return_value = None

        response = self.client.post(
            "/api/auth/login", json={"email": "fan@example.test", "password": "wrong"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("accessToken", response.json)

    def test_me_returns_the_current_account_including_its_profile(self):
        with self.app.app_context():
            token = create_access_token(identity="7")
        response = self.client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, self.account)
        self.current_user.assert_called_once_with()

    def test_me_rejects_missing_token_before_account_lookup(self):
        response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 401)
        self.current_user.assert_not_called()

    def test_me_rejects_token_for_deleted_account(self):
        self.current_user.side_effect = Unauthorized("Account no longer exists")
        with self.app.app_context():
            token = create_access_token(identity="7")

        response = self.client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
