"""Personal ratings use whole numbers, without coercing strings or booleans."""

from pydantic import BaseModel, Field


class RatingRequest(BaseModel):
    rating: int = Field(strict=True, ge=1, le=10)


class PersonalRating(BaseModel):
    anime_id: int
    rating: int | None
