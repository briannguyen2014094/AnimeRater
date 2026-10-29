"""Validation, persistence, session protection, and account isolation for ratings."""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app
from packages.auth.routes import get_database
from packages.catalog.anilist_client import AniListClient, RateLimited


class RatingsTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "ratings.db"
        initialize_database(self.path)

        def database():
            with get_connection(self.path) as connection:
                yield connection

        app.dependency_overrides[get_database] = database
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.addCleanup(self.client.close)
        self.headers = {"X-Requested-With": "AnimeRater"}

    def login(self, username):
        body = {"username": username, "password": "a-long-test-password"}
        self.client.post("/api/auth/register", json=body, headers=self.headers)
        self.assertEqual(self.client.post("/api/auth/login", json=body, headers=self.headers).status_code, 200)

    def save(self, rating, anime_id=1):
        return self.client.put(f"/api/ratings/{anime_id}", json={"rating": rating}, headers=self.headers)

    def test_set_edit_remove_and_persist_across_connections(self):
        self.login("student")
        self.assertEqual(self.client.get("/api/ratings/1").json(), {"anime_id": 1, "rating": None})
        for value in (1, 10, 7):
            response = self.save(value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"anime_id": 1, "rating": value})
        self.save(4, anime_id=2)
        initialize_database(self.path)
        with get_connection(self.path) as connection:
            rows = connection.execute("SELECT anime_id, rating FROM ratings ORDER BY anime_id").fetchall()
            self.assertEqual([tuple(row) for row in rows], [(1, 7), (2, 4)])
        self.client.post("/api/auth/logout", headers=self.headers)
        self.login("student")
        response = self.client.get("/api/ratings/1")
        self.assertEqual(response.json()["rating"], 7)
        self.assertEqual(response.headers["cache-control"], "no-store")
        for _ in range(2):
            self.assertEqual(self.client.delete("/api/ratings/1", headers=self.headers).status_code, 204)
        self.assertIsNone(self.client.get("/api/ratings/1").json()["rating"])
        self.assertEqual(self.client.get("/api/ratings/2").json()["rating"], 4)

    def test_accounts_cannot_read_edit_or_delete_each_others_ratings(self):
        self.login("first")
        self.save(8)
        self.login("second")
        self.assertIsNone(self.client.get("/api/ratings/1").json()["rating"])
        self.client.delete("/api/ratings/1", headers=self.headers)
        self.save(3)
        self.login("first")
        self.assertEqual(self.client.get("/api/ratings/1").json()["rating"], 8)
        self.save(9)
        self.client.delete("/api/ratings/1", headers=self.headers)
        self.login("second")
        self.assertEqual(self.client.get("/api/ratings/1").json()["rating"], 3)

    def test_rejects_invalid_ratings_without_changing_saved_value(self):
        self.login("student")
        self.save(6)
        for rating in (0, 11, -1, 5.5, 5.0, "8", True, False, None, [], {}):
            with self.subTest(rating=rating):
                self.assertEqual(self.save(rating).status_code, 422)
        self.assertEqual(self.client.put("/api/ratings/1", json={}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get("/api/ratings/1").json()["rating"], 6)
        for anime_id in (0, -1, "abc", "1.5", 9007199254740992):
            with self.subTest(anime_id=anime_id):
                self.assertEqual(self.client.get(f"/api/ratings/{anime_id}").status_code, 422)
                self.assertEqual(self.save(5, anime_id).status_code, 422)
                self.assertEqual(self.client.delete(f"/api/ratings/{anime_id}", headers=self.headers).status_code, 422)

    def test_every_operation_requires_a_current_session(self):
        for phase in ("guest", "expired", "logged-out"):
            if phase == "expired":
                self.login("student")
                with get_connection(self.path) as connection:
                    connection.execute("UPDATE sessions SET expires_at = 0")
            elif phase == "logged-out":
                self.login("student")
                self.client.post("/api/auth/logout", headers=self.headers)
            with self.subTest(phase=phase):
                self.assertEqual(self.client.get("/api/ratings").status_code, 401)
                self.assertEqual(self.client.get("/api/ratings/library").status_code, 401)
                self.assertEqual(self.client.get("/api/ratings/1").status_code, 401)
                self.assertEqual(self.save(5).status_code, 401)
                self.assertEqual(self.client.delete("/api/ratings/1", headers=self.headers).status_code, 401)

    def test_mutations_require_csrf_header(self):
        self.login("student")
        self.assertEqual(self.client.put("/api/ratings/1", json={"rating": 5}).status_code, 403)
        self.save(7)
        self.assertEqual(self.client.delete("/api/ratings/1").status_code, 403)
        self.assertEqual(self.client.get("/api/ratings/1").json()["rating"], 7)

    def test_library_includes_existing_ratings_and_preserves_anilist_ids(self):
        self.login("first")
        self.save(9, 101)
        self.save(4, 202)
        with patch("packages.ratings.routes.anilist.get_anime_by_ids", return_value={
            101: {"id": 5, "anilist_id": 101, "title": "Saved show", "score": 7.5},
        }) as lookup:
            response = self.client.get("/api/ratings/library")
            lookup.assert_called_once_with([101, 202])
        self.assertEqual(response.headers["cache-control"], "no-store")
        rows = response.json()["data"]
        self.assertEqual((rows[0]["id"], rows[0]["anilist_id"], rows[0]["rating"]), (5, 101, 9))
        self.assertTrue(rows[1]["unresolved"])
        self.assertEqual(rows[1]["anilist_id"], 202)
        self.assertEqual(self.client.get("/api/ratings").json()["data"], [
            {"anime_id": 101, "rating": 9}, {"anime_id": 202, "rating": 4},
        ])
        self.login("second")
        with patch("packages.ratings.routes.anilist.get_anime_by_ids", return_value={}) as lookup:
            self.assertEqual(self.client.get("/api/ratings/library").json(), {"data": []})
            lookup.assert_called_once_with([])
        self.assertEqual(self.client.get("/api/ratings").json(), {"data": []})
        self.client.post("/api/auth/logout", headers=self.headers)
        for path in ("/api/ratings", "/api/ratings/library"):
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_library_reports_upstream_failures_without_losing_ratings(self):
        self.login("student")
        self.save(8)
        for error, status in ((RuntimeError("offline"), 502), (RateLimited(30), 503)):
            with patch("packages.ratings.routes.anilist.get_anime_by_ids", side_effect=error):
                response = self.client.get("/api/ratings/library")
            self.assertEqual(response.status_code, status)
            if status == 503:
                self.assertEqual(response.headers["retry-after"], "30")
            self.assertEqual(self.client.get("/api/ratings/1").json()["rating"], 8)

    def test_rated_anime_lookup_batches_caches_and_does_not_guess_mal_ids(self):
        client = AniListClient()
        self.addCleanup(client.client.close)
        def payload(query, variables):
            return {"data": {"Page": {"media": [
                {"id": anime_id, "idMal": anime_id + 1000, "title": {"english": str(anime_id)}}
                for anime_id in variables["ids"]
            ]}}}
        with patch.object(client, "_post", side_effect=payload) as post:
            self.assertEqual(client.get_anime_by_ids([]), {})
            self.assertEqual(client.get_anime_by_ids([9007199254740991]), {})
            self.assertEqual(post.call_count, 0)
            rows = client.get_anime_by_ids(list(range(1, 122)))
            self.assertEqual([len(call.args[1]["ids"]) for call in post.call_args_list], [50, 50, 21])
            self.assertEqual(rows[1]["id"], 1001)
            self.assertEqual(rows[1]["anilist_id"], 1)
            client.get_anime_by_ids(list(range(1, 122)))
            self.assertEqual(post.call_count, 3)

    def test_database_constraints_and_account_deletion(self):
        self.login("student")
        self.save(7)
        with get_connection(self.path) as connection:
            user_id = connection.execute("SELECT id FROM users").fetchone()["id"]
            for rating in (0, 11, 4.5, "invalid", None):
                with self.subTest(rating=rating), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("INSERT INTO ratings VALUES (?, 2, ?)", (user_id, rating))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO ratings VALUES (?, 1, 5)", (user_id,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO ratings VALUES (?, 0, 5)", (user_id,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO ratings VALUES (999, 1, 5)")
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ratings").fetchone()[0], 0)

    def test_startup_adds_ratings_without_losing_existing_accounts_or_favorites(self):
        self.login("student")
        self.client.post("/api/favorites", json={"id": 1, "title": "Cowboy Bebop"}, headers=self.headers)
        with get_connection(self.path) as connection:
            connection.execute("DROP TABLE ratings")
        initialize_database(self.path)
        initialize_database(self.path)
        self.assertEqual(self.client.get("/api/favorites").json()["data"][0]["title"], "Cowboy Bebop")
        self.assertEqual(self.save(9).status_code, 200)
