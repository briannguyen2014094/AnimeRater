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


class RateLimited(RuntimeError):
    """AniList answered 429; the client stands down until the window passes.

    429 is not an upstream outage, so it must not surface as a 502.
    """

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"AniList is rate limiting this client; retry in {retry_after:.0f}s")


# AniList silently clamps perPage to this, so it is the most a single request can return
ANILIST_MAX_PER_PAGE = 50
DEFAULT_RETRY_AFTER_SECONDS = 60.0


def _retry_after_seconds(header: str | None) -> float:
    try:
        return float(header) if header else DEFAULT_RETRY_AFTER_SECONDS
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS

TOP_ANIME_QUERY = """
query GetTopAnime($page: Int, $perPage: Int) {
    Page(page: $page, perPage: $perPage) {
        media(type: ANIME, sort: SCORE_DESC, isAdult: false) {
            id
            idMal
            title {
                english
                romaji
            }
            episodes
            averageScore
            coverImage {
                large
            }
            genres
        }
        pageInfo {
            hasNextPage
        }
    }
}
"""

SEARCH_ANIME_QUERY = """
query SearchAnime($search: String, $page: Int, $perPage: Int) {
    Page(page: $page, perPage: $perPage) {
        media(type: ANIME, search: $search, sort: SEARCH_MATCH, isAdult: false) {
            id
            idMal
            title {
                english
                romaji
            }
            episodes
            averageScore
            coverImage {
                large
            }
            genres
        }
        pageInfo {
            hasNextPage
        }
    }
}
"""

