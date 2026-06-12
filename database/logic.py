from __future__ import annotations

import sqlite3
from datetime import date, time, datetime, timedelta
from typing import Optional

from database.db import get_connection

SESSION_DURATION = timedelta(minutes=60)
BREAK_DURATION   = timedelta(minutes=30)
SLOT_BLOCK       = SESSION_DURATION + BREAK_DURATION


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
    """
    Создаёт пользователя или обновляет данные при повторном /start.
    phone не перезаписывается, если уже есть — используем COALESCE.
    """
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

def get_booking_by_id(booking_id: int) -> Optional[sqlite3.Row]:
    """Возвращает запись с данными пользователя или None."""
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

def get_user(user_id: int) -> Optional[sqlite3.Row]:
    """Возвращает строку пользователя или None, если не найден."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        
def get_user_bookings(user_id: int) -> list[sqlite3.Row]:
    """Активные записи пользователя, отсортированные по дате и времени."""
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
# ─── schedule setup ───────────────────────────────────────────────────────────

DEFAULT_SCHEDULE: dict[int, tuple[str, str, bool]] = {
    0: ("10:00", "20:00", True),   # Пн
    1: ("10:00", "20:00", True),   # Вт
    2: ("10:00", "20:00", True),   # Ср
    3: ("10:00", "20:00", True),   # Чт
    4: ("10:00", "20:00", True),   # Пт
    5: ("10:00", "20:00", False),  # Сб — выходной
    6: ("10:00", "20:00", False),  # Вс — выходной
}

def seed_default_schedule(overwrite: bool = False) -> None:
    """
    Заполняет work_schedule_template дефолтным графиком.
    При overwrite=False пропускает строки, которые уже существуют.
    """
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


# ─── working hours ────────────────────────────────────────────────────────────

def get_working_hours(d: date) -> Optional[tuple[time, time]]:
    """
    Приоритет: work_exceptions → vacations → weekly template
    """
    with get_connection() as conn:
        # 1. Исключения
        exc = conn.execute(
            "SELECT is_day_off, start_time, end_time FROM work_exceptions WHERE date = ?",
            (d.isoformat(),),
        ).fetchone()
        if exc:
            if exc["is_day_off"]:
                return None
            return _time_from_str(exc["start_time"]), _time_from_str(exc["end_time"])

        # 2. Отпуск
        vac = conn.execute(
            "SELECT id FROM vacations WHERE date_from <= ? AND date_to >= ?",
            (d.isoformat(), d.isoformat()),
        ).fetchone()
        if vac:
            return None

        # 3. Шаблон недели
        tpl = conn.execute(
            "SELECT is_working_day, start_time, end_time FROM work_schedule_template WHERE weekday = ?",
            (d.weekday(),),
        ).fetchone()
        if not tpl or not tpl["is_working_day"]:
            return None

        return _time_from_str(tpl["start_time"]), _time_from_str(tpl["end_time"])


# ─── bookings for day ─────────────────────────────────────────────────────────

def get_bookings_for_day(d: date) -> list[sqlite3.Row]:
    """Все активные/подтверждённые записи на дату, отсортированные по времени."""
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


# ─── slot availability ────────────────────────────────────────────────────────

def is_time_slot_available(d: date, start: time, end: time) -> bool:
    """
    Проверяет, свободен ли интервал [start, end) с учётом 30-минутного перерыва
    после каждой существующей записи.
    """
    slot_start = _to_dt(d, start)
    slot_end   = _to_dt(d, end)

    for booking in get_bookings_for_day(d):
        b_start         = _to_dt(d, _time_from_str(booking["start_time"]))
        b_blocked_until = _to_dt(d, _time_from_str(booking["end_time"])) + BREAK_DURATION

        if slot_start < b_blocked_until and slot_end > b_start:
            return False

    return True


# ─── slot generation ──────────────────────────────────────────────────────────

def generate_available_slots(d: date) -> list[time]:
    """
    Возвращает список доступных start_time для записи.

    Алгоритм:
      1. Получить рабочие часы.
      2. Построить заблокированные интервалы: [b_start, b_end + break).
      3. Вычислить свободные окна внутри рабочего времени.
      4. В каждом окне уложить слоты плотно (без фиксированной сетки).
    """
def generate_available_slots(d: date) -> list[time]:
    hours = get_working_hours(d)
    if hours is None:
        return []

    work_start, work_end = hours
    day_start = _to_dt(d, work_start)
    day_end = _to_dt(d, work_end)

    # Если дата сегодня — не показываем слоты, которые уже прошли
    if d == date.today():
        now = datetime.now()
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

    # Свободные окна = рабочее время минус заблокированные интервалы
    free_windows: list[tuple[datetime, datetime]] = []
    cursor = day_start

    for b_start, b_end in blocked:
        if cursor < b_start:
            free_windows.append((cursor, b_start))
        cursor = max(cursor, b_end)

    if cursor < day_end:
        free_windows.append((cursor, day_end))

    # Плотная укладка слотов внутри каждого окна
    available: list[time] = []
    for window_start, window_end in free_windows:
        slot = window_start
        while slot + SESSION_DURATION <= window_end:
            available.append(slot.time())
            slot += SESSION_DURATION

    return available


# ─── create booking ───────────────────────────────────────────────────────────

def create_booking(user_id: int, d: date, start: time) -> int:
    """
    Создаёт запись для пользователя.
    Возвращает id новой записи.

    Защита от race condition: BEGIN EXCLUSIVE делает проверку + INSERT атомарными.
    Raises:
        ValueError — слот недоступен или вне рабочих часов.
    """
    end = (datetime.combine(d, start) + SESSION_DURATION).time()

    conn = get_connection()
    try:
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


# ─── cancel booking ───────────────────────────────────────────────────────────

def cancel_booking(booking_id: int) -> None:
    """
    Удаляет запись по id.
    Слот становится доступным немедленно.
    Raises:
        ValueError — запись не найдена.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM bookings WHERE id = ?",
            (booking_id,),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Запись #{booking_id} не найдена.")


