"""Request and response shapes for the authentication API."""

from pydantic import BaseModel, Field, SecretStr


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    password: SecretStr = Field(min_length=1, max_length=128)


class RegisterRequest(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=128)


class PublicUser(BaseModel):
    # Password hashes and session tokens must never appear in user responses.
    id: int
    username: str
