"""Media ownership checks using isolated SQL, MongoDB, and GridFS doubles."""

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.exceptions import Unauthorized

from tests import support  # noqa: F401


class FakeObjectId(str):
    def __new__(cls, value):
        if len(value) != 24 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("Invalid ObjectId")
        return super().__new__(cls, value)


class MediaIdentityTests(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(anime_media=Mock())
        self.fs = Mock()
        self.file_id = FakeObjectId("1234567890abcdef12345678")
        self.fs.put.return_value = self.file_id
        self.fs.exists.return_value = True

        mongo = ModuleType("config.mongodb")
        mongo.db, mongo.fs = self.db, self.fs
        bson = ModuleType("bson")
        bson.ObjectId = FakeObjectId
        gridfs = ModuleType("gridfs")
        gridfs.__path__ = []
        gridfs_errors = ModuleType("gridfs.errors")
        gridfs_errors.NoFile = type("NoFile", (Exception,), {})
        requests = ModuleType("requests")
        requests.get = Mock(side_effect=AssertionError("Network is disabled in media tests"))
        requests.exceptions = SimpleNamespace(RequestException=RuntimeError)
        jikan = ModuleType("services.jikan")
        jikan.get_anime = Mock(side_effect=AssertionError("Network is disabled in media tests"))
        source = Path(__file__).resolve().parents[1] / "routes" / "media.py"
        spec = importlib.util.spec_from_file_location("_media_identity_under_test", source)
        self.media = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "config.mongodb": mongo,
            "bson": bson,
            "gridfs": gridfs,
            "gridfs.errors": gridfs_errors,
            "requests": requests,
            "services.jikan": jikan,
        }):
            spec.loader.exec_module(self.media)

        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="media-tests-secret-at-least-32-characters",
        )
        JWTManager(self.app)
        self.app.register_blueprint(self.media.media_bp, url_prefix="/api/media")
        self.client = self.app.test_client()
        self.account = {"id": 7, "profile": {"userId": 902}}
        self.current_user = self.enterContext(
            patch.object(self.media, "get_current_user", return_value=self.account)
        )
        with self.app.app_context():
            self.token = create_access_token(identity="7")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def upload(self, headers):
        return self.client.post(
            "/api/media/45",
            data={"file": (BytesIO(b"image bytes"), "cover.png", "image/png")},
            headers=headers,
        )

    def test_upload_records_authenticated_account_instead_of_anime_profile(self):
        response = self.upload(self.headers)

        self.assertEqual(response.status_code, 201)
        self.current_user.assert_called_once_with()
        self.assertEqual(self.fs.put.call_args.kwargs["metadata"]["uploadedBy"], 7)
        self.assertEqual(self.db.anime_media.insert_one.call_args.args[0]["uploadedBy"], 7)

    def test_upload_and_delete_require_valid_jwt_before_account_or_storage_access(self):
        self.assertEqual(self.upload({}).status_code, 401)
        response = self.client.delete(f"/api/media/file/{self.file_id}")

        self.assertEqual(response.status_code, 401)
        self.current_user.assert_not_called()
        self.fs.put.assert_not_called()
        self.fs.delete.assert_not_called()
        self.db.anime_media.insert_one.assert_not_called()

    def test_deleted_account_cannot_upload_or_delete(self):
        self.current_user.side_effect = Unauthorized("La cuenta ya no existe")

        self.assertEqual(self.upload(self.headers).status_code, 401)
        response = self.client.delete(
            f"/api/media/file/{self.file_id}", headers=self.headers
        )

        self.assertEqual(response.status_code, 401)
        self.fs.put.assert_not_called()
        self.fs.exists.assert_not_called()
        self.fs.delete.assert_not_called()
        self.db.anime_media.insert_one.assert_not_called()

    def test_account_can_delete_its_uploaded_media(self):
        self.db.anime_media.find_one.return_value = {
            "fileId": self.file_id, "uploadedBy": 7
        }

        response = self.client.delete(
            f"/api/media/file/{self.file_id}", headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.db.anime_media.find_one.assert_called_once_with({"fileId": self.file_id})
        self.fs.delete.assert_called_once_with(self.file_id)
        self.db.anime_media.delete_many.assert_called_once_with({"fileId": self.file_id})

    def test_other_accounts_and_unowned_cached_media_are_not_deleted(self):
        for stored in (
            {"fileId": self.file_id, "uploadedBy": 8},
            {"fileId": self.file_id, "uploadedBy": 902},
            {"fileId": self.file_id, "source": "jikan"},
            {"fileId": self.file_id, "uploadedBy": None},
            None,
        ):
            with self.subTest(stored=stored):
                self.db.anime_media.find_one.return_value = stored
                response = self.client.delete(
                    f"/api/media/file/{self.file_id}", headers=self.headers
                )
                self.assertEqual(response.status_code, 403)
        self.fs.delete.assert_not_called()
        self.db.anime_media.delete_many.assert_not_called()

    def test_public_media_listing_and_cached_image_do_not_require_an_account(self):
        self.db.anime_media.find.return_value = []
        self.assertEqual(self.client.get("/api/media/45").status_code, 200)
        self.db.anime_media.find_one.return_value = {"fileId": self.file_id}
        image = BytesIO(b"image bytes")
        image.content_type = "image/png"
        self.fs.get.return_value = image

        response = self.client.get("/api/media/45/image")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"image bytes")
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=3600")
        self.current_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
