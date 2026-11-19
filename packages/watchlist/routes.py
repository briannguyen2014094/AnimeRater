"""Account watchlist keyed by AniList ID, with independent status and progress."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from packages.auth.routes import get_current_user, get_database, protect_auth_requests
from packages.catalog.anilist_client import RateLimited, anilist


MAX_SAFE_INTEGER = 9007199254740991
AnimeId = Annotated[int, Path(gt=0, le=MAX_SAFE_INTEGER)]


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["plan_to_watch", "watching", "completed", "dropped"]


class ProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episodes_watched: int = Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)


router = APIRouter(
    prefix="/api/watchlist", tags=["Watchlist"],
    dependencies=[Depends(protect_auth_requests)],
)


def entry(row):
    return dict(
        json.loads(row["details"]),
        anilist_id=row["anime_id"], status=row["status"], episodes_watched=row["episodes_watched"],
        updated_at=row["updated_at"],
    )


def catalog_details(anime_id):
    try:
        details = anilist.get_anime_details(anime_id)
    except RateLimited as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": str(int(exc.retry_after))}) from exc
    except Exception as exc:
        raise HTTPException(502, "Couldn't verify this anime with AniList. Please try again.") from exc
    if details is None:
        raise HTTPException(404, "This anime is unavailable on AniList.")
    return details


def find_entry(connection, user_id, anime_id):
    return connection.execute(
        "SELECT * FROM watchlist WHERE user_id = ? AND anime_id = ?", (user_id, anime_id),
    ).fetchone()


@router.get("")
def list_watchlist(user=Depends(get_current_user), connection=Depends(get_database)):
    rows = connection.execute(
        "SELECT * FROM watchlist WHERE user_id = ? ORDER BY anime_id", (user["id"],),
    )
    return {"data": [entry(row) for row in rows]}


@router.put("/{anime_id}")
def save_status(anime_id: AnimeId, body: StatusUpdate, user=Depends(get_current_user), connection=Depends(get_database)):
    key = (user["id"], anime_id)
    existing = find_entry(connection, *key)
    details = existing["details"] if existing else json.dumps(catalog_details(anime_id))
    row = connection.execute(
        """INSERT INTO watchlist (user_id, anime_id, status, details, updated_at)
        VALUES (?, ?, ?, ?, CAST(strftime('%s','now') AS INTEGER))
        ON CONFLICT(user_id, anime_id) DO UPDATE SET
            status = excluded.status, updated_at = excluded.updated_at
        RETURNING *""",
        (*key, body.status, details),
    ).fetchone()
    return entry(row)


def save_progress(connection, user_id, anime_id, count):
    key = (user_id, anime_id)
    if find_entry(connection, *key) is None:
        raise HTTPException(404, "Add this anime to your watchlist first.")
    details = catalog_details(anime_id)
    total = details["episodes"]
    # Use one UPDATE so simultaneous increments apply to the current stored count.
    row = connection.execute(
        """UPDATE watchlist
        SET episodes_watched = COALESCE(:count, episodes_watched + 1), details = :details,
            updated_at = CAST(strftime('%s','now') AS INTEGER)
        WHERE user_id = :user_id AND anime_id = :anime_id
            AND COALESCE(:count, episodes_watched + 1) <= :limit
        RETURNING *""",
        {
            "count": count, "details": json.dumps(details), "user_id": user_id,
            "anime_id": anime_id, "limit": MAX_SAFE_INTEGER if total is None else total,
        },
    ).fetchone()
    if row is not None:
        return entry(row)
    if find_entry(connection, *key) is None:
        raise HTTPException(404, "Add this anime to your watchlist first.")
    message = "Episode count is too large." if total is None else f"Enter an episode count from 0 to {total}."
    raise HTTPException(422, message)


@router.put("/{anime_id}/progress")
def correct_progress(anime_id: AnimeId, body: ProgressUpdate, user=Depends(get_current_user), connection=Depends(get_database)):
    return save_progress(connection, user["id"], anime_id, body.episodes_watched)


@router.post("/{anime_id}/progress")
def increment_progress(anime_id: AnimeId, user=Depends(get_current_user), connection=Depends(get_database)):
    return save_progress(connection, user["id"], anime_id, None)


@router.delete("/{anime_id}", status_code=204)
def remove_entry(anime_id: AnimeId, user=Depends(get_current_user), connection=Depends(get_database)):
    connection.execute("DELETE FROM watchlist WHERE user_id = ? AND anime_id = ?", (user["id"], anime_id))
