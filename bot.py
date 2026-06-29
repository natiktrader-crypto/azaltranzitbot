"""
Hasanov_Natik — Telegram-бот для проверки статуса рейсов
(задержки, отмены, прилёт/вылет) через airport.az

Источник данных: https://airport.az/en/flights/arrivals/ и /departures/

Команда токена берётся из переменной окружения BOT_TOKEN —
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

AVIATIONSTACK_KEY = os.getenv("AVIATIONSTACK_KEY")

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

# Терминалы, как они подписаны на сайте
TERMINAL_PATTERNS = ["Terminal 1", "Terminal 2", "T2 South", "T2 North"]

WEATHER_CODES = {
    0: "Ясно", 1: "Малооблачно", 2: "Облачно", 3: "Облачно",
    45: "Туман", 48: "Туман",
    51: "Лёгкий дождь", 53: "Дождь", 55: "Сильный дождь",
    61: "Дождь", 63: "Дождь", 65: "Сильный дождь",
    71: "Снег", 73: "Снег", 75: "Сильный снег",
    80: "Ливень", 81: "Ливень", 82: "Сильный ливень",
    95: "Гроза", 96: "Гроза с градом", 99: "Гроза с градом",
}
BAD_WEATHER_CODES = {45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99}


def fetch_weather():
    """Погода в Баку через бесплатный Open-Meteo (без ключа)."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": 40.4675, "longitude": 50.0467, "current_weather": "true"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        cw = resp.json()["current_weather"]
        temp = cw["temperature"]
        code = cw["weathercode"]
        desc = WEATHER_CODES.get(code, "неизвестно")
        return temp, desc, code
    except Exception as e:
        logger.error(f"Ошибка погоды: {e}")
        return None, None, None


def compute_delay(scheduled: str, actual: str):
    """Считает задержку в минутах между расписанием и фактом."""
    if not actual:
        return None
    try:
        h1, m1 = map(int, scheduled.split(":"))
        h2, m2 = map(int, actual.split(":"))
        diff = (h2 * 60 + m2) - (h1 * 60 + m1)
        if diff < -600:
            diff += 1440
        elif diff > 600:
            diff -= 1440
        return diff
    except Exception:
        return None


def suggest_cause(weather_code):
    """Честное предположение о причине — НЕ официальный факт."""
    if weather_code in BAD_WEATHER_CODES:
        return (
            f"⚠️ Возможно связано с погодой ({WEATHER_CODES.get(weather_code)}) "
            "— это предположение, а не подтверждённая официальная причина."
        )
    return "ℹ️ Точная причина задержки не публикуется авиакомпанией."