ANIME_DETAIL_QUERY = """
query GetAnimeDetails($id: Int) {
    Media(id: $id, type: ANIME) {
        id
        idMal
        isAdult
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
        self._anime_cache: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()
        # FastAPI runs these sync endpoints in a thread pool, so the cache is shared across threads
        self._cache_lock = threading.Lock()
        # once AniList answers 429, stop calling until the window it gave us has passed
        self._rate_limited_until = 0.0
    
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
            # the AniList id is always present, so detail lookups key off it
            "anilist_id": raw.get("id"),
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
        
    def _normalize_payload(self, payload: dict[str, Any], label: str = "") -> list[dict[str, Any]]:
        if label:
            print(f"Normalized payload for {label}")

        if not self._verify_payload(payload):
            return []

        media_items = payload.get("data", {}).get("Page", {}).get("media", [])
        return [self._normalize_anime(item) for item in media_items]
        
    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post("", json={"query": query, "variables": variables})
        if response.status_code == 429:
            retry_after = _retry_after_seconds(response.headers.get("retry-after"))
            self._rate_limited_until = time.monotonic() + retry_after
            raise RateLimited(retry_after)
        response.raise_for_status()
        return response.json()

    def _rate_limit_remaining(self) -> float:
        return max(0.0, self._rate_limited_until - time.monotonic())

    def _stale_or_raise(self, cache_key: tuple[Any, ...], retry_after: float) -> Any:
        """Serve an expired entry if we have one; a stale page beats an error."""
        stale = self._cache_get(cache_key, allow_stale=True)
        if stale is not None:
            return stale
        raise RateLimited(retry_after)

    def _cache_get(self, key: tuple[Any, ...], allow_stale: bool = False) -> Any:
        """Return a cache entry, or None when it is missing or expired.

        Expired entries are left in place rather than deleted, so that a request
        arriving during a rate-limit window can still fall back to them. They age
        out through the size cap instead.
        """
        with self._cache_lock:
            entry = self._anime_cache.get(key)
            if entry is None:
                return None

            stored_at, value = entry
            if not allow_stale and time.monotonic() - stored_at >= self.CACHE_TTL_SECONDS:
                return None

            self._anime_cache.move_to_end(key)
            return value

    def _cache_put(self, key: tuple[Any, ...], value: Any) -> None:
        # A GraphQL error and a no-match both normalize to an empty result,
        # so empties are never cached - a transient failure must not stick around
        if not value:
            return

        with self._cache_lock:
            self._anime_cache[key] = (time.monotonic(), value)
            self._anime_cache.move_to_end(key)
            while len(self._anime_cache) > self.CACHE_MAX_ENTRIES:
                self._anime_cache.popitem(last=False)

    @staticmethod
    def _has_next_page(payload: dict[str, Any]) -> bool:
        page_info = (payload.get("data", {}).get("Page", {}) or {}).get("pageInfo") or {}
        return bool(page_info.get("hasNextPage"))

    @staticmethod
    def _chunk_geometry(page: int, limit: int) -> tuple[int, int, int]:
        """Map one displayed page onto a single, larger AniList request.

        AniList caps perPage at 50, so one request covers as many displayed pages as
        fit inside that: at 25 per page, one request fills two displayed pages.
        Returns (anilist_page, fetch_size, offset).
        """
        pages_per_chunk = max(1, ANILIST_MAX_PER_PAGE // limit)
        fetch_size = limit * pages_per_chunk
        anilist_page = (page - 1) // pages_per_chunk + 1
        offset = ((page - 1) % pages_per_chunk) * limit
        return anilist_page, fetch_size, offset

    def _fetch_chunk(self, kind: str, query: str, variables: dict[str, Any],
                     anilist_page: int, fetch_size: int) -> dict[str, Any]:
        """Fetch, or reuse, the chunk of results that covers several displayed pages."""
        cache_key = (kind, str(variables.get("search", "")), anilist_page, fetch_size)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # while AniList is throttling us, do not spend attempts on calls that will 429
        remaining = self._rate_limit_remaining()
        if remaining > 0:
            return self._stale_or_raise(cache_key, remaining)

        request_variables = {**variables, "page": anilist_page, "perPage": fetch_size}
        try:
            payload = self._post(query, request_variables)
        except RateLimited as exc:
            return self._stale_or_raise(cache_key, exc.retry_after)

        items = self._normalize_payload(payload, label=kind)
        chunk = {"items": items, "has_next_page": self._has_next_page(payload)}
        if items:
            self._cache_put(cache_key, chunk)
        return chunk

    @staticmethod
    def _slice_chunk(chunk: dict[str, Any], offset: int, limit: int) -> dict[str, Any]:
        items = chunk["items"]
        # a chunk with items still left in it has a next page whatever pageInfo says
        has_next = offset + limit < len(items) or chunk["has_next_page"]
        return {"data": items[offset:offset + limit], "has_next_page": has_next}

    def get_top_page(self, page: int = 1, limit: int = 15) -> dict[str, Any]:
        """One displayed catalog page, served out of a larger cached chunk."""
        limit = max(1, min(limit, ANILIST_MAX_PER_PAGE))
        anilist_page, fetch_size, offset = self._chunk_geometry(page, limit)
        chunk = self._fetch_chunk("top", TOP_ANIME_QUERY, {}, anilist_page, fetch_size)
        return self._slice_chunk(chunk, offset, limit)

    def get_top_anime(self, page: int = 1, limit: int = 15) -> list[dict[str, Any]]:
        """Just the results, for callers that do not need the pagination flag."""
        return self.get_top_page(page=page, limit=limit)["data"]

    def get_search_page(self, query: str, page: int = 1, limit: int = 15) -> dict[str, Any]:
        """One displayed search page, served out of a larger cached chunk."""
        if not query or not query.strip():
            return {"data": [], "has_next_page": False}

        limit = max(1, min(limit, ANILIST_MAX_PER_PAGE))
        anilist_page, fetch_size, offset = self._chunk_geometry(page, limit)
        # case and surrounding whitespace do not change the results, so they share one entry
        variables = {"search": query.strip().casefold()}
        chunk = self._fetch_chunk("search", SEARCH_ANIME_QUERY, variables, anilist_page, fetch_size)
        return self._slice_chunk(chunk, offset, limit)

    def search_anime(self, query: str, page: int = 1, limit: int = 15) -> list[dict[str, Any]]:
        """Search AniList by title. Returns [] for a blank query or when nothing matches."""
        return self.get_search_page(query, page=page, limit=limit)["data"]

    def get_anime_details(self, anilist_id: int) -> dict[str, Any] | None:
        """Fetch one anime by AniList id, including the synopsis the list queries omit."""
        cache_key = ("detail", anilist_id)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        remaining = self._rate_limit_remaining()
        if remaining > 0:
            return self._stale_or_raise(cache_key, remaining)

        try:
            payload = self._post(ANIME_DETAIL_QUERY, {"id": anilist_id})
        except httpx.HTTPStatusError as exc:
            # AniList answers 404 for an id that does not exist; that is not an outage
            if exc.response.status_code == 404:
                return None
            raise
        except RateLimited as exc:
            return self._stale_or_raise(cache_key, exc.retry_after)

        for err in payload.get("errors") or []:
            print(f"[WARNING] AniList GraphQL Error: {err.get('message')}")

        media = (payload.get("data") or {}).get("Media")
        if not media or media.get("isAdult"):
            return None

        details = self._normalize_anime(media)
        self._cache_put(cache_key, details)
        return details
    
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

    print("---detail test---")
    details = client.get_anime_details(154587)   # Frieren, by AniList id
    if details:
        print(f"[{details['id']}] {details['title']} | anilist_id={details['anilist_id']} "
              f"| synopsis {len(details['synopsis'] or '')} chars")