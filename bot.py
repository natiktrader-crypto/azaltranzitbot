import asyncio
import requests

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton
)

BOT_TOKEN = "ВАШ_ТОКЕН"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

language = {}

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Расписание")],
        [KeyboardButton(text="🌤 Погода")],
        [KeyboardButton(text="🌐 Language")]
    ],
    resize_keyboard=True
)


def get_weather():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=40.4093"
            "&longitude=49.8671"
            "&current_weather=true"
        )

        data = requests.get(url).json()

        temp = data["current_weather"]["temperature"]

        return f"{temp}°C"

    except:
        return "нет данных"


def search_flight(number):

    number = number.upper().replace("J", "")

    with open("flights.txt", "r", encoding="utf-8") as f:

        for line in f:

            parts = line.strip().split()

            if len(parts) < 4:
                continue

            flight = parts[0]
            city = parts[1]
            time = parts[2]
            pax = parts[3]

            if flight == number:

                return city, time, pax

    return None


@dp.message(Command("start"))
async def start(message: Message):

    language[message.chat.id] = "ru"

    await message.answer(
        "✈️ AZAL Transit Bot",
        reply_markup=menu
    )


@dp.message(lambda m: m.text == "🌐 Language")
async def lang(message: Message):

    await message.answer(
        "🇷🇺 Русский\n"
        "🇬🇧 English\n"
        "🇹🇷 Türkçe"
    )


@dp.message(lambda m: m.text == "🇷🇺 Русский")
async def ru(message: Message):
    language[message.chat.id] = "ru"
    await message.answer("Язык изменён.")


@dp.message(lambda m: m.text == "🇬🇧 English")
async def en(message: Message):
    language[message.chat.id] = "en"
    await message.answer("Language changed.")


@dp.message(lambda m: m.text == "🇹🇷 Türkçe")
async def tr(message: Message):
    language[message.chat.id] = "tr"
    await message.answer("Dil değiştirildi.")


@dp.message(lambda m: m.text == "📋 Расписание")
async def schedule(message: Message):

    await message.answer_document(
        document=open("flights.txt", "rb")
    )


@dp.message(lambda m: m.text == "🌤 Погода")
async def weather(message: Message):

    temp = get_weather()

    await message.answer(
        f"🌤 Баку: {temp}"
    )


@dp.message()
async def find(message: Message):

    result = search_flight(message.text)

    if not result:
        await message.answer("❌ Рейс не найден.")
        return

    city, time, pax = result

    lang = language.get(message.chat.id, "ru")

    weather = get_weather()

    if lang == "ru":

        text = (
            f"✈️ J{message.text.upper().replace('J','')} {city}\n\n"
            f"🛬 Прибытие: {time}\n"
            f"📌 Статус: По расписанию\n"
            f"⏱ Задержка: Нет\n"
            f"👥 Транзит: {pax}\n"
            f"🌤 Погода: {weather}"
        )

    elif lang == "en":

        text = (
            f"✈️ J{message.text.upper().replace('J','')} {city}\n\n"
            f"🛬 Arrival: {time}\n"
            f"📌 Status: On time\n"
            f"⏱ Delay: No\n"
            f"👥 Passengers: {pax}\n"
            f"🌤 Weather: {weather}"
        )

    else:

        text = (
            f"✈️ J{message.text.upper().replace('J','')} {city}\n\n"
            f"🛬 Varış: {time}\n"
            f"📌 Durum: Zamanında\n"
            f"⏱ Gecikme: Yok\n"
            f"👥 Yolcu: {pax}\n"
            f"🌤 Hava: {weather}"
        )

    await message.answer(text)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
