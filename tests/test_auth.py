"""Run with: python -m unittest discover -s tests -v"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app
from packages.auth.routes import COOKIE_NAME, get_database
from packages.auth.service import hash_token


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "auth.db"
        initialize_database(self.path)

        def test_database():
            with get_connection(self.path) as connection:
                yield connection

        app.dependency_overrides[get_database] = test_database
        self.addCleanup(app.dependency_overrides.clear)
        # HTTPS exercises the default Secure cookie without changing settings.
        self.client = TestClient(app, base_url="https://testserver")
        self.addCleanup(self.client.close)
        self.headers = {"X-Requested-With": "AnimeRater"}
        self.credentials = {"username": "student", "password": "a-long-test-password"}

    def post(self, endpoint, credentials=None):
        return self.client.post(
            f"/api/auth/{endpoint}", json=credentials, headers=self.headers,
        )

    def register(self):
        response = self.post("register", self.credentials)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"id", "username"})

    def test_register_login_me_logout(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.register()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        response = self.post("login", self.credentials)
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"].lower()
        for flag in ("httponly", "secure", "samesite=lax", "max-age=604800"):
            self.assertIn(flag, cookie)
        token = self.client.cookies[COOKIE_NAME]
        with get_connection(self.path) as connection:
            user = connection.execute("SELECT * FROM users").fetchone()
            self.assertTrue(user["password_hash"].startswith("$argon2id$"))
            self.assertNotEqual(user["password_hash"], self.credentials["password"])
            session = connection.execute("SELECT * FROM sessions").fetchone()
            self.assertEqual(session["token_hash"], hash_token(token))
            self.assertNotEqual(session["token_hash"], token)
        for _ in range(2):
            response = self.client.get("/api/auth/me")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["username"], "student")
            self.assertEqual(response.headers["cache-control"], "no-store")
        response = self.post("logout")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertNotIn(COOKIE_NAME, self.client.cookies)
        self.client.cookies.set(COOKIE_NAME, token)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_duplicate_user_and_bad_credentials(self):
        self.register()
        duplicate = dict(self.credentials, username="STUDENT")
        self.assertEqual(self.post("register", duplicate).status_code, 409)
        wrong_password = dict(self.credentials, password="incorrect")
        unknown_user = dict(self.credentials, username="unknown")
        for credentials in (wrong_password, unknown_user):
            response = self.post("login", credentials)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "Invalid username or password")
            self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(self.post("login", duplicate).status_code, 200)

    def test_session_rotation_and_expiration(self):
        self.register()
        self.post("login", self.credentials)
        old_token = self.client.cookies[COOKIE_NAME]
        self.post("login", self.credentials)
        new_token = self.client.cookies[COOKIE_NAME]
        self.assertNotEqual(old_token, new_token)
        with get_connection(self.path) as connection:
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM sessions WHERE token_hash = ?", (hash_token(old_token),),
            ).fetchone())
            connection.execute("UPDATE sessions SET expires_at = 0")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, "made-up-token")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_validation_and_csrf_header(self):
        for endpoint in ("register", "login", "logout"):
            response = self.client.post(f"/api/auth/{endpoint}", json=self.credentials)
            self.assertEqual(response.status_code, 403)
        for credentials in (
            dict(self.credentials, password="short"),
            dict(self.credentials, password="x" * 129),
            dict(self.credentials, username="bad name"),
        ):
            self.assertEqual(self.post("register", credentials).status_code, 422)
        # No CORS permission is granted for another site's custom-header requests.
        response = self.client.options("/api/auth/login", headers={
            "Origin": "https://another-site.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Requested-With",
        })
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_local_http_cookie_setting(self):
        self.register()
        with patch.dict(os.environ, {"SESSION_COOKIE_SECURE": "false"}):
            with TestClient(app, base_url="http://testserver") as client:
                response = client.post("/api/auth/login", json=self.credentials, headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("secure", response.headers["set-cookie"].lower())
                self.assertEqual(client.get("/api/auth/me").status_code, 200)


if __name__ == "__main__":
    unittest.main()
