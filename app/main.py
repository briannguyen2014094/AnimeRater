from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from packages.catalog.anilist_client import AniListClient

app = FastAPI(title="AnimeRater")

ROOT = Path(__file__).resolve().parents[1] / "static"
app.mount("/static", StaticFiles(directory=ROOT), name="static")

anilist = AniListClient()


@app.get("/")
def serve_home():
    return FileResponse(ROOT / "index.html")


@app.get("/api/catalog/top")
def get_top_anime_page(page: int = 1, limit: int = 12):
    try:
        return {"page": page, "data": anilist.get_top_anime(page=page, limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/catalog/search")
def search_anime(
    q: str = Query("", description="Title text to search for"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=50),
):
    # A blank query is not an error; it just has nothing to search for.
    if not q.strip():
        return {"query": q, "page": page, "data": []}

    try:
        results = anilist.search_anime(q, page=page, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"query": q, "page": page, "data": results}


@app.get("/api/catalog/anime/{anime_id}")
def get_anime_details(anime_id: int):
    """One anime in full, including the synopsis the list endpoints leave out.

    anime_id is the AniList id, which the list payloads expose as anilist_id.
    """
    try:
        details = anilist.get_anime_details(anime_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if details is None:
        raise HTTPException(status_code=404, detail=f"No anime with AniList id {anime_id}")

    return details