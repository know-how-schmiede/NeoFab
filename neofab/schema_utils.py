from __future__ import annotations

from sqlalchemy import text

from models import db


def ensure_training_playlist_schema() -> None:
    """
    Ensure the training_playlists table and playlist_id column exist.
    SQLite only; safe to call multiple times.
    """
    db.create_all()

    columns = db.session.execute(text("PRAGMA table_info(training_videos)")).fetchall()
    if any(row[1] == "playlist_id" for row in columns):
        return

    db.session.execute(text("ALTER TABLE training_videos ADD COLUMN playlist_id INTEGER"))
    db.session.commit()
