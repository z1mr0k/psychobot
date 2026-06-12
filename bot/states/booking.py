from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    choosing_date = State()
    choosing_time = State()