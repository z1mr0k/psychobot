from __future__ import annotations

from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    FSInputFile, ReplyKeyboardRemove,
)

from bot.keyboards.admin import vacation_months_keyboard, vacation_days_keyboard
from database.logic import add_days_off
from config import ADMINS
from bot.keyboards.admin import (
    admin_main_keyboard, booking_actions_keyboard,
    edit_booking_keyboard, export_period_keyboard,
    schedule_menu_keyboard, weekdays_keyboard, vacation_keyboard,
)
from bot.services.admin_service import (
    get_bookings_by_date, get_future_bookings, get_booking_by_id,
    shift_booking, extend_booking,
    get_full_template, update_schedule_day,
    get_exceptions, add_exception, delete_exception, add_vacation,
    export_bookings_to_excel,
)
from database.logic import cancel_booking

router = Router()

# ─── FSM ─────────────────────────────────────────────────────────────────────

class AdminStates(StatesGroup):
    # расписание
    waiting_day_start  = State()
    waiting_day_end    = State()
    editing_weekday    = State()
    # исключение
    waiting_exc_date   = State()
    waiting_exc_type   = State()
    waiting_exc_start  = State()
    waiting_exc_end    = State()
    waiting_exc_delete = State()
    # отпуск (старый текстовый ввод — оставляем для совместимости)
    waiting_vac_start  = State()
    waiting_vac_end    = State()
    # новый мультивыбор отпуска
    selecting_vacation_days = State()


# ─── GUARD ───────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# ─── ФОРМАТИРОВАНИЕ ЗАПИСИ ────────────────────────────────────────────────────

def _fmt_booking(b) -> str:
    return (
        f"📅 {b['date']}\n"
        f"👤 {b['first_name']} {b['last_name']}\n"
        f"📞 {b['phone'] or '—'}\n"
        f"🕒 {b['start_time'][:5]} – {b['end_time'][:5]}\n"
        f"💬 статус: {b['status']}"
    )


# ─── ВХОД В АДМИНКУ ──────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_enter(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("👨‍💼 Админ-панель", reply_markup=admin_main_keyboard())


# ─── СЕГОДНЯ ─────────────────────────────────────────────────────────────────

@router.message(F.text == "📋 Сегодняшние записи")
async def admin_today(message: Message):
    if not is_admin(message.from_user.id):
        return
    bookings = get_bookings_by_date(date.today())
    if not bookings:
        await message.answer("На сегодня записей нет.")
        return
    for b in bookings:
        await message.answer(_fmt_booking(b), reply_markup=booking_actions_keyboard(b["id"]))


# ─── ЗАВТРА ──────────────────────────────────────────────────────────────────

@router.message(F.text == "📅 Завтра")
async def admin_tomorrow(message: Message):
    if not is_admin(message.from_user.id):
        return
    bookings = get_bookings_by_date(date.today() + timedelta(days=1))
    if not bookings:
        await message.answer("На завтра записей нет.")
        return
    for b in bookings:
        await message.answer(_fmt_booking(b), reply_markup=booking_actions_keyboard(b["id"]))


# ─── ВСЕ БУДУЩИЕ ─────────────────────────────────────────────────────────────

@router.message(F.text == "📆 Все будущие записи")
async def admin_future(message: Message):
    if not is_admin(message.from_user.id):
        return
    bookings = get_future_bookings()
    if not bookings:
        await message.answer("Будущих записей нет.")
        return
    for b in bookings:
        await message.answer(_fmt_booking(b), reply_markup=booking_actions_keyboard(b["id"]))


