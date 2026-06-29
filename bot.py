import os
import requests
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

AVIATION_KEY = os.getenv("AVIATIONSTACK_KEY")


def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=40.4093&longitude=49.8671&current_weather=true"
        data = requests.get(url, timeout=10).json()
        temp = data["current_weather"]["temperature"]
        return f"{temp}°C"
    except:
        return "неизвестно"


def get_flight(flight):
    try:
        url = "http://api.aviationstack.com/v1/flights"

        params = {
            "access_key": AVIATION_KEY,
            "flight_iata": flight
        }

        r = requests.get(url, params=params, timeout=15)

        data = r.json()

        if not data.get("data"):
            return None

        f = data["data"][0]

        city = f["departure"]["airport"]
        status = f["flight_status"]

        arrival = f["arrival"]["scheduled"]

        delay = f["arrival"].get("delay")

        return {
            "city": city,
            "arrival": arrival,
            "status": status,
            "delay": delay
        }

    except:
        return None


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Введите номер рейса:\n"
        "J222\n"
        "J278\n"
        "J274"
    )


@dp.message()
async def flight(message: Message):

    code = message.text.upper()

    await message.answer("🔎 Поиск рейса...")

    result = get_flight(code)

    if not result:
        await message.answer("Рейс не найден.")
        return

    weather = get_weather()

    delay_text = "нет"

    if result["delay"]:
        delay_text = f"{result['delay']} мин"

    status = result["status"]

    if status == "active":
        status = "по расписанию"

    text = (
        f"✈️ {code}\n\n"
        f"🏙 {result['city']}\n"
        f"🛬 Прибытие: {result['arrival']}\n"
        f"📌 Статус: {status}\n"
        f"⏱ Задержка: {delay_text}\n"
        f"🌤 Погода в Баку: {weather}\n"
    )

    await message.answer(text)


async def main():
    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
