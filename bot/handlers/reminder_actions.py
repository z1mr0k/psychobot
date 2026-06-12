from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import ADMINS
from database.logic import (
    cancel_booking,
    confirm_booking,
    get_booking_by_id,
    get_available_dates,
)
from bot.keyboards.calendar_kb import months_keyboard
from bot.handlers.booking import Booking

router = Router()


async def _notify_admins(bot, text: str) -> None:
    for admin_id in ADMINS:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            pass


# ─── ПОДТВЕРЖДЕНИЕ ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("remind_confirm:"))
async def remind_confirm(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    b = get_booking_by_id(booking_id)

    if not b:
        await callback.message.edit_text("⚠️ Запись не найдена.")
        await callback.answer()
        return

    confirm_booking(booking_id)

    await callback.message.edit_text(
        f"✅ Запись подтверждена!\n\n"
        f"📅 {b['date']}\n"
        f"🕒 {b['start_time'][:5]} – {b['end_time'][:5]}\n\n"
        f"Ждём вас!"
    )
    await _notify_admins(
        callback.message.bot,
        f"✅ Клиент подтвердил запись\n\n"
        f"👤 {b['first_name']} {b['last_name']}\n"
        f"📅 {b['date']} в {b['start_time'][:5]}",
    )
    await callback.answer()


# ─── ПЕРЕНОС ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("remind_reschedule:"))
async def remind_reschedule(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split(":")[1])
    b = get_booking_by_id(booking_id)

    if not b:
        await callback.message.edit_text("⚠️ Запись не найдена.")
        await callback.answer()
        return

    # Удаляем старую запись — слот освобождается немедленно
    cancel_booking(booking_id)

    await _notify_admins(
        callback.message.bot,
        f"🔄 Клиент перенёс запись\n\n"
        f"👤 {b['first_name']} {b['last_name']}\n"
        f"📅 {b['date']} в {b['start_time'][:5]}",
    )

    # Запускаем FSM выбора новой даты
    available = get_available_dates()
    if not available:
        await callback.message.edit_text("😔 Свободных дат нет. Попробуйте позже.")
        await callback.answer()
        return

    await state.update_data(available_dates=[d.isoformat() for d in available])
    await state.set_state(Booking.choosing_month)
    await callback.message.edit_text(
        "📅 Выберите новую дату:",
        reply_markup=months_keyboard(available),
    )
    await callback.answer()


# ─── ОТМЕНА ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("remind_cancel:"))
async def remind_cancel(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    b = get_booking_by_id(booking_id)

    if not b:
        await callback.message.edit_text("⚠️ Запись не найдена.")
        await callback.answer()
        return

    cancel_booking(booking_id)

    await callback.message.edit_text(
        f"❌ Запись отменена.\n\n"
        f"📅 {b['date']} в {b['start_time'][:5]}\n\n"
        f"Для новой записи нажмите 📅 Записаться."
    )
    await _notify_admins(
        callback.message.bot,
        f"❌ Клиент отменил запись\n\n"
        f"👤 {b['first_name']} {b['last_name']}\n"
        f"📅 {b['date']} в {b['start_time'][:5]}",
    )
    await callback.answer()