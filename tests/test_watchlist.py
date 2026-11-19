"""Session isolation and episode tracking through the watchlist API."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_connection, initialize_database
from app.main import app
from packages.auth.routes import get_database


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "watchlist.db"
        initialize_database(path)

        def database():
            with get_connection(path) as connection:
                yield connection

        app.dependency_overrides[get_database] = database
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, base_url="https://testserver", headers={"X-Requested-With": "AnimeRater"})
        self.addCleanup(self.client.close)
        self.catalog = {
            101: {"id": 5, "anilist_id": 101, "title": "Known total", "episodes": 12},
            202: {"id": 6, "anilist_id": 202, "title": "Unknown total", "episodes": None},
        }
        lookup = patch("packages.watchlist.routes.anilist.get_anime_details", side_effect=self.catalog.get)
        self.addCleanup(lookup.stop)
        self.lookup = lookup.start()
        self.url = "/api/watchlist/101"

    def login(self, username):
        body = {"username": username, "password": "a-long-test-password"}
        self.client.post("/api/auth/register", json=body)
        self.assertEqual(self.client.post("/api/auth/login", json=body).status_code, 200)

    def entries(self):
        response = self.client.get("/api/watchlist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()["data"]

    def set_status(self, status, url=None):
        return self.client.put(url or self.url, json={"status": status})

    def correct_count(self, count, url=None):
        return self.client.put(f"{url or self.url}/progress", json={"episodes_watched": count})

    def test_authentication_and_request_validation(self):
        self.assertEqual(self.client.get("/api/watchlist").status_code, 401)
        self.assertEqual(self.set_status("watching").status_code, 401)
        self.assertEqual(self.correct_count(1).status_code, 401)
        self.assertEqual(self.client.post(f"{self.url}/progress").status_code, 401)
        self.assertEqual(self.client.delete(self.url).status_code, 401)
        self.login("viewer")
        self.assertEqual(self.client.delete(self.url, headers={"X-Requested-With": ""}).status_code, 403)
        self.assertEqual(self.set_status("paused").status_code, 422)
        self.assertEqual(self.set_status("watching", "/api/watchlist/0").status_code, 422)
        self.lookup.assert_not_called()
        self.assertEqual(self.set_status("watching", "/api/watchlist/5").status_code, 404)
        self.assertEqual(self.entries(), [])

    def test_status_changes_keep_one_entry_and_preserve_progress(self):
        self.login("viewer")
        entry = self.set_status("plan_to_watch").json()
        self.assertEqual((entry["anilist_id"], entry["status"], entry["episodes_watched"]), (101, "plan_to_watch", 0))
        self.assertEqual(self.correct_count(5).json()["status"], "plan_to_watch")
        for status in ("watching", "completed", "dropped", "plan_to_watch"):
            changed = self.set_status(status).json()
            self.assertEqual((changed["status"], changed["episodes_watched"]), (status, 5))
        self.assertEqual(self.entries(), [changed])

    def test_progress_increments_corrects_and_respects_known_total(self):
        self.login("viewer")
        self.assertEqual(self.set_status("watching").status_code, 200)
        self.assertEqual(self.correct_count(11).json()["episodes_watched"], 11)
        increment = self.client.post(f"{self.url}/progress").json()
        self.assertEqual((increment["episodes_watched"], increment["status"]), (12, "watching"))
        self.assertEqual(self.client.post(f"{self.url}/progress").status_code, 422)
        for invalid in (-1, 13, 5.5, "5", True, None, 9007199254740992):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.correct_count(invalid).status_code, 422)
        self.assertEqual(self.entries(), [increment])
        self.assertEqual(self.correct_count(0).json()["episodes_watched"], 0)

    def test_unknown_total_and_newly_available_limit(self):
        self.login("viewer")
        url = "/api/watchlist/202"
        self.assertIsNone(self.set_status("watching", url).json()["episodes"])
        self.assertEqual(self.correct_count(20, url).json()["episodes_watched"], 20)
        self.assertEqual(self.client.post(f"{url}/progress").json()["episodes_watched"], 21)
        self.catalog[202]["episodes"] = 21
        self.assertEqual(self.client.post(f"{url}/progress").status_code, 422)
        corrected = self.correct_count(18, url).json()
        self.assertEqual((corrected["episodes_watched"], corrected["episodes"]), (18, 21))

    def test_accounts_cannot_read_change_or_remove_each_others_entries(self):
        self.login("first")
        self.set_status("watching")
        self.correct_count(5)
        self.login("second")
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.correct_count(1).status_code, 404)
        self.assertEqual(self.client.post(f"{self.url}/progress").status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertEqual(self.set_status("dropped").json()["episodes_watched"], 0)

        self.login("first")
        self.assertEqual([(row["status"], row["episodes_watched"]) for row in self.entries()], [("watching", 5)])
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.set_status("plan_to_watch").json()["episodes_watched"], 0)

        self.login("second")
        self.assertEqual([(row["status"], row["episodes_watched"]) for row in self.entries()], [("dropped", 0)])
