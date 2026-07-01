from __future__ import annotations

import calendar
import sqlite3
from datetime import date, time, datetime, timedelta, timezone
from typing import Optional

from database.db import get_connection

SESSION_DURATION = timedelta(minutes=60)
BREAK_DURATION   = timedelta(minutes=30)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _to_dt(d: date, t: time) -> datetime:
    return datetime.combine(d, t)


def _time_from_str(s: str) -> time:
    return time.fromisoformat(s)


# ─── users ───────────────────────────────────────────────────────────────────

def upsert_user(
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    phone: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, phone)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                phone      = COALESCE(users.phone, excluded.phone)
            """,
            (user_id, username, first_name, last_name, phone),
        )


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def get_user_bookings(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, date, start_time, end_time, status
            FROM bookings
            WHERE user_id = ? AND status IN ('active', 'confirmed')
            ORDER BY date, start_time
            """,
            (user_id,),
        ).fetchall()


def update_user_phone(user_id: int, phone: str) -> None:
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?",
            (phone, user_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Пользователь {user_id} не найден.")


# ─── bookings ────────────────────────────────────────────────────────────────

def get_booking_by_id(booking_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT b.id, b.date, b.start_time, b.end_time, b.status,
                   u.user_id, u.first_name, u.last_name, u.phone, u.username
            FROM bookings b
            JOIN users u ON u.user_id = b.user_id
            WHERE b.id = ?
            """,
            (booking_id,),
        ).fetchone()


def get_bookings_for_day(d: date) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, user_id, date, start_time, end_time, status
            FROM bookings
            WHERE date = ? AND status IN ('active', 'confirmed')
            ORDER BY start_time
            """,
            (d.isoformat(),),
        ).fetchall()


def create_booking(user_id: int, d: date, start: time) -> int:
    end = (datetime.combine(d, start) + SESSION_DURATION).time()

    # Убеждаемся что пользователь существует в БД
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,),
        )

    conn = get_connection()
    try:
        # ... остальной код без изменений
        conn.execute("BEGIN EXCLUSIVE")

        working = get_working_hours(d)
        if working is None:
            raise ValueError(f"{d.isoformat()} не является рабочим днём.")

        work_start, work_end = working
        if start < work_start or end > work_end:
            raise ValueError("Слот выходит за пределы рабочего времени.")

        rows = conn.execute(
            """
            SELECT start_time, end_time FROM bookings
            WHERE date = ? AND status IN ('active', 'confirmed')
            """,
            (d.isoformat(),),
        ).fetchall()

        slot_start = _to_dt(d, start)
        slot_end   = _to_dt(d, end)

        for row in rows:
            b_start         = _to_dt(d, _time_from_str(row["start_time"]))
            b_blocked_until = _to_dt(d, _time_from_str(row["end_time"])) + BREAK_DURATION
            if slot_start < b_blocked_until and slot_end > b_start:
                raise ValueError("Слот уже занят.")

        cursor = conn.execute(
            """
            INSERT INTO bookings (user_id, date, start_time, end_time, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (user_id, d.isoformat(), start.isoformat(), end.isoformat()),
        )
        booking_id = cursor.lastrowid
        conn.commit()
        return booking_id

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cancel_booking(booking_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM bookings WHERE id = ?",
            (booking_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Запись #{booking_id} не найдена.")


def confirm_booking(booking_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE bookings SET status = 'confirmed' WHERE id = ?",
            (booking_id,),
        )


# ─── reminders ────────────────────────────────────────────────────────────────

def get_bookings_pending_reminder(delta: timedelta, field: str) -> list[sqlite3.Row]:
    ALLOWED_FIELDS = {"reminder_24h_sent", "reminder_2h_sent"}
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Недопустимое поле: {field}")

    MSK = timezone(timedelta(hours=3))
    now    = datetime.now(MSK).replace(tzinfo=None)
    target = now + delta
    window = timedelta(minutes=1)

    target_date = target.date().isoformat()
    time_lo = (datetime.combine(target.date(), target.time()) - window).time().isoformat()
    time_hi = (datetime.combine(target.date(), target.time()) + window).time().isoformat()

    with get_connection() as conn:
        return conn.execute(
            f"""
            SELECT b.id, b.user_id, b.date, b.start_time, b.end_time, b.status,
                   u.username, u.first_name, u.phone
            FROM bookings b
            JOIN users u ON u.user_id = b.user_id
            WHERE b.date        = ?
              AND b.start_time >= ?
              AND b.start_time <  ?
              AND b.status IN ('active', 'confirmed')
              AND b.{field} = 0
            """,
            (target_date, time_lo, time_hi),
        ).fetchall()


def mark_reminder_sent(booking_id: int, field: str) -> None:
    ALLOWED_FIELDS = {"reminder_24h_sent", "reminder_2h_sent"}
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Недопустимое поле: {field}")
    with get_connection() as conn:
        conn.execute(
            f"UPDATE bookings SET {field} = 1 WHERE id = ?",
            (booking_id,),
        )


# ─── schedule ─────────────────────────────────────────────────────────────────

DEFAULT_SCHEDULE: dict[int, tuple[str, str, bool]] = {
    0: ("10:00", "20:00", True),
    1: ("10:00", "20:00", True),
    2: ("10:00", "20:00", True),
    3: ("10:00", "20:00", True),
    4: ("10:00", "20:00", True),
    5: ("10:00", "20:00", False),
    6: ("10:00", "20:00", False),
}


def seed_default_schedule(overwrite: bool = False) -> None:
    with get_connection() as conn:
        for weekday, (start, end, is_working) in DEFAULT_SCHEDULE.items():
            if overwrite:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO work_schedule_template
                        (weekday, start_time, end_time, is_working_day)
                    VALUES (?, ?, ?, ?)
                    """,
                    (weekday, start, end, int(is_working)),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO work_schedule_template
                        (weekday, start_time, end_time, is_working_day)
                    VALUES (?, ?, ?, ?)
                    """,
                    (weekday, start, end, int(is_working)),
                )


def get_working_hours(d: date) -> Optional[tuple[time, time]]:
    """
    Приоритет: work_exceptions → vacations → weekly template
    """
    with get_connection() as conn:
        exc = conn.execute(
            "SELECT is_day_off, start_time, end_time FROM work_exceptions WHERE date = ?",
            (d.isoformat(),),
        ).fetchone()
        if exc:
            if exc["is_day_off"]:
                return None
            return _time_from_str(exc["start_time"]), _time_from_str(exc["end_time"])

        vac = conn.execute(
            "SELECT id FROM vacations WHERE date_from <= ? AND date_to >= ?",
            (d.isoformat(), d.isoformat()),
        ).fetchone()
        if vac:
            return None

        tpl = conn.execute(
            """
            SELECT is_working_day, start_time, end_time
            FROM work_schedule_template WHERE weekday = ?
            """,
            (d.weekday(),),
        ).fetchone()
        if not tpl or not tpl["is_working_day"]:
            return None

        return _time_from_str(tpl["start_time"]), _time_from_str(tpl["end_time"])


# ─── slot generation ──────────────────────────────────────────────────────────

def generate_available_slots(d: date) -> list[time]:
    hours = get_working_hours(d)
    if hours is None:
        return []

    work_start, work_end = hours
    day_start = _to_dt(d, work_start)
    day_end = _to_dt(d, work_end)

    if d == date.today():
        from datetime import timezone, timedelta

        MSK = timezone(timedelta(hours=3))
        now = datetime.now(MSK).replace(tzinfo=None)

        if day_start < now:
            day_start = now + timedelta(minutes=30)

    if day_end - day_start < SESSION_DURATION:
        return []

    bookings = get_bookings_for_day(d)

    blocked: list[tuple[datetime, datetime]] = sorted(
        (
            _to_dt(d, _time_from_str(b["start_time"])),
            _to_dt(d, _time_from_str(b["end_time"])) + BREAK_DURATION,
        )
        for b in bookings
    )

    free_windows: list[tuple[datetime, datetime]] = []
    cursor = day_start

    for b_start, b_end in blocked:
        if cursor < b_start:
            free_windows.append((cursor, b_start))
        cursor = max(cursor, b_end)

    if cursor < day_end:
        free_windows.append((cursor, day_end))

    available: list[time] = []

    for window_start, window_end in free_windows:
        slot = window_start
        while slot + SESSION_DURATION <= window_end:
            available.append(slot.time())
            slot += SESSION_DURATION

    return available


# ─── available dates ──────────────────────────────────────────────────────────

SCHEDULE_HORIZON_MONTHS = 3  # было 3

def get_available_dates(from_date: Optional[date] = None) -> list[date]:
    start = from_date or date.today()
    month = start.month + SCHEDULE_HORIZON_MONTHS
    year  = start.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    result: list[date] = []
    current = start
    while current <= end:
        if generate_available_slots(current):
            result.append(current)
        current += timedelta(days=1)
    return result


# ─── exceptions & vacations ───────────────────────────────────────────────────

def add_days_off(dates: list[str]) -> None:
    with get_connection() as conn:
        for date_str in dates:
            conn.execute(
                """
                INSERT INTO work_exceptions (date, is_day_off, start_time, end_time)
                VALUES (?, 1, NULL, NULL)
                ON CONFLICT(date) DO UPDATE SET
                    is_day_off = 1,
                    start_time = NULL,
                    end_time   = NULL
                """,
                (date_str,),
            )


def delete_days_off(dates: list[str]) -> None:
    with get_connection() as conn:
        for date_str in dates:
            conn.execute(
                "DELETE FROM work_exceptions WHERE date = ?",
                (date_str,),
            )


def add_exception(
    d: date,
    is_day_off: bool,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO work_exceptions (date, is_day_off, start_time, end_time)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                is_day_off = excluded.is_day_off,
                start_time = excluded.start_time,
                end_time   = excluded.end_time
            """,
            (d.isoformat(), int(is_day_off), start_time, end_time),
        )


