"""Run with: python -m unittest discover -s tests -v"""

import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app
from packages.auth.routes import COOKIE_NAME, get_database
from packages.auth.service import hash_token
from packages.auth.mail import send_password_reset


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
        for endpoint in ("register", "login", "logout", "forgot-password", "reset-password", "recovery-email"):
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

    def request_reset(self):
        with patch.dict(os.environ, {
            "APP_BASE_URL": "https://anime.example", "SMTP_HOST": "smtp.example", "SMTP_FROM": "accounts@anime.example",
        }), patch("packages.auth.routes.send_password_reset") as send:
            response = self.post("forgot-password", {"username": "student"})
            self.assertEqual(response.status_code, 202)
            return send

    def test_password_recovery_and_session_revocation(self):
        self.register()
        self.post("login", self.credentials)
        old_session = self.client.cookies[COOKIE_NAME]
        with TestClient(app, base_url="https://testserver") as second_device:
            second_device.post("/api/auth/login", json=self.credentials, headers=self.headers)
            second_session = second_device.cookies[COOKIE_NAME]
        self.assertEqual(self.post("recovery-email", {
            "email": "student@example.com", "password": "wrong-password",
        }).status_code, 401)
        self.assertEqual(self.post("recovery-email", {
            "email": "student@example.com", "password": self.credentials["password"],
        }).status_code, 204)
        send = self.request_reset()
        email, token = send.call_args.args
        self.assertEqual(email, "student@example.com")
        with get_connection(self.path) as connection:
            row = connection.execute("SELECT * FROM password_resets").fetchone()
            self.assertEqual(row["token_hash"], hash_token(token))
            self.assertNotEqual(row["token_hash"], token)
        self.request_reset().assert_not_called()
        new_password = "a-new-long-test-password"
        body = {"token": token, "password": new_password}
        self.assertEqual(self.post("reset-password", dict(body, password="short")).status_code, 422)
        self.assertEqual(self.post("reset-password", body).status_code, 204)
        self.assertEqual(self.post("reset-password", body).status_code, 400)
        with get_connection(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
        for token in (old_session, second_session):
            self.client.cookies.clear()
            self.client.cookies.set(COOKIE_NAME, token)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.post("login", self.credentials).status_code, 401)
        self.assertEqual(self.post("login", dict(self.credentials, password=new_password)).status_code, 200)
        with get_connection(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0], 0)
            password_hash = connection.execute("SELECT password_hash FROM users").fetchone()[0]
            self.assertTrue(password_hash.startswith("$argon2id$"))

    def test_password_hashes_are_salted(self):
        self.register()
        self.post("register", dict(self.credentials, username="another_student"))
        with get_connection(self.path) as connection:
            hashes = [row[0] for row in connection.execute("SELECT password_hash FROM users")]
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertTrue(all(value.startswith("$argon2id$") for value in hashes))

    def test_changing_recovery_email_invalidates_old_links(self):
        self.post("register", dict(self.credentials, email="old@example.com"))
        token = self.request_reset().call_args.args[1]
        self.post("login", self.credentials)
        self.assertEqual(self.post("recovery-email", {
            "email": "new@example.com", "password": self.credentials["password"],
        }).status_code, 204)
        self.assertEqual(self.post("reset-password", {
            "token": token, "password": "another-long-password",
        }).status_code, 400)
        self.assertEqual(self.request_reset().call_args.args[0], "new@example.com")

    def test_recovery_expiry_replacement_and_generic_responses(self):
        self.post("register", dict(self.credentials, email="student@example.com"))
        token = self.request_reset().call_args.args[1]
        with get_connection(self.path) as connection:
            connection.execute("UPDATE password_resets SET requested_at = 0")
        replacement = self.request_reset().call_args.args[1]
        self.assertEqual(self.post("reset-password", {"token": token, "password": self.credentials["password"]}).status_code, 400)
        with get_connection(self.path) as connection:
            connection.execute("UPDATE password_resets SET expires_at = 0")
        self.assertEqual(self.post("reset-password", {"token": replacement, "password": self.credentials["password"]}).status_code, 400)
        with patch.dict(os.environ, {
            "APP_BASE_URL": "https://anime.example", "SMTP_HOST": "smtp.example", "SMTP_FROM": "accounts@anime.example",
        }), patch("packages.auth.routes.send_password_reset") as send:
            known = self.post("forgot-password", {"username": "student"})
            unknown = self.post("forgot-password", {"username": "unknown"})
            self.assertEqual(known.json(), unknown.json())
            self.assertNotIn("token", known.text)
            self.assertEqual(send.call_count, 1)

    def test_missing_recovery_email_and_configuration(self):
        self.register()
        self.request_reset().assert_not_called()
        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_FROM": "", "APP_BASE_URL": ""}):
            self.assertEqual(self.post("forgot-password", {"username": "student"}).status_code, 503)
        self.assertEqual(self.post("recovery-email", {"email": "student@example.com", "password": self.credentials["password"]}).status_code, 401)
        self.assertEqual(self.post("register", dict(self.credentials, email="invalid")).status_code, 422)

    def test_migrate_existing_database(self):
        path = Path(self.directory.name) / "legacy.db"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL)")
            connection.execute("INSERT INTO users VALUES (1, 'legacy', 'existing-hash')")
        connection.close()
        initialize_database(path)
        initialize_database(path)
        with get_connection(path) as connection:
            user = connection.execute("SELECT * FROM users").fetchone()
            self.assertEqual(user["password_hash"], "existing-hash")
            self.assertIsNone(user["email"])

    def test_reset_mail_uses_configured_origin_and_tls(self):
        with patch.dict(os.environ, {
            "APP_BASE_URL": "https://anime.example", "SMTP_HOST": "smtp.example", "SMTP_FROM": "accounts@anime.example",
            "SMTP_USERNAME": "smtp-user", "SMTP_PASSWORD": "smtp-secret",
        }), patch("packages.auth.mail.smtplib.SMTP") as smtp:
            send_password_reset("student@example.com", "a-secret-token")
            connection = smtp.return_value.__enter__.return_value
            connection.starttls.assert_called_once()
            connection.login.assert_called_once_with("smtp-user", "smtp-secret")
            message = connection.send_message.call_args.args[0]
            self.assertIn("https://anime.example/#reset_token=a-secret-token", message.get_content())


if __name__ == "__main__":
    unittest.main()
