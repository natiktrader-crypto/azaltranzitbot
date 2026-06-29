import os
import re
import asyncio
import logging
import requests

from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
AVIATIONSTACK_KEY = os.getenv("AVIATIONSTACK_KEY")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

ARRIVALS = "https://airport.az/en/flights/arrivals/"
DEPARTURES = "https://airport.az/en/flights/departures/"


def get_weather():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=40.4093"
            "&longitude=49.8671"
            "&current_weather=true"
        )

        data = requests.get(url, timeout=10).json()

        temp = data["current_weather"]["temperature"]

        return f"+{temp}°C"

    except:
        return "нет данных"


def airport_search(number):

    urls = [ARRIVALS, DEPARTURES]

    for url in urls:

        try:
            html = requests.get(
                url,
                headers=HEADERS,
                timeout=15
            ).text

            if number.upper() in html.upper():

                return "Найден на airport.az"

        except:
            pass

    return None


def aviation_search(number):

    if not AVIATIONSTACK_KEY:
        return None

    try:
        url = "http://api.aviationstack.com/v1/flights"

        params = {
            "access_key": AVIATIONSTACK_KEY,
            "flight_iata": number
        }

        data = requests.get(
            url,
            params=params,
            timeout=15
        ).json()

        if not data.get("data"):
            return None

        flight = data["data"][0]

        return {
            "status": flight.get("flight_status"),
            "arrival": flight["arrival"].get("scheduled"),
            "delay": flight["arrival"].get("delay")
        }

    except Exception as e:
        logging.error(e)

        return None


@dp.message(Command("start"))
async def start(message: Message):

    await message.answer(
        "✈️ Бот AZAL.\n\n"
        "Введите номер рейса:\n"
        "J278"
    )


@dp.message()
async def search(message: Message):

    flight = message.text.upper().strip()

    await message.answer("🔎 Поиск рейса...")

    weather = get_weather()

    result = aviation_search(flight)

    if result:

        delay = result["delay"]

        if delay:
            delay_text = f"{delay} минут"
        else:
            delay_text = "нет"

        text = (
            f"✈️ {flight}\n\n"
            f"🛬 Прибытие: {result['arrival']}\n"
            f"📌 Статус: {result['status']}\n"
            f"⏱ Задержка: {delay_text}\n"
            f"🌤 Погода: {weather}"
        )

        await message.answer(text)

        return

    airport = airport_search(flight)

    if airport:

        await message.answer(
            f"✈️ {flight}\n\n"
            f"📌 Рейс найден на airport.az\n"
            f"🌤 Погода: {weather}"
        )

        return

    await message.answer(
        "❌ Рейс не найден."
    )


async def main():

    logging.info("Bot started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
