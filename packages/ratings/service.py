"""SQLite storage for one rating per account and anime."""


def initialize_ratings(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            anime_id INTEGER NOT NULL CHECK (anime_id > 0),
            rating INTEGER NOT NULL CHECK (typeof(rating) = 'integer' AND rating BETWEEN 1 AND 10),
            PRIMARY KEY (user_id, anime_id)
        )
    """)


def get_rating(connection, user_id, anime_id):
    row = connection.execute(
        "SELECT rating FROM ratings WHERE user_id = ? AND anime_id = ?",
        (user_id, anime_id),
    ).fetchone()
    return row["rating"] if row else None


def save_rating(connection, user_id, anime_id, rating):
    connection.execute(
        """INSERT INTO ratings (user_id, anime_id, rating) VALUES (?, ?, ?)
        ON CONFLICT(user_id, anime_id) DO UPDATE SET rating = excluded.rating""",
        (user_id, anime_id, rating),
    )


def delete_rating(connection, user_id, anime_id):
    connection.execute(
        "DELETE FROM ratings WHERE user_id = ? AND anime_id = ?", (user_id, anime_id),
    )
