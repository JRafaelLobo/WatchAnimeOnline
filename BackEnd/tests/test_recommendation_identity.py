"""Recommendation access regressions; no SQL, Spark, or network is started."""

from datetime import timedelta
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from tests import support  # noqa: F401
from routes import recommendations


class RecommendationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="recommendation-tests-secret-at-least-32-characters",
        )
        JWTManager(self.app)
        self.app.register_blueprint(
            recommendations.recommendations_bp,
            url_prefix="/api/recommendations",
        )
        self.client = self.app.test_client()
        self.account = {
            "id": 7,
            "nombre": "animefan",
            "email": "fan@example.test",
            "fechaCreacion": None,
            "profile": {
                "userId": 902,
                "username": "animefan",
                "meanScore": 8.1,
                "reviewCount": 12,
            },
        }
        self.current_user = self.enterContext(
            patch.object(recommendations, "get_current_user", return_value=self.account)
        )
        self.trained = self.enterContext(
            patch.object(recommendations.recommender, "has_trained_user", return_value=True)
        )
        self.personal = self.enterContext(
            patch.object(
                recommendations.recommender,
                "generate_recommendations",
                return_value=[{"movieId": 45, "predictedRating": 8.6}],
            )
        )
        self.general = self.enterContext(
            patch.object(
                recommendations.recommender,
                "generate_global_recommendations",
                return_value=[{"movieId": 88, "predictedRating": 8.2}],
            )
        )
        with self.app.app_context():
            self.token = create_access_token(identity="7")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_current_recommendations_use_profile_id_instead_of_auth_id(self):
        response = self.client.get("/api/recommendations/me?limit=6", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.json["mode"], "personalized")
        self.assertEqual(response.json["userId"], 902)
        self.trained.assert_called_once_with(902)
        self.personal.assert_called_once_with(902, 6)
        self.general.assert_not_called()

    def test_missing_profile_uses_general_recommendations(self):
        self.account["profile"] = None

        response = self.client.get("/api/recommendations/me", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "global")
        self.assertEqual(response.json["recommendations"][0]["movieId"], 88)
        self.personal.assert_not_called()
        self.trained.assert_not_called()
        self.general.assert_called_once_with(10)

    def test_profile_absent_from_model_uses_general_recommendations(self):
        self.trained.return_value = False

        response = self.client.get("/api/recommendations/me", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "global")
        self.personal.assert_not_called()
        self.general.assert_called_once_with(10)

    def test_exhausted_personal_recommendations_do_not_fall_back_to_seen_items(self):
        self.personal.return_value = []

        response = self.client.get("/api/recommendations/me", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "personalized")
        self.assertEqual(response.json["recommendations"], [])
        self.assertEqual(response.json["returnedCount"], 0)
        self.general.assert_not_called()

    def test_explicit_profile_route_accepts_only_the_accounts_linked_profile(self):
        for other_id in (7, 903):
            with self.subTest(other_id=other_id):
                response = self.client.get(
                    f"/api/recommendations/{other_id}", headers=self.headers
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")

        self.personal.assert_not_called()
        self.general.assert_not_called()
        self.trained.assert_not_called()
        response = self.client.get("/api/recommendations/902", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.personal.assert_called_once_with(902, 10)

    def test_unlinked_account_cannot_request_an_arbitrary_profile(self):
        self.account["profile"] = None

        response = self.client.get("/api/recommendations/7", headers=self.headers)

        self.assertEqual(response.status_code, 403)
        self.personal.assert_not_called()
        self.general.assert_not_called()

    def test_personal_routes_reject_missing_or_expired_tokens_before_data_access(self):
        with self.app.app_context():
            expired = create_access_token(identity="7", expires_delta=timedelta(seconds=-1))
        for path in ("/api/recommendations/me", "/api/recommendations/902"):
            for headers in ({}, {"Authorization": f"Bearer {expired}"}):
                with self.subTest(path=path, headers_present=bool(headers)):
                    response = self.client.get(path, headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.headers.get("Cache-Control"), "no-store")

        self.current_user.assert_not_called()
        self.trained.assert_not_called()
        self.personal.assert_not_called()
        self.general.assert_not_called()

    def test_model_error_is_reported_as_service_unavailable(self):
        self.trained.side_effect = RuntimeError("Spark unavailable")

        response = self.client.get("/api/recommendations/me", headers=self.headers)

        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json)
        self.personal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
