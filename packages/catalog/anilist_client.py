import re
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"

DEFAULT_HEADERS = {
    "User-Agent": "AnimeRaterApp",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

TOP_ANIME_QUERY = """
query GetTopAnime($page: Int, $perPage: Int) {
    Page(page: $page, perPage: $perPage) {
        media(type: ANIME, sort: SCORE_DESC) {
            id
            idMal
            title {
                english
                romaji
            }
            description
            episodes
            averageScore
            coverImage {
                large
            }
            genres
        }
    }
}
"""

SEARCH_ANIME_QUERY = """
query SearchAnime($search: String, $page: Int, $perPage: Int) {
    Page(page: $page, perPage: $perPage) {
        media(type: ANIME, search: $search, sort: SEARCH_MATCH) {
            id
            idMal
            title {
                english
                romaji
            }
            description
            episodes
            averageScore
            coverImage {
                large
            }
            genres
        }
    }
}
"""


class AniListClient:
    # AniList allows 90 requests a minute
    CACHE_TTL_SECONDS = 300
    CACHE_MAX_ENTRIES = 128

    def __init__(self):
        self.client = httpx.Client(
            base_url=ANILIST_GRAPHQL_URL,
            headers=DEFAULT_HEADERS,
        )
        # ordered least-recently-used first, so eviction is a single popitem
        self._anime_cache: OrderedDict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = OrderedDict()
        # FastAPI runs these sync endpoints in a thread pool, so the cache is shared across threads
        self._cache_lock = threading.Lock()
    
    @staticmethod
    def _clean_html(raw_html: str | None) -> str | None:
        """AniList descriptions often contain <br> or <i> tags; strip them cleanly."""
        if not raw_html:
            return None
        return re.sub(r"<[^<]+?>", "", raw_html).strip()
    
    def _normalize_anime(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize raw AniList media payload to match platform schema."""
        title_info = raw.get("title") or {}
        chosen_title = title_info.get("english") or title_info.get("romaji") or "Unknown Title"

        raw_score = raw.get("averageScore")
        score = round(raw_score / 10.0, 2) if raw_score is not None else None

        return {
            # idMal retains compatibility with MyAnimeList IDs
            "id": raw.get("idMal") or raw.get("id"),
            "title": chosen_title,
            "synopsis": self._clean_html(raw.get("description")),
            "episodes": raw.get("episodes"),
            "score": score,
            "image_url": (raw.get("coverImage") or {}).get("large"),
            "genres": raw.get("genres") or [],
        }
        
    @staticmethod
    def _verify_payload(payload: dict[str, Any]) -> bool:
        if "errors" in payload:
            for err in payload.get("errors", []):
                print(f"[WARNING] AniList GraphQL Error: {err.get('message')}")
            return False

        media = payload.get("data", {}).get("Page", {}).get("media", [])
        return len(media) > 0
        
    def _normalize_payload(self, payload: dict[str, Any], func: Any = None) -> list[dict[str, Any]]:
        if func:
            func_name = getattr(func, "__name__", "query")
            print(f"Normalized payload for {func_name}")

        if not self._verify_payload(payload):
            return []

        media_items = payload.get("data", {}).get("Page", {}).get("media", [])
        return [self._normalize_anime(item) for item in media_items]
        
    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post("", json={"query": query, "variables": variables})
        response.raise_for_status()
        return response.json()

    def _cache_get(self, key: tuple[Any, ...]) -> list[dict[str, Any]] | None:
        """Return a live cache entry, or None when it is missing or expired."""
        with self._cache_lock:
            entry = self._anime_cache.get(key)
            if entry is None:
                return None

            stored_at, value = entry
            if time.monotonic() - stored_at >= self.CACHE_TTL_SECONDS:
                del self._anime_cache[key]
                return None

            self._anime_cache.move_to_end(key)
            return value

    def _cache_put(self, key: tuple[Any, ...], value: list[dict[str, Any]]) -> None:
        # A GraphQL error and a no-match both come back as an empty list
        if not value:
            return

        with self._cache_lock:
            self._anime_cache[key] = (time.monotonic(), value)
            self._anime_cache.move_to_end(key)
            while len(self._anime_cache) > self.CACHE_MAX_ENTRIES:
                self._anime_cache.popitem(last=False)

    def get_top_anime(self, page: int = 1, limit: int = 15) -> list[dict[str, Any]]:
        cache_key = ("top", page, limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        variables = {"page": page, "perPage": limit}
        payload = self._post(TOP_ANIME_QUERY, variables)
        results = self._normalize_payload(payload, func=self.get_top_anime)
        self._cache_put(cache_key, results)
        return results

    def search_anime(self, query: str, page: int = 1, limit: int = 15) -> list[dict[str, Any]]:
        """Search AniList by title. Returns [] for a blank query or when nothing matches."""
        if not query or not query.strip():
            return []

        # case and surrounding whitespace do not change the results, so they share one entry
        cache_key = ("search", query.strip().casefold(), page, limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        variables = {"search": query.strip(), "page": page, "perPage": limit}
        payload = self._post(SEARCH_ANIME_QUERY, variables)
        results = self._normalize_payload(payload, func=self.search_anime)
        self._cache_put(cache_key, results)
        return results
    
if __name__ == "__main__":
    # debugging
    client = AniListClient()
    
    print("---top anime test---")
    top_anime = client.get_top_anime(page=1)
    # anime dict keys -> dict_keys(['id', 'title', 'synopsis', 'episodes', 'score', 'image_url', 'genres'])
    for anime in top_anime:
        print(f"[{anime['id']}] {anime['title']} | Score: {anime['score']} | Episodes: {anime['episodes']}")

    print("---search anime test---")
    search_results = client.search_anime("cowboy bebop", page=1)
    for anime in search_results:
        print(f"[{anime['id']}] {anime['title']} | Score: {anime['score']} | Episodes: {anime['episodes']}")

    print("---cache test---")
    cache_client = AniListClient()
    fetches = []

    def fake_post(query, variables):
        fetches.append(variables)
        return {"data": {"Page": {"media": [{
            "idMal": 1,
            "id": 1,
            "title": {"english": "Cached Show", "romaji": "Cached Show"},
            "description": "<i>cached</i>",
            "episodes": 1,
            "averageScore": 80,
            "coverImage": {"large": "u"},
            "genres": ["Action"],
        }]}}}

    cache_client._post = fake_post
    cache_client.get_top_anime(page=1, limit=5)
    cache_client.get_top_anime(page=1, limit=5)
    print(f"two identical calls sent {len(fetches)} request(s)")