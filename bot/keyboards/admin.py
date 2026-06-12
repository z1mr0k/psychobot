from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Сегодняшние записи"), KeyboardButton(text="📅 Завтра")],
            [KeyboardButton(text="📆 Все будущие записи")],
            [KeyboardButton(text="📊 Экспорт Excel")],
            [KeyboardButton(text="⚙️ Настройка расписания")],
            [KeyboardButton(text="🏖 Отпуск / выходные")],
        ],
        resize_keyboard=True,
    )


def booking_actions_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data=f"admin_edit:{booking_id}")
    builder.button(text="❌ Отменить", callback_data=f"admin_cancel:{booking_id}")
    builder.adjust(2)
    return builder.as_markup()


def edit_booking_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏪ -1 час",   callback_data=f"admin_shift:{booking_id}:-60")
    builder.button(text="◀️ -30 мин",  callback_data=f"admin_shift:{booking_id}:-30")
    builder.button(text="▶️ +30 мин",  callback_data=f"admin_shift:{booking_id}:+30")
    builder.button(text="⏩ +1 час",   callback_data=f"admin_shift:{booking_id}:+60")
    builder.button(text="➕ Продлить +30", callback_data=f"admin_extend:{booking_id}:+30")
    builder.button(text="➖ Сократить -30", callback_data=f"admin_extend:{booking_id}:-30")
    builder.button(text="❌ Отменить запись", callback_data=f"admin_cancel:{booking_id}")
    builder.button(text="🔙 Назад", callback_data="admin_back")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def export_period_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Эта неделя", callback_data="export:week")
    builder.button(text="📆 Этот месяц", callback_data="export:month")
    builder.adjust(2)
    return builder.as_markup()


def schedule_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Шаблон недели",  callback_data="schedule:template")
    builder.button(text="📌 Исключения",     callback_data="schedule:exceptions")
    builder.adjust(1)
    return builder.as_markup()


def weekdays_keyboard(template: dict) -> InlineKeyboardMarkup:
    """template: {weekday: row from work_schedule_template}"""
    DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder = InlineKeyboardBuilder()
    for i, name in enumerate(DAYS):
        row = template.get(i)
        if row and row["is_working_day"]:
            label = f"✅ {name} {row['start_time'][:5]}–{row['end_time'][:5]}"
        else:
            label = f"❌ {name} — выходной"
        builder.button(text=label, callback_data=f"schedule_day:{i}")
    builder.button(text="🔙 Назад", callback_data="schedule:back")
    builder.adjust(1)
    return builder.as_markup()


def vacation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏖 Добавить отпуск / выходные", callback_data="vacation:add")
    builder.button(text="🗑 Удалить исключение",          callback_data="vacation:delete")
    builder.button(text="🔙 Назад", callback_data="schedule:back")
    builder.adjust(1)
    return builder.as_markup()
import calendar
from datetime import date

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def vacation_months_keyboard() -> InlineKeyboardMarkup:
    """Текущий месяц + 2 следующих."""
    today = date.today()
    builder = InlineKeyboardBuilder()
    for i in range(3):
        month = today.month + i
        year = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        builder.button(
            text=f"{MONTHS_RU[month]} {year}",
            callback_data=f"vac_month:{year}:{month}",
        )
    builder.button(text="🔙 Назад", callback_data="vacation:back")
    builder.adjust(1)
    return builder.as_markup()


def vacation_days_keyboard(year: int, month: int, selected: set[str]) -> InlineKeyboardMarkup:
    """Сетка дней месяца с отметками выбранных."""
    builder = InlineKeyboardBuilder()

    for day_name in DAYS_RU:
        builder.button(text=day_name, callback_data="cal_ignore")

    first_weekday, days_in_month = calendar.monthrange(year, month)
    for _ in range(first_weekday):
        builder.button(text=" ", callback_data="cal_ignore")

    today = date.today()
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if d < today:
            builder.button(text="·", callback_data="cal_ignore")
            continue

        if d.isoformat() in selected:
            builder.button(text=f"✅{day}", callback_data=f"vac_day:{d.isoformat()}")
        else:
            builder.button(text=str(day), callback_data=f"vac_day:{d.isoformat()}")

    builder.button(text="✅ Готово", callback_data="vac_done")
    builder.button(text="🔙 К месяцам", callback_data="vac_back_months")
    builder.adjust(7)
    return builder.as_markup()