def get_exceptions(from_date: Optional[date] = None) -> list:
    """
    Возвращает все выходные дни — из work_exceptions и из vacations.
    Объединяет в единый список для отображения в админке.
    """
    d = (from_date or date.today()).isoformat()

    with get_connection() as conn:
        # Из work_exceptions
        exc_rows = conn.execute(
            "SELECT date, is_day_off, start_time, end_time FROM work_exceptions WHERE date >= ? ORDER BY date",
            (d,),
        ).fetchall()

        # Из vacations — разворачиваем диапазоны в отдельные дни
        vac_rows = conn.execute(
            "SELECT date_from, date_to FROM vacations WHERE date_to >= ? ORDER BY date_from",
            (d,),
        ).fetchall()

    # Даты уже покрытые work_exceptions
    exc_dates = {row["date"] for row in exc_rows}

    # Добавляем дни из vacations которых нет в work_exceptions
    extra: list[dict] = []
    for vac in vac_rows:
        current = date.fromisoformat(vac["date_from"])
        end_v   = date.fromisoformat(vac["date_to"])
        while current <= end_v:
            if current.isoformat() >= d and current.isoformat() not in exc_dates:
                extra.append({
                    "date": current.isoformat(),
                    "is_day_off": 1,
                    "start_time": None,
                    "end_time": None,
                    "source": "vacation",
                })
            current += timedelta(days=1)

    # Объединяем и сортируем
    combined = list(exc_rows) + extra
    combined.sort(key=lambda x: x["date"] if isinstance(x, dict) else x["date"])
    return combined


def delete_exception(d: date) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM work_exceptions WHERE date = ?", (d.isoformat(),))


def add_vacation(start: date, end: date) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO vacations (date_from, date_to) VALUES (?, ?)",
            (start.isoformat(), end.isoformat()),
        )


def get_vacations() -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, date_from, date_to FROM vacations ORDER BY date_from"
        ).fetchall()


def delete_vacation(vacation_id: int) -> None:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM vacations WHERE id = ?", (vacation_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Отпуск #{vacation_id} не найден.")