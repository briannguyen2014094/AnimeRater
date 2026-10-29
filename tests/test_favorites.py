"""Account isolation and session enforcement for persisted favorites."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app
from packages.auth.routes import get_database


class FavoritesTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "favorites.db"
        initialize_database(self.path)

        def database():
            with get_connection(self.path) as connection:
                yield connection

        app.dependency_overrides[get_database] = database
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.addCleanup(self.client.close)
        self.headers = {"X-Requested-With": "AnimeRater"}
        self.anime = {"id": 1, "anilist_id": 1, "title": "Cowboy Bebop", "score": 8.9}

    def login(self, username):
        body = {"username": username, "password": "a-long-test-password"}
        self.client.post("/api/auth/register", json=body, headers=self.headers)
        self.assertEqual(self.client.post("/api/auth/login", json=body, headers=self.headers).status_code, 200)

    def save(self, anime=None):
        return self.client.post("/api/favorites", json=anime or self.anime, headers=self.headers)

    def test_requires_valid_session_for_every_operation(self):
        for phase in ("guest", "expired", "logged-out"):
            if phase == "expired":
                self.login("student")
                with get_connection(self.path) as connection:
                    connection.execute("UPDATE sessions SET expires_at = 0")
            elif phase == "logged-out":
                self.login("student")
                self.client.post("/api/auth/logout", headers=self.headers)
            self.assertEqual(self.client.get("/api/favorites").status_code, 401)
            self.assertEqual(self.save().status_code, 401)
            self.assertEqual(self.client.delete("/api/favorites/1", headers=self.headers).status_code, 401)

    def test_persistence_account_isolation_and_idempotency(self):
        self.login("first")
        self.assertEqual(self.save().status_code, 204)
        self.assertEqual(self.save().status_code, 204)
        response = self.client.get("/api/favorites")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(response.json()["data"]), 1)
        self.assertEqual(response.json()["data"][0]["title"], self.anime["title"])
        self.login("second")
        self.assertEqual(self.client.get("/api/favorites").json()["data"], [])
        self.assertEqual(self.client.delete("/api/favorites/1", headers=self.headers).status_code, 204)
        self.assertEqual(self.save(dict(self.anime, title="Second account's copy")).status_code, 204)
        self.login("first")
        self.assertEqual(self.client.get("/api/favorites").json()["data"][0]["title"], "Cowboy Bebop")
        self.assertEqual(self.client.delete("/api/favorites/1", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get("/api/favorites").json()["data"], [])
        self.login("second")
        self.assertEqual(len(self.client.get("/api/favorites").json()["data"]), 1)

    def test_mutations_require_csrf_header_and_validate_data(self):
        self.login("student")
        self.assertEqual(self.client.post("/api/favorites", json=self.anime).status_code, 403)
        self.assertEqual(self.client.delete("/api/favorites/1").status_code, 403)
        self.assertEqual(self.save(dict(self.anime, id=-1)).status_code, 422)
        self.assertEqual(self.save(dict(self.anime, title="")).status_code, 422)
        self.assertEqual(self.client.get("/api/favorites").json()["data"], [])

    def test_existing_database_is_upgraded_without_losing_favorites(self):
        legacy = self.path.parent / "legacy.db"
        with get_connection(legacy) as connection:
            connection.executescript("""
                CREATE TABLE favorites (
                    user_id INTEGER NOT NULL, anime_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, anime_id)
                );
                INSERT INTO favorites (user_id, anime_id) VALUES (1, 42);
            """)
        initialize_database(legacy)
        initialize_database(legacy)
        with get_connection(legacy) as connection:
            row = connection.execute("SELECT * FROM favorites").fetchone()
            self.assertEqual(row["anime_id"], 42)
            self.assertEqual(row["details"], "{}")