def fetch_page(url: str) -> str:
    """Скачивает HTML страницы airport.az."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_flights(html: str) -> list[dict]:
    """
    Разбирает HTML страницы рейсов airport.az.
    Каждый рейс на сайте — это <a href="...?flight=ID">текст рейса</a>.
    """
    soup = BeautifulSoup(html, "html.parser")
    flight_links = soup.find_all("a", href=re.compile(r"\?flight=\d+"))

    flights = []
    # Паттерн: время1 [время2] ДД Mon ГородРейс ТерминалСтатус
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
        airline_code = code_m.group(1)
        flight_num = code_m.group(2)
        flight_code = f"{airline_code} {flight_num}"
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
            "airline_code": airline_code,
            "flight_num": flight_num,
            "flight_code": flight_code.upper().replace(" ", ""),
            "flight_code_display": flight_code,
            "terminal": terminal,
            "status": status,
        })

    return flights


def fetch_aviationstack(flight_number: str) -> list[dict]:
    """Запрашивает статус рейса через AviationStack API (доп. источник)."""
    if not AVIATIONSTACK_KEY:
        return []

    url = "http://api.aviationstack.com/v1/flights"
    params = {
        "access_key": AVIATIONSTACK_KEY,
        "flight_iata": flight_number,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Ошибка AviationStack: {e}")
        return []

    results = []
    for item in data.get("data", []):
        results.append({
            "source": "AviationStack",
            "flight_code_display": item.get("flight", {}).get("iata", flight_number),
            "city_from": item.get("departure", {}).get("airport", "?"),
            "city_to": item.get("arrival", {}).get("airport", "?"),
            "status": item.get("flight_status", "неизвестно"),
            "scheduled_dep": item.get("departure", {}).get("scheduled", "?"),
            "scheduled_arr": item.get("arrival", {}).get("scheduled", "?"),
            "delay_dep": item.get("departure", {}).get("delay"),
            "delay_arr": item.get("arrival", {}).get("delay"),
        })
    return results


def format_aviationstack(f: dict) -> str:
    lines = [
        f"✈️ Рейс {f['flight_code_display']} (AviationStack)",
        f"🛫 Из: {f['city_from']}",
        f"🛬 В: {f['city_to']}",
        f"📌 Статус: {f['status']}",
        f"🕐 Вылет по расписанию: {f['scheduled_dep']}",
        f"🕐 Прилёт по расписанию: {f['scheduled_arr']}",
    ]
    if f.get("delay_dep"):
        lines.append(f"⏱ Задержка вылета: {f['delay_dep']} мин")
    if f.get("delay_arr"):
        lines.append(f"⏱ Задержка прилёта: {f['delay_arr']} мин")
    return "\n".join(lines)



def flight_matches(query: str, airline_code: str, flight_num: str) -> bool:
    """Точное сравнение номера рейса (без ложных совпадений по подстроке)."""
    query = query.upper().replace(" ", "")
    num_stripped = flight_num.lstrip("0") or "0"

    if query.isdigit():
        return query.lstrip("0") == num_stripped

    full_code = f"{airline_code}{flight_num}"
    if query == full_code:
        return True

    if query.startswith(airline_code):
        rest = query[len(airline_code):]
        if rest.isdigit():
            return rest.lstrip("0") == num_stripped

    return False


def search_flight(flight_number: str) -> list[dict]:
    """Ищет рейс по номеру (например J2123 или 123) во всех направлениях."""
    results = []

    for direction, url in URLS.items():
        try:
            html = fetch_page(url)
        except requests.RequestException as e:
            logger.error(f"Ошибка загрузки {direction}: {e}")
            continue

        flights = parse_flights(html)
        for f in flights:
            if flight_matches(flight_number, f["airline_code"], f["flight_num"]):
                f["direction"] = "Вылет" if direction == "departures" else "Прилёт"
                results.append(f)

    return results


def format_flight(f: dict, weather=None) -> str:
    delay = compute_delay(f["scheduled_time"], f["actual_time"])

    lines = [
        f"✈️ Рейс {f['flight_code_display']} ({f['direction']})",
        f"🏙 {f['city']}",
        f"📅 {f['date']}",
        f"🕐 Расписание: {f['scheduled_time']}",
    ]

    if f["actual_time"]:
        lines.append(f"🕓 Фактически: {f['actual_time']}")

    if delay is not None:
        if delay > 0:
            lines.append(f"⏱ Опаздывает: на {delay} мин")
        elif delay < 0:
            lines.append(f"⏱ Раньше расписания: на {abs(delay)} мин")
        else:
            lines.append("⏱ Без задержки, точно по расписанию")

    if f["terminal"]:
        lines.append(f"🚪 {f['terminal']}")

    lines.append(f"📌 Статус: {f['status']}")

    if delay and delay > 5 and weather:
        temp, desc, code = weather
        lines.append(f"🌤 Погода в Баку сейчас: {desc}, {temp}°C")
        lines.append(suggest_cause(code))

    return "\n".join(lines)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("debug"))
async def cmd_debug(message: Message):
    report = []
    for direction, url in URLS.items():
        try:
            html = fetch_page(url)
            flights = parse_flights(html)
            report.append(f"{direction}: получено {len(flights)} рейсов, длина HTML {len(html)} символов")
            if flights:
                sample = flights[0]
                report.append(f"  Пример: {sample['flight_code_display']} {sample['city']} {sample['status']}")
        except Exception as e:
            report.append(f"{direction}: ОШИБКА — {e}")
    await message.answer("\n".join(report))


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот Hasanov_Natik.\n\n"
        "Напишите номер рейса — лучше ТОЛЬКО ЦИФРЫ (например: 226), "
        "без буквы авиакомпании, чтобы избежать путаницы.\n\n"
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

    av_results = fetch_aviationstack(query)

    if not results and not av_results:
        await message.answer(
            f"Рейс «{query}» не найден ни на airport.az, ни через AviationStack.\n"
            "Проверьте номер или попробуйте позже — расписание обновляется."
        )
        return

    for f in results[:5]:
        weather = fetch_weather()
        await message.answer(format_flight(f, weather))

    for f in av_results[:3]:
        await message.answer(format_aviationstack(f))


async def main():
    logger.info("Бот Hasanov_Natik запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
