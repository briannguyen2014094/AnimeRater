from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import initialize_database
from packages.auth.routes import router as auth_router
from packages.favorites.routes import router as favorites_router
from packages.ratings.routes import router as ratings_router
from packages.catalog.anilist_client import AniListClient, RateLimited


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="AnimeRater", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(favorites_router)
app.include_router(ratings_router)

ROOT = Path(__file__).resolve().parents[1] / "static"
app.mount("/static", StaticFiles(directory=ROOT), name="static")

anilist = AniListClient()

AnimeGenre = Literal[
    "Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", "Horror",
    "Mahou Shoujo", "Mecha", "Music", "Mystery", "Psychological", "Romance",
    "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller",
]
AnimeFormat = Literal["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC"]


def _upstream_error(exc: Exception) -> HTTPException:
    """Rate limiting is temporary rather than a gateway fault, so it gets its own status."""
    if isinstance(exc, RateLimited):
        return HTTPException(
            status_code=503,
            detail=str(exc),
            headers={"Retry-After": str(int(exc.retry_after))},
        )
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/")
def serve_home():
    return FileResponse(ROOT / "index.html")


@app.get("/api/catalog/top")
def get_top_anime_page(page: int = 1, limit: int = 12):
    try:
        result = anilist.get_top_page(page=page, limit=limit)
    except Exception as exc:
        raise _upstream_error(exc)

    return {"page": page, "data": result["data"], "has_next_page": result["has_next_page"]}


@app.get("/api/catalog/search")
def search_anime(
    q: str = Query("", description="Title text to search for"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=50),
    genre: AnimeGenre | None = None,
    year: int | None = Query(None, ge=1900, le=9998, description="First release year"),
    media_format: AnimeFormat | None = Query(None, alias="format"),
):
    try:
        result = anilist.get_search_page(
            q, page=page, limit=limit, genre=genre, year=year, media_format=media_format,
        )
    except Exception as exc:
        raise _upstream_error(exc)

    return {"query": q, "page": page, "data": result["data"], "has_next_page": result["has_next_page"]}


@app.get("/api/catalog/anime/{anime_id}")
def get_anime_details(anime_id: int):
    """One anime in full, including the synopsis the list endpoints leave out.

    anime_id is the AniList id, which the list payloads expose as anilist_id.
    """
    try:
        details = anilist.get_anime_details(anime_id)
    except Exception as exc:
        raise _upstream_error(exc)

    if details is None:
        raise HTTPException(status_code=404, detail=f"No anime with AniList id {anime_id}")

    return details
