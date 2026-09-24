import re
import httpx
from typing import Any

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


class AniListClient:
    def __init__(self):
        self.client = httpx.Client(
            base_url=ANILIST_GRAPHQL_URL,
            headers=DEFAULT_HEADERS,
        )
        self._anime_cache = {} # implement a cache in the future so we don't exhaust rate limits
    
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
            
    def get_top_anime(self, page: int = 1, limit: int = 15) -> list[dict[str, Any]]:
        variables = {"page": page, "perPage": limit}
        payload = self._post(TOP_ANIME_QUERY, variables)
        return self._normalize_payload(payload, func=self.get_top_anime)
    
if __name__ == "__main__":
    # debugging
    client = AniListClient()
    
    print("---top anime test---")
    top_anime = client.get_top_anime(page=1)
    # anime dict keys -> dict_keys(['id', 'title', 'synopsis', 'episodes', 'score', 'image_url', 'genres'])
    for anime in top_anime:
        print(f"[{anime['id']}] {anime['title']} | Score: {anime['score']} | Episodes: {anime['episodes']}")
                