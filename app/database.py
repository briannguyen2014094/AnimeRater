"""Small SQLite helpers shared by the backend. No extra packages required."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "animerater.db"


@contextmanager
def get_connection(database_path=DATABASE_PATH):
    """Open a connection, commit successful work, and always close it."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI may enter and exit one request's dependency on different threads.
    # Each request still gets its own connection; never share it across requests.
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    # SQLite requires foreign keys to be enabled on every connection.
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path=DATABASE_PATH):
    """Create missing tables without deleting existing records."""
    with get_connection(database_path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);

            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                anime_id INTEGER NOT NULL CHECK (anime_id > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, anime_id)
            );
        """)


if __name__ == "__main__":
    initialize_database()
    print(f"Database ready: {DATABASE_PATH}")
