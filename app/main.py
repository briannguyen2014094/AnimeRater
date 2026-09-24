from pathlib import Path
from fastapi import FastAPI, HTTPException
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