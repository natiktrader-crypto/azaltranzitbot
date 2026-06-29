"""
Hasanov_Natik — Telegram-бот для проверки статуса рейсов
(задержки, отмены, прилёт/вылет) через airport.az

Источник данных: https://airport.az/en/flights/arrivals/ и /departures/

Токен берётся из переменной окружения BOT_TOKEN —
сам токен НИКОГДА не пишется в код (это безопасная практика).
"""

import os
import re
import logging
import requests
from bs4 import BeautifulSoup

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Добавьте переменную окружения BOT_TOKEN "
        "в настройках Railway (Variables) перед запуском."
    )

URLS = {
    "departures": "https://airport.az/en/flights/departures/",
    "arrivals": "https://airport.az/en/flights/arrivals/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

TERMINAL_PATTERNS = ["Terminal 1", "Terminal 2", "T2 South", "T2 North"]


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_flights(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    flight_links = soup.find_all("a", href=re.compile(r"\?flight=\d+"))

    flights = []
    time_pattern = re.compile(
        r"^(\d{2}:\d{2})(?:\s(\d{2}:\d{2}))?(\d{2})\s?([A-Za-z]{3})(.*)$"
    )
    code_pattern = re.compile(r"([A-Z0-9]{2})\s?(\d{2,5})")

    for a in flight_links:
        text = a.get_text(strip=True)
        m = time_pattern.match(text)
        if not m:
            continue

        time1, time2, day, month, rest = m.groups()

        code_m = code_pattern.search(rest)
        if not code_m:
            continue

        city = rest[: code_m.start()].strip()
        flight_code = f"{code_m.group(1)} {code_m.group(2)}"
        after = rest[code_m.end():].strip()

        terminal = ""
        status = after
        for t in TERMINAL_PATTERNS:
            if after.startswith(t):
                terminal = t
                status = after[len(t):].strip()
                break

        if not status or status == "-":
            status = "Расписание (рейс пока не начался)"

        flights.append({
            "scheduled_time": time1,
            "actual_time": time2,
            "date": f"{day} {month}",
            "city": city,
            "flight_code": flight_code.upper().replace(" ", ""),
            "flight_code_display": flight_code,
            "terminal": terminal,
            "status": status,
        })

    return flights


def search_flight(flight_number: str) -> list:
    flight_number = flight_number.upper().replace(" ", "")
    results = []

    for direction, url in URLS.items():
        try:
            html = fetch_page(url)
        except requests.RequestException as e:
            logger.error(f"Ошибка загрузки {direction}: {e}")
            continue

        flights = parse_flights(html)
        for f in flights:
            code_clean = f["flight_code"]
            if flight_number in code_clean or code_clean.endswith(flight_number):
                f["direction"] = "Вылет" if direction == "departures" else "Прилёт"
                results.append(f)

    return results


def format_flight(f: dict) -> str:
    lines = [
        f"✈️ Рейс {f['flight_code_display']} ({f['direction']})",
        f"🏙 {f['city']}",
        f"📅 {f['date']}",
        f"🕐 Расписание: {f['scheduled_time']}",
    ]
    if f["actual_time"]:
        lines.append(f"🕓 Фактическое время: {f['actual_time']}")
    if f["terminal"]:
        lines.append(f"🚪 {f['terminal']}")
    lines.append(f"📌 Статус: {f['status']}")
    return "\n".join(lines)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот Hasanov_Natik.\n\n"
        "Напишите номер рейса (например: J2123 или 123), "
        "и я пришлю актуальный статус: вовремя, задержка или отмена.\n\n"
        "Источник данных: airport.az"
    )


@dp.message()
async def handle_flight_query(message: Message):
    query = message.text.strip()

    if not re.search(r"\d", query):
        await message.answer("Пришлите номер рейса, например: J2123 или просто 123")
        return

    await message.answer("🔎 Ищу информацию о рейсе...")

    try:
        results = search_flight(query)
    except Exception as e:
        logger.exception("Ошибка поиска рейса")
        await message.answer(f"⚠️ Произошла ошибка при поиске: {e}")
        return

    if not results:
        await message.answer(
            f"Рейс «{query}» не найден в текущем расписании airport.az.\n"
            "Проверьте номер или попробуйте позже — расписание обновляется."
        )
        return

    for f in results[:5]:
        await message.answer(format_flight(f))


async def main():
    logger.info("Бот Hasanov_Natik запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