# ─── РЕДАКТИРОВАНИЕ ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_edit:"))
async def admin_edit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    booking_id = int(callback.data.split(":")[1])
    b = get_booking_by_id(booking_id)
    if not b:
        await callback.message.edit_text("⚠️ Запись не найдена.")
        await callback.answer()
        return
    await callback.message.edit_text(
        _fmt_booking(b) + "\n\nВыберите действие:",
        reply_markup=edit_booking_keyboard(booking_id),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()


# ─── СДВИГ ВРЕМЕНИ ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_shift:"))
async def admin_shift(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    _, booking_id, delta = callback.data.split(":")
    booking_id = int(booking_id)
    delta = int(delta)

    success, error = shift_booking(booking_id, delta)
    if not success:
        await callback.answer(f"⚠️ {error}", show_alert=True)
        return

    b = get_booking_by_id(booking_id)
    await callback.message.edit_text(
        _fmt_booking(b) + "\n\n✅ Время обновлено. Выберите действие:",
        reply_markup=edit_booking_keyboard(booking_id),
    )

    # Уведомление клиенту
    await callback.message.bot.send_message(
        chat_id=b["user_id"],
        text=(
            f"📅 Ваша запись была перенесена.\n\n"
            f"📅 {b['date']}\n"
            f"🕒 {b['start_time'][:5]} – {b['end_time'][:5]}\n\n"
            f"Если у вас вопросы — свяжитесь с нами."
        ),
    )
    await callback.answer()


# ─── ПРОДЛЕНИЕ / СОКРАЩЕНИЕ ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_extend:"))
async def admin_extend(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    _, booking_id, delta = callback.data.split(":")
    booking_id = int(booking_id)
    delta = int(delta)

    success, error = extend_booking(booking_id, delta)
    if not success:
        await callback.answer(f"⚠️ {error}", show_alert=True)
        return

    b = get_booking_by_id(booking_id)
    await callback.message.edit_text(
        _fmt_booking(b) + "\n\n✅ Длительность обновлена. Выберите действие:",
        reply_markup=edit_booking_keyboard(booking_id),
    )
    await callback.answer()


# ─── ОТМЕНА ЗАПИСИ АДМИНОМ ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_cancel:"))
async def admin_cancel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    booking_id = int(callback.data.split(":")[1])
    b = get_booking_by_id(booking_id)

    try:
        cancel_booking(booking_id)
    except ValueError:
        await callback.message.edit_text("⚠️ Запись не найдена.")
        await callback.answer()
        return

    await callback.message.edit_text("✅ Запись отменена.")

    if b:
        await callback.message.bot.send_message(
            chat_id=b["user_id"],
            text=(
                f"❌ Ваша запись отменена.\n\n"
                f"📅 {b['date']}\n"
                f"🕒 {b['start_time'][:5]} – {b['end_time'][:5]}\n\n"
                f"Для новой записи нажмите 📅 Записаться."
            ),
        )
    await callback.answer()


# ─── ЭКСПОРТ EXCEL ───────────────────────────────────────────────────────────

@router.message(F.text == "📊 Экспорт Excel")
async def admin_export(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Выберите период:", reply_markup=export_period_keyboard())


@router.callback_query(F.data.startswith("export:"))
async def admin_export_period(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    period = callback.data.split(":")[1]
    await callback.message.edit_text("⏳ Формирую файл...")

    try:
        path = export_bookings_to_excel(period)
        await callback.message.bot.send_document(
            chat_id=callback.from_user.id,
            document=FSInputFile(path),
            caption="📊 Экспорт записей",
        )
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit_text(f"⚠️ Ошибка экспорта: {e}")

    await callback.answer()


# ─── НАСТРОЙКА РАСПИСАНИЯ ────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Настройка расписания")
async def admin_schedule(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("⚙️ Расписание:", reply_markup=schedule_menu_keyboard())


@router.callback_query(F.data == "schedule:template")
async def admin_schedule_template(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    template = get_full_template()
    await callback.message.edit_text(
        "📋 Шаблон недели. Нажмите на день чтобы изменить:",
        reply_markup=weekdays_keyboard(template),
    )
    await callback.answer()

@router.callback_query(F.data == "schedule:back")
async def admin_schedule_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.message.edit_text(
        "⚙️ Расписание:",
        reply_markup=schedule_menu_keyboard(),
    )
    await callback.answer()
    
@router.callback_query(F.data.startswith("schedule_day:"))
async def admin_schedule_day(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    weekday = int(callback.data.split(":")[1])
    DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    await state.update_data(editing_weekday=weekday)
    await state.set_state(AdminStates.waiting_day_start)
    await callback.message.answer(
        f"📅 {DAYS[weekday]}\n\n"
        f"Введите время начала в формате ЧЧ:ММ\n"
        f"или напишите <b>выходной</b> чтобы сделать день нерабочим:",
    )
    await callback.answer()


@router.message(AdminStates.waiting_day_start)
async def admin_day_start(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text == "выходной":
        data = await state.get_data()
        update_schedule_day(data["editing_weekday"], is_working=False)
        await state.clear()
        template = get_full_template()
        await message.answer(
            "✅ День помечен как выходной.",
            reply_markup=weekdays_keyboard(template),
        )
        return

    if not _valid_time(text):
        await message.answer("⚠️ Неверный формат. Введите ЧЧ:ММ или 'выходной':")
        return

    await state.update_data(day_start=text)
    await state.set_state(AdminStates.waiting_day_end)
    await message.answer("Введите время окончания в формате ЧЧ:ММ:")


@router.message(AdminStates.waiting_day_end)
async def admin_day_end(message: Message, state: FSMContext):
    text = message.text.strip()
    if not _valid_time(text):
        await message.answer("⚠️ Неверный формат. Введите ЧЧ:ММ:")
        return

    data = await state.get_data()
    update_schedule_day(
        data["editing_weekday"],
        is_working=True,
        start_time=data["day_start"],
        end_time=text,
    )
    await state.clear()
    template = get_full_template()
    await message.answer(
        f"✅ Расписание обновлено: {data['day_start']} – {text}",
        reply_markup=weekdays_keyboard(template),
    )


# ─── ИСКЛЮЧЕНИЯ ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "schedule:exceptions")
async def admin_exceptions(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    exceptions = get_exceptions()
    if exceptions:
        lines = []
        for e in exceptions:
            if e["is_day_off"]:
                lines.append(f"📅 {e['date']} — выходной")
            else:
                lines.append(f"📅 {e['date']} — {e['start_time'][:5]}–{e['end_time'][:5]}")
        text = "📌 Текущие исключения:\n\n" + "\n".join(lines)
    else:
        text = "📌 Исключений нет."

    await callback.message.edit_text(text, reply_markup=vacation_keyboard())
    await callback.answer()


@router.callback_query(F.data == "vacation:add")
async def admin_vacation_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(selected_vacation_days=[])
    await state.set_state(AdminStates.selecting_vacation_days)
    await callback.message.edit_text(
        "🏖 Выберите месяц:",
        reply_markup=vacation_months_keyboard(),
    )
    await callback.answer()

@router.callback_query(AdminStates.selecting_vacation_days, F.data.startswith("vac_month:"))
async def vacation_month_chosen(callback: CallbackQuery, state: FSMContext):
    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)

    data = await state.get_data()
    selected = set(data.get("selected_vacation_days", []))

    await state.update_data(vac_year=year, vac_month=month)
    await callback.message.edit_text(
        "🏖 Выберите дни отпуска (можно несколько):",
        reply_markup=vacation_days_keyboard(year, month, selected),
    )
    await callback.answer()


@router.callback_query(AdminStates.selecting_vacation_days, F.data.startswith("vac_day:"))
async def vacation_day_toggle(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":", 1)[1]

    data = await state.get_data()
    selected = set(data.get("selected_vacation_days", []))

    if date_str in selected:
        selected.discard(date_str)
    else:
        selected.add(date_str)

    await state.update_data(selected_vacation_days=list(selected))

    year = data["vac_year"]
    month = data["vac_month"]
    await callback.message.edit_text(
        f"🏖 Выберите дни отпуска (можно несколько):\n"
        f"Выбрано: {len(selected)} дн.",
        reply_markup=vacation_days_keyboard(year, month, selected),
    )
    await callback.answer()


@router.callback_query(AdminStates.selecting_vacation_days, F.data == "vac_back_months")
async def vacation_back_to_months(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🏖 Выберите месяц:",
        reply_markup=vacation_months_keyboard(),
    )
    await callback.answer()


@router.callback_query(AdminStates.selecting_vacation_days, F.data == "vac_done")
async def vacation_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_vacation_days", [])

    if not selected:
        await callback.answer("⚠️ Не выбрано ни одного дня.", show_alert=True)
        return

    add_days_off(selected)

    dates_sorted = sorted(selected)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Добавлено выходных дней: {len(dates_sorted)}\n\n"
        f"С {dates_sorted[0]} по {dates_sorted[-1]}"
    )
    await callback.message.answer("⚙️ Расписание:", reply_markup=schedule_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "vacation:back")
async def vacation_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("⚙️ Расписание:", reply_markup=schedule_menu_keyboard())
    await callback.answer()

@router.message(AdminStates.waiting_exc_date)
async def admin_exc_date(message: Message, state: FSMContext):
    try:
        d = date.fromisoformat(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите ГГГГ-ММ-ДД:")
        return
    await state.update_data(exc_date=d.isoformat())
    await state.set_state(AdminStates.waiting_exc_type)
    await message.answer(
        "Это выходной или изменённый рабочий день?\n\n"
        "Напишите <b>выходной</b> или <b>рабочий</b>:"
    )


@router.message(AdminStates.waiting_exc_type)
async def admin_exc_type(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text == "выходной":
        data = await state.get_data()
        add_exception(date.fromisoformat(data["exc_date"]), is_day_off=True)
        await state.clear()
        await message.answer(f"✅ {data['exc_date']} добавлен как выходной.")
    elif text == "рабочий":
        await state.set_state(AdminStates.waiting_exc_start)
        await message.answer("Введите время начала в формате ЧЧ:ММ:")
    else:
        await message.answer("⚠️ Введите 'выходной' или 'рабочий':")


@router.message(AdminStates.waiting_exc_start)
async def admin_exc_start(message: Message, state: FSMContext):
    text = message.text.strip()
    if not _valid_time(text):
        await message.answer("⚠️ Неверный формат. Введите ЧЧ:ММ:")
        return
    await state.update_data(exc_start=text)
    await state.set_state(AdminStates.waiting_exc_end)
    await message.answer("Введите время окончания в формате ЧЧ:ММ:")


@router.message(AdminStates.waiting_exc_end)
async def admin_exc_end(message: Message, state: FSMContext):
    text = message.text.strip()
    if not _valid_time(text):
        await message.answer("⚠️ Неверный формат. Введите ЧЧ:ММ:")
        return
    data = await state.get_data()
    add_exception(
        date.fromisoformat(data["exc_date"]),
        is_day_off=False,
        start_time=data["exc_start"],
        end_time=text,
    )
    await state.clear()
    await message.answer(
        f"✅ {data['exc_date']} — рабочий день {data['exc_start']}–{text}"
    )


@router.callback_query(F.data == "vacation:delete")
async def admin_exc_delete_ask(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_exc_delete)
    await callback.message.answer(
        "Введите дату исключения для удаления (ГГГГ-ММ-ДД):"
    )
    await callback.answer()


@router.message(AdminStates.waiting_exc_delete)
async def admin_exc_delete(message: Message, state: FSMContext):
    try:
        d = date.fromisoformat(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите ГГГГ-ММ-ДД:")
        return
    delete_exception(d)
    await state.clear()
    await message.answer(f"✅ Исключение {d.isoformat()} удалено.")


# ─── ОТПУСК ──────────────────────────────────────────────────────────────────

@router.message(F.text == "🏖 Отпуск / выходные")
async def admin_vacation(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_vac_start)
    await message.answer(
        "Введите дату начала отпуска (ГГГГ-ММ-ДД):",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(AdminStates.waiting_vac_start)
async def admin_vac_start(message: Message, state: FSMContext):
    try:
        d = date.fromisoformat(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите ГГГГ-ММ-ДД:")
        return
    await state.update_data(vac_start=d.isoformat())
    await state.set_state(AdminStates.waiting_vac_end)
    await message.answer("Введите дату окончания отпуска (ГГГГ-ММ-ДД):")


@router.message(AdminStates.waiting_vac_end)
async def admin_vac_end(message: Message, state: FSMContext):
    try:
        end = date.fromisoformat(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите ГГГГ-ММ-ДД:")
        return

    data = await state.get_data()
    start = date.fromisoformat(data["vac_start"])

    if end < start:
        await message.answer("⚠️ Дата окончания не может быть раньше начала.")
        return

    add_vacation(start, end)
    days = (end - start).days + 1
    await state.clear()
    await message.answer(
        f"✅ Отпуск добавлен: {start.isoformat()} – {end.isoformat()} ({days} дн.)",
        reply_markup=admin_main_keyboard(),
    )


# ─── ВСПОМОГАТЕЛЬНЫЕ ─────────────────────────────────────────────────────────

def _valid_time(s: str) -> bool:
    try:
        parts = s.split(":")
        assert len(parts) == 2
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
        return True
    except Exception:
        return False