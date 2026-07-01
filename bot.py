import asyncio
import logging
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("azal")

BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
AVIATIONSTACK_KEY = os.getenv("AVIATIONSTACK_KEY", "")
YANDEX_API_KEY    = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID  = os.getenv("YANDEX_FOLDER_ID", "")

ARRIVALS_URL   = "https://airport.az/ru/flights/arrivals/"
DEPARTURES_URL = "https://airport.az/ru/flights/departures/"
HEADERS        = {"User-Agent": "Mozilla/5.0 (Linux; Android 10)"}
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# ---------- парсинг airport.az ----------

def parse_board(url: str) -> list:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.error("fetch error %s: %s", url, e)
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    result = []
    for a in soup.select('a[href*="?flight="]'):
        raw = a.get_text(" ", strip=True)
        if len(raw) < 10:
            continue
        times  = re.findall(r'\b(\d{2}:\d{2})\b', raw)
        sched  = times[0] if times else ""
        actual = times[1] if len(times) > 1 else ""
        cm = re.search(r'\b([A-Z][A-Z0-9])\s?(\d{2,5})\b', raw)
        if not cm:
            continue
        airline, num = cm.group(1), cm.group(2)
        tm = re.search(r'Terminal\s*(\d)|T(\d)', raw, re.I)
        terminal = (tm.group(1) or tm.group(2)) if tm else "-"
        status = "-"
        for s in ["Прибыл","Отменен","Посадка","В пути","Ожидается","Вылетел","Задержан"]:
            if s in raw:
                status = s
                break
        cm2 = re.search(
            r'\d{1,2}\s+[А-Яа-яA-Za-z]+\s+(.+?)\s+' + re.escape(cm.group(0)), raw)
        city = cm2.group(1).strip() if cm2 else "-"
        result.append({
            "airline": airline, "number": num,
            "code": f"J{num}" if airline == "J2" else f"{airline}{num}",
            "city": city, "sched": sched, "actual": actual,
            "status": status, "terminal": terminal,
        })
    return result

def delay_min(sched, actual):
    if not sched or not actual:
        return None
    try:
        t1 = datetime.strptime(sched, "%H:%M")
        t2 = datetime.strptime(actual, "%H:%M")
        d  = int((t2 - t1).total_seconds() / 60)
        return d + 1440 if d < -120 else d
    except Exception:
        return None

# ---------- карточка рейса ----------

def build_card(f: dict) -> str:
    d         = delay_min(f["sched"], f["actual"])
    cancelled = "Отменен" in f["status"]
    arrived   = f["status"] in ("Прибыл", "Посадка")
    enroute   = f["status"] in ("В пути", "Ожидается")

    if cancelled:
        zaderjka  = "❌ рейс отменён"
        pribyl    = "❌ отменён"
        opozdanie = "—"
    elif arrived:
        zaderjka  = "да ⚠️" if d and d > 0 else "нет ✅"
        pribyl    = f"✅ {f['actual']}" if f["actual"] else "✅"
        opozdanie = f"+{d} мин" if d and d > 0 else "без опоздания"
    elif enroute:
        zaderjka  = "возможна ⚠️" if d and d > 0 else "нет ✅"
        pribyl    = f"🛫 в пути, ожид. {f['actual']}" if f["actual"] else "🛫 в пути"
        opozdanie = f"+{d} мин (ожид.)" if d and d > 0 else "по расписанию"
    else:
        zaderjka  = f"+{d} мин ⚠️" if d and d > 0 else "—"
        pribyl    = f["actual"] or "—"
        opozdanie = f"+{d} мин" if d else "—"

    term = f"Терминал {f['terminal']}" if f["terminal"] != "-" else "—"
    return (
        f"✈️ <b>Команда:</b> {f['code']}\n"
        f"🌍 <b>Направление:</b> {f['city']}\n"
        f"⏱ <b>Задержка:</b> {zaderjka}\n"
        f"🛬 <b>Прибыл:</b> {pribyl}\n"
        f"⚠️ <b>Опоздание:</b> {opozdanie}\n"
        f"🕐 <b>Время:</b> {f['sched']} (план)\n"
        f"🏢 <b>Терминал:</b> {term}"
    )

