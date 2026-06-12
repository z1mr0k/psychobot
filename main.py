import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.handlers.admin import router as admin_router

from config import BOT_TOKEN
from database.models import init_db
from database.logic import seed_default_schedule

from bot.handlers.start import router as start_router
from bot.handlers.booking import router as booking_router
from bot.handlers.my_bookings import router as my_bookings_router
from bot.services.reminder import send_reminders
from bot.handlers.reminder_actions import router as reminder_actions_router

async def main():
    init_db()
    seed_default_schedule()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(my_bookings_router)
    dp.include_router(admin_router)
    dp.include_router(reminder_actions_router)
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, "interval", minutes=1, args=[bot])
    scheduler.start()

    print("Бот запущен 🚀")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())