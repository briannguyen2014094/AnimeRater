import httpx
from typing import Any

BASE_URL = "https://api.jikan.moe/v4"
DEFAULT_HEADERS = {
    "User-Agent": "AnimeRaterApp"
}


class JikanClient:
    def __init__(self):
        self.client = httpx.Client(
            base_url=BASE_URL,
            headers=DEFAULT_HEADERS,
        )
    
    @staticmethod
    def _normalize_anime(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw.get("mal_id"),
            "title": raw.get("title"),
            "synopsis": raw.get("synopsis"),
            "episodes": raw.get("episodes"),
            "score": raw.get("score"),
            "image_url": raw.get("images", {}).get("jpg", {}).get("large_image_url"),
            "genres": [g["name"] for g in raw.get("genres", [])],
        }
        
    @staticmethod
    def _verify_payload(payload: dict) -> bool:
        if len(payload.get("data", [])) > 0: return True
            
        status = payload["status"]
        status_type = payload["type"]
        message = payload["message"]
            
        print(f"[WARNING] Status Code {status} ({status_type}): {message}")
        return False
        
    def _normalize_payload(self, payload: dict) -> list[dict[str, str]] | None:
        if not self._verify_payload(payload): return
        return [self._normalize_anime(item) for item in payload.get("data", [])]
        
    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            response = self.client.get(endpoint, params=params)
            return response.json()
            
    
    def get_top_anime(self, page: int = 1, limit: int = 25) -> list[dict[str, Any]]:
        params = {"page": page, "limit": limit}
        payload = self._get("/top/anime", params=params)

        return self._normalize_payload(payload)
    
    def search_anime(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        params = {
            "q": query, 
            "limit": limit}
        payload = self._get("/anime", params=params)
        return self._normalize_payload(payload)

if __name__ == "__main__":
    # debugging
    client = JikanClient()
    
    print("---top anime test---")
    top_anime = client.get_top_anime(page=1)
    for anime in top_anime:
        print(f"[{anime['id']}] {anime['title']} | Score: {anime['score']} | Episodes: {anime['episodes']}")
    
    print("\n\n---search test---")
    query = "Naruto"
    results = client.search_anime(query)
    if results: 
        for anime in results:
            print(f"[{anime['id']}] {anime['title']} | Score: {anime['score']} | Episodes: {anime['episodes']}")
                