def short_line(f: dict) -> str:
    d  = delay_min(f["sched"], f["actual"])
    em = ("❌" if "Отменен" in f["status"] else
          "✅" if f["status"] in ("Прибыл","Посадка") else
          "⚠️" if d and d > 15 else "🛫")
    return f"{em} {f['code']}  {f['city']}  {f['sched']}"

# ---------- AviationStack ----------

def avstack(number: str):
    if not AVIATIONSTACK_KEY:
        return None
    try:
        r = requests.get(
            "http://api.aviationstack.com/v1/flights",
            params={"access_key": AVIATIONSTACK_KEY,
                    "flight_iata": f"J2{number}", "limit": 1},
            timeout=10)
        data = r.json().get("data", [])
        if not data:
            return None
        d   = data[0]
        arr = d.get("arrival", {})
        sched  = (arr.get("scheduled") or "")[:16].replace("T"," ")[:5]
        actual = (arr.get("actual") or arr.get("estimated") or "")
        actual = actual[:16].replace("T"," ")[:5] if actual else ""
        return {
            "airline": "J2", "number": number, "code": f"J{number}",
            "city": arr.get("airport","—"), "sched": sched, "actual": actual,
            "status": d.get("flight_status",""),
            "terminal": arr.get("terminal","-") or "-",
        }
    except Exception as e:
        log.warning("avstack: %s", e)
        return None

def find_flight(number: str):
    for f in parse_board(ARRIVALS_URL) + parse_board(DEPARTURES_URL):
        if f["number"] == number and f["airline"] == "J2":
            return f
    return avstack(number)

# ---------- YandexGPT ----------

def yandex_ask(question: str, ctx: str) -> str:
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        return "YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы в Railway Variables."

    system_text = (
        "Ты — помощник диспетчера аэропорта Гейдар Алиев (Баку, GYD). "
        "Отвечай коротко по-русски. Используй только данные ниже.\n\n"
        f"Рейсы AZAL сейчас:\n{ctx}"
    )
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID,
        "Content-Type": "application/json",
    }
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": "800",
        },
        "messages": [
            {"role": "system", "text": system_text},
            {"role": "user", "text": question},
        ],
    }
    try:
        r = requests.post(YANDEX_GPT_URL, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        result = r.json()
        return result["result"]["alternatives"][0]["message"]["text"].strip()
    except Exception as e:
        return f"Ошибка YandexGPT: {e}"

def flights_context() -> str:
    lines = []
    for tag, url in [("ПРИЛЁТ", ARRIVALS_URL), ("ВЫЛЕТ", DEPARTURES_URL)]:
        for f in parse_board(url):
            if f["airline"] != "J2":
                continue
            d  = delay_min(f["sched"], f["actual"])
            ds = f"+{d}мин" if d and d > 0 else "вовремя"
            lines.append(
                f"[{tag}] {f['code']} {f['city']} "
                f"план={f['sched']} факт={f['actual'] or '—'} "
                f"статус={f['status']} задержка={ds} терминал={f['terminal']}"
            )
    return "\n".join(lines) if lines else "Данных нет."

# ---------- клавиатуры ----------

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛬 Прилёт AZAL"), KeyboardButton(text="🛫 Вылет AZAL")],
        [KeyboardButton(text="⚠️ Задержки"),    KeyboardButton(text="🤖 Спросить AI")],
    ],
    resize_keyboard=True,
)

def flights_kb(flights: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=short_line(f), callback_data=f"f:{f['number']}")]
        for f in flights[:25]
    ])

