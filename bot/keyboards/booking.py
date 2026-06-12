from datetime import date, time
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove



def dates_keyboard(dates: list[date]) -> ReplyKeyboardMarkup:
    """Одна дата — одна кнопка. Формат: 'Пн, 05 мая'."""
    WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    MONTHS = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    rows = [
        [KeyboardButton(text=f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month]}")]
        for d in dates
    ]
    rows.append([KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def times_keyboard(slots: list[time]) -> ReplyKeyboardMarkup:
    """Слоты по два в ряд. Формат: '10:00'."""
    buttons = [KeyboardButton(text=s.strftime("%H:%M")) for s in slots]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записаться")],
            [KeyboardButton(text="📋 Мои записи")],
        ],
        resize_keyboard=True,
    )