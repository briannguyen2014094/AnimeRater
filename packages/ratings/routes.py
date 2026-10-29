"""The session determines whose rating is read or changed."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from packages.auth.routes import get_current_user, get_database, protect_auth_requests
from packages.ratings import service
from packages.ratings.models import PersonalRating, RatingRequest
from packages.catalog.anilist_client import AniListClient, RateLimited


router = APIRouter(
    prefix="/api/ratings", tags=["Ratings"],
    dependencies=[Depends(protect_auth_requests)],
)
AnimeId = Annotated[int, Path(gt=0, le=9007199254740991)]
anilist = AniListClient()


@router.get("")
def list_ratings(user=Depends(get_current_user), connection=Depends(get_database)):
    return {"data": service.list_ratings(connection, user["id"])}


@router.get("/library")
def ratings_library(user=Depends(get_current_user), connection=Depends(get_database)):
    ratings = service.list_ratings(connection, user["id"])
    try:
        details = anilist.get_anime_by_ids([row["anime_id"] for row in ratings])
    except RateLimited as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": str(int(exc.retry_after))}) from exc
    except Exception as exc:
        raise HTTPException(502, "Couldn't load rated anime from AniList. Please try again.") from exc
    # Keep deleted or unavailable anime editable so their ratings can still be removed.
    return {"data": [dict(details.get(row["anime_id"]) or {
        "id": row["anime_id"], "anilist_id": row["anime_id"],
        "title": f"Unavailable anime #{row['anime_id']}", "unresolved": True,
    }, rating=row["rating"]) for row in ratings]}


@router.get("/{anime_id}", response_model=PersonalRating)
def get_rating(anime_id: AnimeId, user=Depends(get_current_user), connection=Depends(get_database)):
    return {"anime_id": anime_id, "rating": service.get_rating(connection, user["id"], anime_id)}


@router.put("/{anime_id}", response_model=PersonalRating)
def save_rating(anime_id: AnimeId, body: RatingRequest, user=Depends(get_current_user), connection=Depends(get_database)):
    service.save_rating(connection, user["id"], anime_id, body.rating)
    return {"anime_id": anime_id, "rating": body.rating}


@router.delete("/{anime_id}", status_code=204)
def delete_rating(anime_id: AnimeId, user=Depends(get_current_user), connection=Depends(get_database)):
    service.delete_rating(connection, user["id"], anime_id)
