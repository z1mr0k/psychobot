from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


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
    builder.button(text="❌ Отменить",       callback_data=f"admin_cancel:{booking_id}")
    builder.adjust(2)
    return builder.as_markup()


def edit_booking_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏪ -1 час",          callback_data=f"admin_shift:{booking_id}:-60")
    builder.button(text="◀️ -30 мин",         callback_data=f"admin_shift:{booking_id}:-30")
    builder.button(text="▶️ +30 мин",         callback_data=f"admin_shift:{booking_id}:+30")
    builder.button(text="⏩ +1 час",          callback_data=f"admin_shift:{booking_id}:+60")
    builder.button(text="➕ Продлить +30",    callback_data=f"admin_extend:{booking_id}:+30")
    builder.button(text="➖ Сократить -30",   callback_data=f"admin_extend:{booking_id}:-30")
    builder.button(text="❌ Отменить запись", callback_data=f"admin_cancel:{booking_id}")
    builder.button(text="🔙 Назад",           callback_data="admin_back")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def export_period_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Эта неделя", callback_data="export:week")
    builder.button(text="📆 Этот месяц", callback_data="export:month")
    builder.button(text="🔙 Назад",      callback_data="admin_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()


def schedule_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Шаблон недели", callback_data="schedule:template")
    builder.button(text="📌 Исключения",    callback_data="schedule:exceptions")
    builder.button(text="🔙 В главное меню", callback_data="admin_to_main")
    builder.adjust(1)
    return builder.as_markup()


def weekdays_keyboard(template: dict) -> InlineKeyboardMarkup:
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
    builder.button(text="🏖 Добавить выходные",  callback_data="vacation:add")
    builder.button(text="🗑 Удалить выходные",   callback_data="vacation:delete")
    builder.button(text="🔙 Назад",              callback_data="schedule:back")
    builder.adjust(1)
    return builder.as_markup()


def vacation_months_keyboard(mode: str = "add") -> InlineKeyboardMarkup:
    today = date.today()
    builder = InlineKeyboardBuilder()
    for i in range(4):  # было 3
        month = today.month + i
        year  = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        builder.button(
            text=f"{MONTHS_RU[month]} {year}",
            callback_data=f"vac_month:{year}:{month}:{mode}",
        )
    builder.button(text="🔙 Назад", callback_data="vacation:back")
    builder.adjust(1)
    return builder.as_markup()


def vacation_days_keyboard(
    year: int,
    month: int,
    selected: set[str],
    mode: str = "add",
    existing_days_off: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    existing_days_off — даты уже помеченные как выходные (показываем серым 🔴).
    """
    if existing_days_off is None:
        existing_days_off = set()

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

        iso = d.isoformat()
        if iso in selected:
            mark = "🗑" if mode == "delete" else "✅"
            builder.button(text=f"{mark}{day}", callback_data=f"vac_day:{iso}:{mode}")
        elif iso in existing_days_off and mode == "delete":
            # день уже выходной, но ещё не выбран для удаления
            builder.button(text=f"🔴{day}", callback_data=f"vac_day:{iso}:{mode}")
        else:
            builder.button(text=str(day), callback_data=f"vac_day:{iso}:{mode}")

    done_text = "🗑 Удалить выбранные" if mode == "delete" else "✅ Готово"
    builder.button(text=done_text,       callback_data=f"vac_done:{mode}")
    builder.button(text="🔙 К месяцам", callback_data=f"vac_back_months:{mode}")
    builder.adjust(7)
    return builder.as_markup()
    done_text = "🗑 Удалить выбранные" if mode == "delete" else "✅ Готово"
    builder.button(text=done_text,        callback_data=f"vac_done:{mode}")
    builder.button(text="🔙 К месяцам",  callback_data=f"vac_back_months:{mode}")
    builder.adjust(7)
    return builder.as_markup()

@router.callback_query(AdminStates.selecting_vacation_days, F.data.startswith("vac_month:"))
async def vacation_month_chosen(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month, mode = int(parts[1]), int(parts[2]), parts[3]

    data = await state.get_data()
    selected = set(data.get("selected_vacation_days", []))

    await state.update_data(vac_year=year, vac_month=month, vac_mode=mode)

    # При удалении — показываем какие дни уже выходные
    existing: set[str] = set()
    if mode == "delete":
        from database.logic import get_exceptions
        all_exc = get_exceptions()
        existing = {
            e["date"] for e in all_exc
            if e["date"].startswith(f"{year}-{month:02d}")
        }

    title = "🗑 Выберите дни для удаления:" if mode == "delete" else "🏖 Выберите дни (можно несколько):"
    await callback.message.edit_text(
        f"{title}\nВыбрано: {len(selected)} дн.",
        reply_markup=vacation_days_keyboard(year, month, selected, mode, existing),
    )
    await callback.answer()


@router.callback_query(AdminStates.selecting_vacation_days, F.data.startswith("vac_day:"))
async def vacation_day_toggle(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    date_str = parts[1]
    mode = parts[2]

    data = await state.get_data()
    selected = set(data.get("selected_vacation_days", []))

    if date_str in selected:
        selected.discard(date_str)
    else:
        selected.add(date_str)

    await state.update_data(selected_vacation_days=list(selected))

    year  = data["vac_year"]
    month = data["vac_month"]

    existing: set[str] = set()
    if mode == "delete":
        from database.logic import get_exceptions
        all_exc = get_exceptions()
        existing = {
            e["date"] for e in all_exc
            if e["date"].startswith(f"{year}-{month:02d}")
        }

    title = "🗑 Выберите дни для удаления:" if mode == "delete" else "🏖 Выберите дни (можно несколько):"
    await callback.message.edit_text(
        f"{title}\nВыбрано: {len(selected)} дн.",
        reply_markup=vacation_days_keyboard(year, month, selected, mode, existing),
    )
    await callback.answer()

def exceptions_months_keyboard() -> InlineKeyboardMarkup:
    today = date.today()
    builder = InlineKeyboardBuilder()
    for i in range(4):  # было 3
        month = today.month + i
        year  = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        builder.button(
            text=f"{MONTHS_RU[month]} {year}",
            callback_data=f"exc_month:{year}:{month}",
        )
    builder.button(text="🔙 Назад", callback_data="schedule:back")
    builder.adjust(1)
    return builder.as_markup()