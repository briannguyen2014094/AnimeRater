"""The session determines whose rating is read or changed."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from packages.auth.routes import get_current_user, get_database, protect_auth_requests
from packages.ratings import service
from packages.ratings.models import PersonalRating, RatingRequest


router = APIRouter(
    prefix="/api/ratings", tags=["Ratings"],
    dependencies=[Depends(protect_auth_requests)],
)
AnimeId = Annotated[int, Path(gt=0, le=9007199254740991)]


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
