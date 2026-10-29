"""HTTP endpoints; password and session logic lives in service.py."""

import os
import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from app.database import get_connection
from packages.auth import service
from packages.auth.mail import reset_mail_settings, send_password_reset
from packages.auth.models import (
    ForgotPasswordRequest, LoginRequest, PublicUser, RecoveryEmailRequest,
    RegisterRequest, ResetPasswordRequest,
)


COOKIE_NAME = "animerater_session"


def get_database():
    with get_connection() as connection:
        yield connection


def protect_auth_requests(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    # A cross-origin HTML form cannot supply this header. Keep CORS disabled;
    # allowing untrusted origins to send this header would weaken this protection.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("X-Requested-With") != "AnimeRater":
        raise HTTPException(status_code=403, detail="X-Requested-With: AnimeRater is required")


router = APIRouter(
    prefix="/api/auth", tags=["Authentication"],
    dependencies=[Depends(protect_auth_requests)],
)


@router.post("/register", response_model=PublicUser, status_code=201)
def register(body: RegisterRequest, connection=Depends(get_database)):
    try:
        return service.register_user(connection, body.username, body.password.get_secret_value(), body.email)
    except sqlite3.IntegrityError as exc:
        existing = connection.execute(
            "SELECT id FROM users WHERE username = ?", (body.username,),
        ).fetchone()
        if existing is None:
            raise
        raise HTTPException(status_code=409, detail="Username is already taken") from exc


@router.post("/login", response_model=PublicUser)
def login(body: LoginRequest, request: Request, response: Response, connection=Depends(get_database)):
    user = service.authenticate_user(connection, body.username, body.password.get_secret_value())
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = service.create_session(connection, user["id"], request.cookies.get(COOKIE_NAME))
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=service.SESSION_SECONDS,
        httponly=True, samesite="lax", path="/",
        # HTTPS is required by default. Disable only for local HTTP development.
        secure=os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false",
    )
    return user


def get_current_user(request: Request, connection=Depends(get_database)):
    """Other protected routes can reuse this with Depends(get_current_user)."""
    user = service.get_session_user(connection, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in")
    return user


@router.get("/me", response_model=PublicUser)
def me(user=Depends(get_current_user)):
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, connection=Depends(get_database)):
    service.delete_session(connection, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")


@router.post("/recovery-email", status_code=204)
def recovery_email(body: RecoveryEmailRequest, user=Depends(get_current_user), connection=Depends(get_database)):
    if service.authenticate_user(connection, user["username"], body.password.get_secret_value()) is None:
        raise HTTPException(status_code=401, detail="Incorrect password")
    connection.execute("UPDATE users SET email = ? WHERE id = ?", (body.email, user["id"]))
    connection.execute("DELETE FROM password_resets WHERE user_id = ?", (user["id"],))


@router.post("/forgot-password", status_code=202)
def forgot_password(body: ForgotPasswordRequest, background_tasks: BackgroundTasks, connection=Depends(get_database)):
    try:
        reset_mail_settings()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Password recovery email is not configured. Please contact the site administrator.") from exc
    reset = service.create_password_reset(connection, body.username)
    if reset:
        # Commit before scheduling delivery; the emailed token must already exist.
        connection.commit()
        background_tasks.add_task(send_password_reset, *reset)
    return {"message": "If this account has a recovery email, a reset link will be sent. Check your inbox and spam folder."}


@router.post("/reset-password", status_code=204)
def reset_password(body: ResetPasswordRequest, response: Response, connection=Depends(get_database)):
    if not service.reset_password(connection, body.token.get_secret_value(), body.password.get_secret_value()):
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired. Request a new link.")
    response.delete_cookie(COOKIE_NAME, path="/")
