"""Authentication logic. SQL values always use placeholders, never formatting."""

import hashlib
import secrets
import time

from pwdlib import PasswordHash


SESSION_SECONDS = 7 * 24 * 60 * 60
password_hasher = PasswordHash.recommended()
# Checking a dummy hash keeps unknown-user logins on the password-check path.
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def register_user(connection, username, password):
    password_hash = password_hasher.hash(password)
    cursor = connection.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    return {"id": cursor.lastrowid, "username": username}


def authenticate_user(connection, username, password):
    user = connection.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    stored_hash = user["password_hash"] if user else DUMMY_PASSWORD_HASH
    password_matches = password_hasher.verify(password, stored_hash)
    if not user or not password_matches:
        return None
    return {"id": user["id"], "username": user["username"]}


def hash_token(token):
    # Tokens are already random secrets; SHA-256 is suitable for their lookup hash.
    return hashlib.sha256(token.encode()).hexdigest()


def delete_session(connection, token):
    if token:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))


def create_session(connection, user_id, previous_token=None):
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    # Rotate this browser's session, while keeping other devices logged in.
    delete_session(connection, previous_token)
    connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    connection.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (hash_token(token), user_id, now + SESSION_SECONDS),
    )
    return token


def get_session_user(connection, token):
    if not token or len(token) > 128:
        return None
    user = connection.execute(
        """SELECT users.id, users.username FROM sessions
           JOIN users ON users.id = sessions.user_id
           WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
        (hash_token(token), int(time.time())),
    ).fetchone()
    return dict(user) if user else None
