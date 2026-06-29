# bot.py
# Telegram-бот AZAL: команда "Рейсы" -> список рейсов -> по выбору рейса
# выводит Время, Опоздание, Стоянку, Пассажиров.
#
# Стек: aiogram 3, Python 3.11+
# Запуск: python bot.py
# Требуется переменная окружения BOT_TOKEN (токен от @BotFather)

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------------
# 1. ДАННЫЕ ПО РЕЙСАМ
#    Обновляй этот словарь каждую смену вручную по манифестам.
#    Ключ — номер рейса без буквы J (например "2176" для J2176).
# --------------------------------------------------------------------------

FLIGHT_DATA = {
    "2176":  {"city": "Istanbul", "time": "01:55", "delay": "нету",   "gate": "A11", "passengers": 11},
    "2812":  {"city": "Moskva",   "time": "02:15", "delay": "нету",   "gate": "A13", "passengers": 59},
    "278":   {"city": "Istanbul", "time": "02:40", "delay": "нету",   "gate": "A9",  "passengers": 15},
    "28004": {"city": "Ankara",   "time": "02:55", "delay": "нету",   "gate": "B7",  "passengers": 18},
    "8216":  {"city": "Aktau",    "time": "03:00", "delay": "нету",   "gate": "B8",  "passengers": 16},
    "2804":  {"city": "Moskva",   "time": "03:40", "delay": "нету",   "gate": "A6",  "passengers": 101},
    "26739": {"city": "Minsk",    "time": "03:45", "delay": "нету",   "gate": "A10", "passengers": 19},
    "2532":  {"city": "Taşkent",  "time": "04:10", "delay": "нету",   "gate": "B10", "passengers": 91},
    "2186":  {"city": "Moskva",   "time": "05:00", "delay": "нету",   "gate": "B5",  "passengers": 72},
    "28050": {"city": "Astana",   "time": "05:15", "delay": "нету",   "gate": "A10", "passengers": 76},
    "254":   {"city": "Almaata",  "time": "05:20", "delay": "нету",   "gate": "A1",  "passengers": 73},
    "220":   {"city": "St.Peter", "time": "05:35", "delay": "нету",   "gate": "A12", "passengers": 78},
    "2810":  {"city": "Moskva",   "time": "05:35", "delay": "нету",   "gate": "A14", "passengers": 114},
    "2146":  {"city": "Lahor",    "time": "05:50", "delay": "нету",   "gate": "A3",  "passengers": 75},
    "2140":  {"city": "St.Peter", "time": "06:35", "delay": "нету",   "gate": "A8",  "passengers": 95},
    "260":   {"city": "Mumbai",   "time": "07:40", "delay": "нету",   "gate": "A11", "passengers": 28},
}

# --------------------------------------------------------------------------
# 2. КЛАВИАТУРЫ
# --------------------------------------------------------------------------

main_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✈️ Рейсы")]],
    resize_keyboard=True,
)


def build_flights_keyboard() -> InlineKeyboardMarkup:
    """Кнопки со списком всех рейсов из FLIGHT_DATA, отсортированных по времени."""
    buttons = []
    sorted_flights = sorted(FLIGHT_DATA.items(), key=lambda item: item[1]["time"])
    for flight_number, info in sorted_flights:
        label = f"J{flight_number}  {info['city']}  {info['time']}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"flight:{flight_number}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_flight_message(flight_number: str) -> str:
    """Собирает текст ответа: Время, Опоздание, Стоянка, Пассажиры."""
    info = FLIGHT_DATA.get(flight_number)
    if not info:
        return f"Рейс J{flight_number} не найден в базе на сегодня."

    return (
        f"✈️ J{flight_number}  {info['city']}\n\n"
        f"🕐 Время: {info['time']}\n"
        f"⏱ Опоздание: {info['delay']}\n"
        f"🛑 Стоянка: {info['gate']}\n"
        f"👥 Пассажиры: {info['passengers']}"
    )


# --------------------------------------------------------------------------
# 3. БОТ И ХЕНДЛЕРЫ
# --------------------------------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот AZAL transit.\n"
        "Нажми «✈️ Рейсы», чтобы увидеть список рейсов на сегодня.\n"
        "Либо просто отправь номер рейса (например 2176).",
        reply_markup=main_menu,
    )


@dp.message(F.text == "✈️ Рейсы")
async def show_flights(message: Message):
    if not FLIGHT_DATA:
        await message.answer("На сегодня рейсы пока не загружены.")
        return
    await message.answer("Выбери рейс:", reply_markup=build_flights_keyboard())


@dp.callback_query(F.data.startswith("flight:"))
async def flight_selected(callback: CallbackQuery):
    flight_number = callback.data.split(":", 1)[1]
    text = format_flight_message(flight_number)
    await callback.message.answer(text)
    await callback.answer()


@dp.message(F.text.regexp(r"^\d{2,6}$"))
async def flight_by_number(message: Message):
    """Если пользователь просто прислал номер рейса текстом."""
    flight_number = message.text.strip()
    text = format_flight_message(flight_number)
    await message.answer(text)


@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Не понял команду 🤖\n"
        "Нажми «✈️ Рейсы» или отправь номер рейса (например 2176).",
        reply_markup=main_menu,
    )


# --------------------------------------------------------------------------
# 4. ЗАПУСК
# --------------------------------------------------------------------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
