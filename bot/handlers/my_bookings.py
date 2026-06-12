from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.keyboards.booking import main_menu_keyboard
from database.logic import get_user_bookings, cancel_booking

router = Router()

_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

def _format_date(date_str: str) -> str:
    from datetime import date
    d = date.fromisoformat(date_str)
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month]}"


def _bookings_keyboard(bookings):
    builder = InlineKeyboardBuilder()
    for b in bookings:
        label = f"{_format_date(b['date'])} в {b['start_time'][:5]}"
        builder.button(
            text=f"❌ Отменить — {label}",
            callback_data=f"cancel_booking:{b['id']}",
        )
    builder.adjust(1)
    return builder.as_markup()


@router.message(F.text == "📋 Мои записи")
async def my_bookings_handler(message: Message):
    bookings = get_user_bookings(message.from_user.id)

    if not bookings:
        await message.answer("У вас нет активных записей.")
        return

    lines = []
    for b in bookings:
        lines.append(f"📅 {_format_date(b['date'])} в {b['start_time'][:5]}")

    await message.answer(
        "Ваши записи:\n\n" + "\n".join(lines) + "\n\nНажмите чтобы отменить:",
        reply_markup=_bookings_keyboard(bookings),
    )


@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking_handler(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])

    try:
        cancel_booking(booking_id)
        await callback.message.edit_text("✅ Запись отменена.")
    except ValueError:
        await callback.message.edit_text("⚠️ Запись не найдена — возможно, уже отменена.")

    await callback.answer()