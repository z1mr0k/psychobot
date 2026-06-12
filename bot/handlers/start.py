from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from database.logic import upsert_user, update_user_phone, get_user
from bot.states.registration import Registration
from bot.keyboards.booking import main_menu_keyboard

router = Router()


# ─── START ─────────────────────────────
@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user = message.from_user

    upsert_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    db_user = get_user(user.id)

    if db_user and db_user["phone"]:
        await message.answer(
            f"👋 Добро пожаловать, {db_user['first_name']} {db_user['last_name']}!",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer("Введите ваше имя:")
    await state.set_state(Registration.first_name)


# ─── NAME ─────────────────────────────
@router.message(Registration.first_name)
async def get_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text)

    await message.answer("Введите вашу фамилию:")
    await state.set_state(Registration.last_name)


# ─── LAST NAME ─────────────────────────
@router.message(Registration.last_name)
async def get_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "Отправьте номер телефона:",
        reply_markup=keyboard,
    )

    await state.set_state(Registration.phone)


# ─── PHONE ─────────────────────────────
@router.message(Registration.phone, F.contact)
async def get_phone(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("⚠️ Отправьте свой номер")
        return

    data = await state.get_data()

    upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=data["first_name"],
        last_name=data["last_name"],
    )

    update_user_phone(message.from_user.id, message.contact.phone_number)

    await message.answer(
        "✅ Регистрация завершена!",
        reply_markup=main_menu_keyboard(),
    )

    await state.clear()