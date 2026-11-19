from contextlib import ExitStack
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from packages.catalog.anilist_client import AniListClient


def catalog_payload(ids=(), *, has_next=False):
    return {"data": {"Page": {
        "media": [{"id": anime_id} for anime_id in ids],
        "pageInfo": {"hasNextPage": has_next},
    }}}


class CatalogFilterTests(unittest.TestCase):
    def setUp(self):
        anilist = AniListClient()
        self.addCleanup(anilist.client.close)
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.post = patches.enter_context(patch.object(anilist, "_post"))
        patches.enter_context(patch("app.main.anilist", anilist))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_title_and_all_filters_are_sent_to_anilist(self):
        self.post.return_value = catalog_payload([1])
        response = self.client.get("/api/catalog/search", params={
            "q": " Cowboy Bebop ", "genre": "Sci-Fi", "year": 1998, "format": "TV",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["anilist_id"], 1)
        query, variables = self.post.call_args.args
        for fragment in ("genre: $genre", "format: $format", "startDate_greater: $yearStart",
                         "startDate_lesser: $yearEnd", "search: $search", "isAdult: false"):
            self.assertIn(fragment, query)
        self.assertEqual(variables, {
            "search": "cowboy bebop", "genre": "Sci-Fi", "format": "TV",
            "yearStart": 19971231, "yearEnd": 19990000, "sort": ("SEARCH_MATCH",),
            "page": 1, "perPage": 50,
        })

    def test_filters_work_without_a_title(self):
        self.post.return_value = catalog_payload([3])
        response = self.client.get("/api/catalog/search", params={"genre": "Slice of Life"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["anilist_id"], 3)
        variables = self.post.call_args.args[1]
        self.assertNotIn("search", variables)
        self.assertEqual(variables["genre"], "Slice of Life")
        self.assertEqual(variables["sort"], ("SCORE_DESC",))
        self.assertEqual(self.client.get("/api/catalog/search").json()["data"], [])
        self.post.assert_called_once()

    def test_filtered_pages_share_chunks_but_filter_combinations_do_not(self):
        self.post.side_effect = [
            catalog_payload(range(1, 51), has_next=True),
            catalog_payload([51]),
            catalog_payload([52]),
            catalog_payload([53]),
            catalog_payload([54]),
        ]
        filters = {"genre": "Action", "year": 2024, "format": "TV"}

        def get_page(page=1, **changes):
            response = self.client.get("/api/catalog/search", params={
                **filters, "page": page, **changes,
            })
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["page"], page)
            return [anime["anilist_id"] for anime in body["data"]], body["has_next_page"]

        self.assertEqual(get_page(1), (list(range(1, 26)), True))
        self.assertEqual(get_page(2), (list(range(26, 51)), True))
        self.post.assert_called_once()
        self.assertEqual(get_page(3), ([51], False))
        first_chunk, second_chunk = [call.args[1] for call in self.post.call_args_list]
        self.assertEqual(second_chunk, {**first_chunk, "page": 2})
        self.assertEqual(get_page(genre="Comedy"), ([52], False))
        self.assertEqual(get_page(year=2023), ([53], False))
        self.assertEqual(get_page(format="MOVIE"), ([54], False))

    def test_invalid_filters_are_rejected_before_contacting_anilist(self):
        for filters in ({"genre": "Invalid"}, {"year": 0}, {"year": "later"}, {"format": "MANGA"}):
            with self.subTest(filters=filters):
                self.assertEqual(self.client.get("/api/catalog/search", params=filters).status_code, 422)
        self.post.assert_not_called()
