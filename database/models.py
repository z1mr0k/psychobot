from database.db import get_connection


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                last_name  TEXT,
                phone      TEXT
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL REFERENCES users(user_id),
                date                TEXT NOT NULL,
                start_time          TEXT NOT NULL,
                end_time            TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'active'
                                        CHECK(status IN ('active', 'confirmed')),
                reminder_24h_sent   INTEGER NOT NULL DEFAULT 0,
                reminder_2h_sent    INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS work_schedule_template (
                weekday        INTEGER PRIMARY KEY CHECK(weekday BETWEEN 0 AND 6),
                start_time     TEXT NOT NULL,
                end_time       TEXT NOT NULL,
                is_working_day INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS work_exceptions (
                date       TEXT PRIMARY KEY,
                is_day_off INTEGER NOT NULL DEFAULT 0,
                start_time TEXT,
                end_time   TEXT
            );

            CREATE TABLE IF NOT EXISTS vacations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                date_from TEXT NOT NULL,
                date_to   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_bookings_date
                ON bookings(date);

            CREATE INDEX IF NOT EXISTS idx_bookings_user_date
                ON bookings(user_id, date);

            CREATE INDEX IF NOT EXISTS idx_bookings_date_status
                ON bookings(date, status);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_slot
                ON bookings(date, start_time)
                WHERE status IN ('active', 'confirmed');
        """)