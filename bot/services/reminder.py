from __future__ import annotations

from datetime import timedelta

from aiogram import Bot
from aiogram.fsm.context import FSMContext

from config import ADMINS
from database.logic import (
    get_bookings_pending_reminder,
    mark_reminder_sent,
    cancel_booking,
    confirm_booking,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def _reminder_24h_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтверждаю",  callback_data=f"remind_confirm:{booking_id}")
    builder.button(text="🔄 Перенести",    callback_data=f"remind_reschedule:{booking_id}")
    builder.button(text="❌ Отменить",     callback_data=f"remind_cancel:{booking_id}")
    builder.adjust(1)
    return builder.as_markup()


async def send_reminders(bot: Bot) -> None:
    """Вызывается планировщиком раз в минуту."""

    # ── 24 часа — с кнопками ──────────────────────────────────────────────────
    for b in get_bookings_pending_reminder(timedelta(hours=24), "reminder_24h_sent"):
        try:
            await bot.send_message(
                chat_id=b["user_id"],
                text=(
                    f"🔔 Напоминание!\n\n"
                    f"Завтра в {b['start_time'][:5]} у вас консультация.\n\n"
                    f"Пожалуйста, подтвердите запись или сообщите об изменениях:"
                ),
                reply_markup=_reminder_24h_keyboard(b["id"]),
            )
            mark_reminder_sent(b["id"], "reminder_24h_sent")
        except Exception:
            pass

    # ── 2 часа — только текст ─────────────────────────────────────────────────
    for b in get_bookings_pending_reminder(timedelta(hours=2), "reminder_2h_sent"):
        try:
            await bot.send_message(
                chat_id=b["user_id"],
                text=(
                    f"🔔 Напоминание!\n\n"
                    f"Сегодня в {b['start_time'][:5]} у вас консультация."
                ),
            )
            mark_reminder_sent(b["id"], "reminder_2h_sent")
        except Exception:
            pass