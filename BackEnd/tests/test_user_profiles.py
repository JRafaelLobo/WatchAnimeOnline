"""Read-only account lookup and the approved unique-name profile mapping."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from werkzeug.exceptions import ServiceUnavailable, Unauthorized
from werkzeug.security import generate_password_hash

from tests import support  # noqa: F401
from services import users


class UserProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash(
            "existing password", method="pbkdf2:sha256:1000"
        )

    def setUp(self):
        self.app = Flask(__name__)
        self.enterContext(self.app.app_context())
        self.cursor = MagicMock()
        self.connection = MagicMock()
        self.connection.cursor.return_value = self.cursor
        self.connect = self.enterContext(
            patch.object(users, "get_connection", return_value=self.connection)
        )
        self.account = SimpleNamespace(
            id=7,
            nombre="animefan",
            email="fan@example.test",
            password_hash=self.password_hash,
            fecha_creacion=datetime(2026, 1, 2, 3, 4, 5),
        )
        self.profile = SimpleNamespace(
            user_id=902,
            username="animefan",
            stats_mean_score=Decimal("8.1"),
        )
        self.cursor.fetchone.side_effect = [self.account, SimpleNamespace(review_count=12)]
        self.cursor.fetchall.side_effect = [[(7,)], [self.profile]]

    def assert_read_only_and_closed(self):
        for call in self.cursor.execute.call_args_list:
            self.assertTrue(call.args[0].strip().upper().startswith("SELECT"))
        self.connection.commit.assert_not_called()
        self.cursor.close.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_valid_existing_password_reads_distinct_profile_and_review_ids(self):
        result = users.authenticate_user("fan@example.test", "existing password")

        self.assertEqual(result["id"], 7)
        self.assertEqual(result["fechaCreacion"], "2026-01-02T03:04:05")
        self.assertEqual(
            result["profile"],
            {"userId": 902, "username": "animefan", "meanScore": 8.1, "reviewCount": 12},
        )
        self.assertNotIn("password_hash", result)
        calls = self.cursor.execute.call_args_list
        self.assertEqual(calls[0].args[1], "fan@example.test")
        self.assertEqual(calls[2].args[1], "animefan")
        self.assertEqual(calls[3].args[1], 902)
        self.assert_read_only_and_closed()

    def test_wrong_password_does_not_load_profile(self):
        result = users.authenticate_user("fan@example.test", "wrong password")

        self.assertIsNone(result)
        self.cursor.fetchall.assert_not_called()
        self.assert_read_only_and_closed()

    def test_missing_account_does_not_load_profile(self):
        self.cursor.fetchone.side_effect = [None]

        result = users.authenticate_user("missing@example.test", "existing password")

        self.assertIsNone(result)
        self.cursor.fetchall.assert_not_called()
        self.assert_read_only_and_closed()

    def test_malformed_stored_password_hash_is_rejected(self):
        self.account.password_hash = "unsupported$hash"

        result = users.authenticate_user("fan@example.test", "existing password")

        self.assertIsNone(result)
        self.cursor.fetchall.assert_not_called()
        self.assert_read_only_and_closed()

    def test_get_user_reads_current_account_and_never_uses_account_id_as_profile(self):
        result = users.get_user(7)

        self.assertEqual(result["profile"]["userId"], 902)
        self.assertEqual(self.cursor.execute.call_args_list[0].args[1], 7)
        self.assert_read_only_and_closed()

    def test_missing_or_ambiguous_username_yields_no_profile(self):
        for profiles in ([], [self.profile, SimpleNamespace(user_id=903)]):
            with self.subTest(profile_count=len(profiles)):
                self.cursor.reset_mock()
                self.connection.reset_mock()
                self.cursor.fetchone.side_effect = [self.account]
                self.cursor.fetchall.side_effect = [[(7,)], profiles]

                result = users.get_user(7)

                self.assertIsNone(result["profile"])
                # No Reviews lookup or fallback lookup by matching numeric IDs.
                self.assertEqual(self.cursor.execute.call_count, 3)
                self.assert_read_only_and_closed()

    def test_duplicate_account_names_cannot_claim_a_shared_profile(self):
        self.cursor.fetchall.side_effect = [[(7,), (8,)]]

        result = users.get_user(7)

        self.assertIsNone(result["profile"])
        self.assertEqual(self.cursor.execute.call_count, 2)
        self.assert_read_only_and_closed()

    def test_nullable_dataset_score_is_preserved(self):
        self.profile.stats_mean_score = None

        result = users.get_user(7)

        self.assertIsNone(result["profile"]["meanScore"])

    def test_sql_failures_close_resources_and_become_service_unavailable(self):
        self.cursor.execute.side_effect = RuntimeError("SQL unreachable")

        with self.assertRaises(ServiceUnavailable):
            users.authenticate_user("fan@example.test", "existing password")

        self.assert_read_only_and_closed()

    def test_connection_failure_is_service_unavailable(self):
        self.connect.side_effect = RuntimeError("SQL unreachable")

        with self.assertRaises(ServiceUnavailable):
            users.get_user(7)

    def test_current_user_rejects_invalid_subjects_before_sql_access(self):
        for identity in (None, 7, [], "", "abc", "7.0", "-7", "0", "2147483648", "７"):
            with self.subTest(identity=identity):
                with patch.object(users, "get_jwt_identity", return_value=identity):
                    with self.assertRaises(Unauthorized):
                        users.get_current_user()
        self.connect.assert_not_called()

    def test_current_user_reloads_the_account_using_the_token_subject(self):
        account = {"id": 7, "profile": None}
        with patch.object(users, "get_jwt_identity", return_value="7"):
            with patch.object(users, "get_user", return_value=account) as get_user:
                self.assertEqual(users.get_current_user(), account)
        get_user.assert_called_once_with(7)

    def test_deleted_account_invalidates_the_session(self):
        self.cursor.fetchone.side_effect = [None]

        with patch.object(users, "get_jwt_identity", return_value="7"):
            with self.assertRaises(Unauthorized):
                users.get_current_user()


if __name__ == "__main__":
    unittest.main()