# ─── reminders ────────────────────────────────────────────────────────────────

def get_bookings_pending_reminder(
    delta: timedelta,
    field: str,
) -> list[sqlite3.Row]:
    ALLOWED_FIELDS = {"reminder_24h_sent", "reminder_2h_sent"}
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Недопустимое поле: {field}")

    now    = datetime.now()
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


def confirm_booking(booking_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE bookings SET status = 'confirmed' WHERE id = ?",
            (booking_id,),
        )


def mark_reminder_sent(booking_id: int, field: str) -> None:
    """
    Помечает флаг напоминания как отправленный.
    Вызывать сразу после успешной отправки уведомления.
    """
    ALLOWED_FIELDS = {"reminder_2h_sent", "reminder_1h_sent"}
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Недопустимое поле: {field}. Допустимые: {ALLOWED_FIELDS}")

    with get_connection() as conn:
        conn.execute(
            f"UPDATE bookings SET {field} = 1 WHERE id = ?",
            (booking_id,),
        )
# ─── available dates ──────────────────────────────────────────────────────────

SCHEDULE_HORIZON_MONTHS = 3


def get_available_dates(from_date: Optional[date] = None) -> list[date]:
    """
    Возвращает доступные даты на 3 месяца вперёд.
    """
    start = from_date or date.today()
    # конец периода — последний день третьего следующего месяца
    month = start.month + 3
    year  = start.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    result: list[date] = []
    current = start
    while current <= end:
        if generate_available_slots(current):
            result.append(current)
        current += timedelta(days=1)
    return result

# ─── vacations ────────────────────────────────────────────────────────────────

def add_vacation(start: date, end: date) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO vacations (date_from, date_to) VALUES (?, ?)",
            (start.isoformat(), end.isoformat()),
        )

def add_days_off(dates: list[str]) -> None:
    """Помечает список дат (ISO-строки) как выходные через work_exceptions."""
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


# ─── update phone ─────────────────────────────────────────────────────────────

def update_user_phone(user_id: int, phone: str) -> None:
    """
    Сохраняет номер телефона пользователя после получения через contact-кнопку.
    Raises:
        ValueError — пользователь не найден.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?",
            (phone, user_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Пользователь {user_id} не найден.")