# ---------- бот ----------

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp  = Dispatcher()
ai_wait: set = set()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "✈️ <b>AZAL Transit Bot</b>\n\n"
        "🛬 Прилёт AZAL — список прилётов\n"
        "🛫 Вылет AZAL — список вылетов\n"
        "⚠️ Задержки — опоздания и отмены\n"
        "🤖 Спросить AI — вопрос на живом языке\n\n"
        "Или отправь номер рейса: <code>278</code> или <code>J278</code>",
        reply_markup=main_menu,
    )

@dp.message(F.text == "🛬 Прилёт AZAL")
async def arrivals(message: Message):
    msg = await message.answer("⏳ Загружаю с airport.az…")
    fl = [f for f in parse_board(ARRIVALS_URL) if f["airline"] == "J2"]
    if not fl:
        await msg.edit_text("Рейсов AZAL на прилёт не найдено.")
        return
    await msg.edit_text(
        f"🛬 <b>Прилёты AZAL — {len(fl)} рейсов</b>",
        reply_markup=flights_kb(fl))

@dp.message(F.text == "🛫 Вылет AZAL")
async def departures(message: Message):
    msg = await message.answer("⏳ Загружаю с airport.az…")
    fl = [f for f in parse_board(DEPARTURES_URL) if f["airline"] == "J2"]
    if not fl:
        await msg.edit_text("Рейсов AZAL на вылет не найдено.")
        return
    await msg.edit_text(
        f"🛫 <b>Вылеты AZAL — {len(fl)} рейсов</b>",
        reply_markup=flights_kb(fl))

@dp.message(F.text == "⚠️ Задержки")
async def delays(message: Message):
    msg = await message.answer("⏳ Проверяю…")
    fl = (
        [f for f in parse_board(ARRIVALS_URL)   if f["airline"] == "J2"] +
        [f for f in parse_board(DEPARTURES_URL) if f["airline"] == "J2"]
    )
    delayed = [
        f for f in fl
        if "Отменен" in f["status"] or (delay_min(f["sched"], f["actual"]) or 0) > 15
    ]
    if not delayed:
        await msg.edit_text("✅ Задержанных и отменённых рейсов нет.")
        return
    await msg.edit_text("⚠️ <b>Задержки / отмены AZAL:</b>",
                        reply_markup=flights_kb(delayed))

@dp.message(F.text == "🤖 Спросить AI")
async def ask_ai_prompt(message: Message):
    ai_wait.add(message.from_user.id)
    await message.answer(
        "🤖 Задай вопрос о рейсах.\n"
        "Например: <i>Есть задержки?</i> или <i>J278 прибыл?</i>"
    )

@dp.callback_query(F.data.startswith("f:"))
async def flight_detail(callback: CallbackQuery):
    number = callback.data.split(":")[1]
    await callback.answer("Ищу…")
    f = find_flight(number)
    if f:
        await callback.message.answer(build_card(f))
    else:
        await callback.message.answer(
            f"❓ Рейс J{number} не найден.\n"
            f"Flightradar24: https://www.flightradar24.com/J2{number}"
        )

@dp.message(F.text.regexp(r'^[Jj]?2?\s?(\d{2,5})$'))
async def by_number(message: Message):
    m = re.search(r'(\d{2,5})$', message.text.strip())
    if not m:
        return
    number = m.group(1)
    msg = await message.answer(f"🔍 Ищу J{number}…")
    f = find_flight(number)
    if f:
        await msg.edit_text(build_card(f))
    else:
        await msg.edit_text(
            f"❓ Рейс J{number} не найден.\n"
            f"Flightradar24: https://www.flightradar24.com/J2{number}"
        )

@dp.message()
async def fallback(message: Message):
    uid = message.from_user.id
    if uid in ai_wait:
        ai_wait.discard(uid)
        msg = await message.answer("🤖 Думаю…")
        ctx    = flights_context()
        answer = yandex_ask(message.text, ctx)
        await msg.edit_text(f"🤖 <b>AI:</b>\n{answer}")
        return
    await message.answer(
        "Отправь номер рейса: <code>278</code> или <code>J278</code>",
        reply_markup=main_menu,
    )

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан!")
    log.info("starting…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
