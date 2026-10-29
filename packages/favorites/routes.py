"""Favorites belong to the authenticated user, never a caller-supplied user ID."""

import json

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from packages.auth.routes import get_current_user, get_database, protect_auth_requests


class Favorite(BaseModel):
    id: int = Field(gt=0, le=9007199254740991)
    anilist_id: int | None = Field(default=None, gt=0, le=9007199254740991)
    title: str = Field(min_length=1, max_length=1000)
    image_url: str = Field(default="", max_length=2048)
    score: float | None = Field(default=None, ge=0, le=10)
    episodes: int | None = Field(default=None, ge=0)
    genres: list[str] = Field(default_factory=list, max_length=100)
    synopsis: str = Field(default="", max_length=50000)


router = APIRouter(
    prefix="/api/favorites", tags=["Favorites"],
    dependencies=[Depends(protect_auth_requests)],
)


@router.get("")
def list_favorites(user=Depends(get_current_user), connection=Depends(get_database)):
    rows = connection.execute(
        "SELECT anime_id, details FROM favorites WHERE user_id = ? ORDER BY created_at, anime_id",
        (user["id"],),
    ).fetchall()
    return {"data": [dict(json.loads(row["details"]), id=row["anime_id"]) for row in rows]}


@router.post("", status_code=204)
def save_favorite(body: Favorite, user=Depends(get_current_user), connection=Depends(get_database)):
    connection.execute(
        """INSERT INTO favorites (user_id, anime_id, details) VALUES (?, ?, ?)
        ON CONFLICT(user_id, anime_id) DO UPDATE SET details = excluded.details""",
        (user["id"], body.id, body.model_dump_json()),
    )


@router.delete("/{anime_id}", status_code=204)
def delete_favorite(anime_id: int = Path(gt=0), user=Depends(get_current_user), connection=Depends(get_database)):
    connection.execute("DELETE FROM favorites WHERE user_id = ? AND anime_id = ?", (user["id"], anime_id))
