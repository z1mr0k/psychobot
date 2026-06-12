from __future__ import annotations

from datetime import date, datetime, time

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import ADMINS
from database.logic import (
    get_available_dates,
    generate_available_slots,
    create_booking,
)
from bot.keyboards.calendar_kb import months_keyboard, days_keyboard, times_keyboard
from bot.keyboards.booking import main_menu_keyboard

router = Router()


class Booking(StatesGroup):
    choosing_month = State()
    choosing_day   = State()
    choosing_time  = State()


# ─── СТАРТ ЗАПИСИ ─────────────────────────────────────────────────────────────

@router.message(F.text == "📅 Записаться")
async def booking_start(message: Message, state: FSMContext):
    available = get_available_dates()
    if not available:
        await message.answer("😔 Свободных дат нет. Попробуйте позже.")
        return

    await state.update_data(available_dates=[d.isoformat() for d in available])
    await state.set_state(Booking.choosing_month)
    await message.answer("📅 Выберите месяц:", reply_markup=months_keyboard(available))


# ─── ВЫБОР МЕСЯЦА ─────────────────────────────────────────────────────────────

@router.callback_query(Booking.choosing_month, F.data.startswith("cal_month:"))
async def booking_month_chosen(callback: CallbackQuery, state: FSMContext):
    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)

    data = await state.get_data()
    available = [date.fromisoformat(s) for s in data["available_dates"]]

    await state.update_data(current_year=year, current_month=month)
    await state.set_state(Booking.choosing_day)
    await callback.message.edit_text(
        "📅 Выберите день:",
        reply_markup=days_keyboard(year, month, available),
    )
    await callback.answer()


@router.callback_query(Booking.choosing_month, F.data == "cal_cancel")
async def booking_cancel_month(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer()


# ─── ВЫБОР ДНЯ ────────────────────────────────────────────────────────────────

@router.callback_query(Booking.choosing_day, F.data.startswith("cal_day:"))
async def booking_day_chosen(callback: CallbackQuery, state: FSMContext):
    chosen_date = date.fromisoformat(callback.data.split(":")[1])
    slots = generate_available_slots(chosen_date)

    if not slots:
        await callback.answer("😔 На эту дату нет свободного времени.", show_alert=True)
        return

    await state.update_data(chosen_date=chosen_date.isoformat())
    await state.set_state(Booking.choosing_time)
    await callback.message.edit_text(
        f"🕐 Выберите время на {chosen_date.strftime('%d.%m.%Y')}:",
        reply_markup=times_keyboard(slots, chosen_date),
    )
    await callback.answer()


@router.callback_query(Booking.choosing_day, F.data == "cal_back")
async def booking_back_to_months(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    available = [date.fromisoformat(s) for s in data["available_dates"]]
    await state.set_state(Booking.choosing_month)
    await callback.message.edit_text(
        "📅 Выберите месяц:",
        reply_markup=months_keyboard(available),
    )
    await callback.answer()


@router.callback_query(Booking.choosing_day, F.data == "cal_ignore")
async def booking_ignore(callback: CallbackQuery):
    await callback.answer()


# ─── ВЫБОР ВРЕМЕНИ ────────────────────────────────────────────────────────────

@router.callback_query(Booking.choosing_time, F.data.startswith("cal_time:"))
async def booking_time_chosen(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
# parts = ["cal_time", "2026-05-20", "10", "00"]
    date_str = parts[1]
    time_str = f"{parts[2]}:{parts[3]}"
    chosen_date = date.fromisoformat(date_str)
    chosen_time = time.fromisoformat(time_str)

    try:
        create_booking(
            user_id=callback.from_user.id,
            d=chosen_date,
            start=chosen_time,
        )
    except ValueError:
        await callback.answer("😔 Слот только что заняли. Попробуйте другое время.", show_alert=True)
        await state.clear()
        return

    await state.clear()

    time_label = chosen_time.strftime("%H:%M")
    date_label = chosen_date.strftime("%d.%m.%Y")

    # Уведомление админу
    for admin_id in ADMINS:
        try:
            await callback.message.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🆕 Новая запись!\n\n"
                    f"👤 {callback.from_user.full_name}"
                    f" (@{callback.from_user.username or '—'})\n"
                    f"📅 {date_label}\n"
                    f"🕐 {time_label}"
                ),
            )
        except Exception:
            pass

    await callback.message.edit_text(
        f"✅ Вы записаны!\n\n"
        f"📅 Дата: {date_label}\n"
        f"🕐 Время: {time_label}\n\n"
        f"Ждём вас! Если планы изменятся — напишите нам.",
    )
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(Booking.choosing_time, F.data == "cal_back_to_month")
async def booking_back_to_days(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    available = [date.fromisoformat(s) for s in data["available_dates"]]
    year  = data["current_year"]
    month = data["current_month"]
    await state.set_state(Booking.choosing_day)
    await callback.message.edit_text(
        "📅 Выберите день:",
        reply_markup=days_keyboard(year, month, available),
    )
    await callback.answer()