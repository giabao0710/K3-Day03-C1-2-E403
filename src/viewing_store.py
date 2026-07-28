import sqlite3
from datetime import UTC, datetime
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent.parent / "viewing_scheduler.sqlite3"
DEFAULT_SLOTS = ("09:00", "11:00", "14:00", "16:00", "19:00")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS viewing_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                viewing_date TEXT NOT NULL,
                slot TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL,
                start_at TEXT NOT NULL,
                event_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (request_id) REFERENCES viewing_requests (request_id)
            )
            """
        )


def get_available_slots(listing_id: int, viewing_date: str) -> list[str]:
    initialize_database()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT slot
            FROM viewing_requests
            WHERE listing_id = ? AND viewing_date = ? AND status IN ('pending', 'confirmed')
            """,
            (listing_id, viewing_date),
        ).fetchall()

    reserved_slots = {str(row["slot"]) for row in rows}
    return [slot for slot in DEFAULT_SLOTS if slot not in reserved_slots]


def create_viewing_request(
    listing_id: int,
    viewing_date: str,
    slot: str,
    customer_name: str,
    customer_phone: str,
) -> int:
    initialize_database()
    created_at = datetime.now(UTC).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO viewing_requests (
                listing_id,
                viewing_date,
                slot,
                customer_name,
                customer_phone,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (listing_id, viewing_date, slot, customer_name, customer_phone, created_at),
        )
        return int(cursor.lastrowid)


def get_viewing_request(request_id: int) -> sqlite3.Row | None:
    initialize_database()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT request_id, listing_id, viewing_date, slot, customer_name, customer_phone, status
            FROM viewing_requests
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
    return row


def create_event_for_request(request_id: int, title: str, start_at: str, event_status: str) -> int:
    initialize_database()
    created_at = datetime.now(UTC).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO calendar_events (request_id, title, start_at, event_status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, title, start_at, event_status, created_at),
        )
        return int(cursor.lastrowid)


def get_calendar_event_for_request(request_id: int) -> sqlite3.Row | None:
    initialize_database()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT event_id, request_id, title, start_at, event_status
            FROM calendar_events
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
    return row
