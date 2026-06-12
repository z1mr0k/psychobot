from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def months_keyboard(available_dates: list[date]) -> InlineKeyboardMarkup:
    """3 кнопки с месяцами у которых есть свободные даты."""
    seen: dict[tuple[int, int], str] = {}
    for d in available_dates:
        key = (d.year, d.month)
        if key not in seen:
            seen[key] = f"{MONTHS_RU[d.month]} {d.year}"

    builder = InlineKeyboardBuilder()
    for (year, month), label in seen.items():
        builder.button(text=label, callback_data=f"cal_month:{year}:{month}")
    builder.button(text="❌ Отмена", callback_data="cal_cancel")
    builder.adjust(1)
    return builder.as_markup()


def days_keyboard(year: int, month: int, available_dates: list[date]) -> InlineKeyboardMarkup:
    """
    Сетка-календарь выбранного месяца.
    Доступные дни — кнопки с датой.
    Недоступные — пустые кнопки (·).
    """
    available_set = {d for d in available_dates if d.year == year and d.month == month}

    builder = InlineKeyboardBuilder()

    # Заголовок — названия дней недели
    for day_name in DAYS_RU:
        builder.button(text=day_name, callback_data="cal_ignore")

    # Сетка дней
    first_weekday, days_in_month = calendar.monthrange(year, month)
    # Пустые ячейки до первого дня
    for _ in range(first_weekday):
        builder.button(text=" ", callback_data="cal_ignore")

    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if d in available_set:
            builder.button(text=str(day), callback_data=f"cal_day:{d.isoformat()}")
        else:
            builder.button(text="·", callback_data="cal_ignore")

    builder.button(text="🔙 Назад", callback_data="cal_back")
    builder.adjust(7)
    return builder.as_markup()


def times_keyboard(slots: list, chosen_date: date) -> InlineKeyboardMarkup:
    """Слоты по 3 в ряд."""
    builder = InlineKeyboardBuilder()
    for s in slots:
        # Сохраняем только ЧЧ:ММ чтобы не ломать split(":")
        time_str = s.strftime("%H:%M")
        builder.button(
            text=time_str,
            callback_data=f"cal_time:{chosen_date.isoformat()}:{time_str}",
        )
    builder.button(text="🔙 Назад", callback_data="cal_back_to_month")
    builder.adjust(3)
    return builder.as_markup()