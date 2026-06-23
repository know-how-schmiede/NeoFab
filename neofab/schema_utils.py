from __future__ import annotations

from sqlalchemy import text

from models import db


def ensure_order_id_sequence_table() -> None:
    """
    Maintain a monotonic order id sequence independent of SQLite rowid reuse.
    Existing installations are initialized to the current maximum order id.
    """
    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS order_id_sequence (
                name VARCHAR(50) PRIMARY KEY,
                last_id INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    )
    max_order_id = db.session.execute(text("SELECT COALESCE(MAX(id), 0) FROM orders")).scalar() or 0
    db.session.execute(
        text(
            """
            INSERT INTO order_id_sequence (name, last_id)
            VALUES ('orders', :max_order_id)
            ON CONFLICT(name) DO UPDATE SET
                last_id = CASE
                    WHEN order_id_sequence.last_id < excluded.last_id THEN excluded.last_id
                    ELSE order_id_sequence.last_id
                END
            """
        ),
        {"max_order_id": int(max_order_id)},
    )
    db.session.commit()


def reserve_next_order_id() -> int:
    """
    Reserve the next order id. The caller commits it together with the order.
    """
    db.session.execute(
        text("UPDATE order_id_sequence SET last_id = last_id + 1 WHERE name = 'orders'")
    )
    next_id = db.session.execute(
        text("SELECT last_id FROM order_id_sequence WHERE name = 'orders'")
    ).scalar()
    if next_id is None:
        ensure_order_id_sequence_table()
        return reserve_next_order_id()
    return int(next_id)


def reset_order_id_sequence() -> None:
    """
    Reset order ids after every order has been deleted.
    """
    remaining_orders = db.session.execute(text("SELECT COUNT(*) FROM orders")).scalar() or 0
    if int(remaining_orders) != 0:
        raise ValueError("Cannot reset order id sequence while orders still exist.")
    db.session.execute(
        text(
            """
            INSERT INTO order_id_sequence (name, last_id)
            VALUES ('orders', 0)
            ON CONFLICT(name) DO UPDATE SET last_id = 0
            """
        )
    )


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
