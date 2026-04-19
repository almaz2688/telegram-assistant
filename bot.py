import os
import base64
import anthropic
import json
import sqlite3
import aiohttp
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from openai import OpenAI
from dotenv import load_dotenv
from telegram import Update, Bot, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from tavily import TavilyClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
import pytz
import random
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
bot_instance = None

DB_PATH = "/app/data/memory.db"

# Координаты Набережных Челнов
CHELNY_LAT = 55.7558
CHELNY_LON = 52.4261

# Домены для разных тематик поиска
SPORTS_DOMAINS = ["championat.com", "sports.ru", "khl.ru", "sport-express.ru", "matchtv.ru"]
NEWS_DOMAINS = ["ria.ru", "tass.ru", "rbc.ru", "lenta.ru", "iz.ru", "kommersant.ru"]
TECH_DOMAINS = ["techcrunch.com", "habr.com", "vc.ru", "wired.com", "theverge.com"]
CRYPTO_DOMAINS = ["coindesk.com", "cointelegraph.com", "decrypt.co", "bits.media", "cryptonews.com"]
REALTY_DOMAINS = ["cian.ru", "realty.rbc.ru", "bn.ru", "irn.ru", "domclick.ru"]
FINANCE_DOMAINS = ["rbc.ru", "banki.ru", "cbr.ru", "finance.mail.ru", "investing.com"]

DATE_KEYWORDS = [
    "сегодня", "today", "сейчас", "now", "играет", "матч", "матчи",
    "расписание", "результат", "счёт", "погода", "курс", "новости"
]

# Коды погоды WMO -> описание
WMO_CODES = {
    0: "ясно ☀️",
    1: "преимущественно ясно 🌤",
    2: "переменная облачность ⛅",
    3: "пасмурно ☁️",
    45: "туман 🌫",
    48: "туман с изморозью 🌫",
    51: "лёгкая морось 🌦",
    53: "морось 🌦",
    55: "сильная морось 🌧",
    61: "небольшой дождь 🌧",
    63: "дождь 🌧",
    65: "сильный дождь 🌧",
    71: "небольшой снег 🌨",
    73: "снег 🌨",
    75: "сильный снег ❄️",
    77: "снежные зёрна ❄️",
    80: "ливень 🌧",
    81: "ливни 🌧",
    82: "сильный ливень ⛈",
    85: "снегопад 🌨",
    86: "сильный снегопад ❄️",
    95: "гроза ⛈",
    96: "гроза с градом ⛈",
    99: "гроза с сильным градом ⛈",
}

ENTREPRENEUR_QUOTES = [
    ("Ваше время ограничено, не тратьте его, живя чужой жизнью.", "Стив Джобс"),
    ("Я убеждён, что примерно половина того, что отделяет успешных предпринимателей от неуспешных — это чистое упорство.", "Стив Джобс"),
    ("Инновация — это способность видеть изменения как возможность, а не угрозу.", "Стив Джобс"),
    ("Правило №1: никогда не теряй деньги. Правило №2: никогда не забывай правило №1.", "Уоррен Баффет"),
    ("Кто-то сидит в тени сегодня, потому что кто-то посадил дерево очень давно.", "Уоррен Баффет"),
    ("Лучше иметь примерную правоту, чем точную неправоту.", "Уоррен Баффет"),
    ("Цена — это то, что ты платишь. Ценность — это то, что ты получаешь.", "Уоррен Баффет"),
    ("Риск возникает тогда, когда вы не знаете, что делаете.", "Уоррен Баффет"),
    ("Предприниматель — это тот, кто прыгает со скалы и строит самолёт на лету.", "Рид Хоффман"),
    ("Если вас не смущает первая версия вашего продукта — вы запустили слишком поздно.", "Рид Хоффман"),
    ("Движение к успеху и движение к неудаче — не противоположности. Неудача — часть пути к успеху.", "Джефф Безос"),
    ("Если вы всегда делаете то, что всегда делали, то всегда будете получать то, что всегда получали.", "Джефф Безос"),
    ("Бренд — это то, что о вас говорят, когда вас нет в комнате.", "Джефф Безос"),
    ("Лучший способ предсказать будущее — создать его.", "Питер Друкер"),
    ("Менеджмент — это делать вещи правильно. Лидерство — это делать правильные вещи.", "Питер Друкер"),
    ("Результаты достигаются путём использования возможностей, а не решения проблем.", "Питер Друкер"),
    ("Единственный способ делать великую работу — любить то, что делаешь.", "Стив Джобс"),
    ("Высокие ожидания — ключ к всему.", "Сэм Уолтон"),
    ("Капитал — это не деньги. Это разум.", "Генри Форд"),
    ("Неудача — это просто возможность начать снова, но более умело.", "Генри Форд"),
    ("Если вы думаете, что можете, — вы правы. Если думаете, что не можете, — тоже правы.", "Генри Форд"),
    ("Деньги — плохой хозяин, но хороший слуга.", "Фрэнсис Бэкон"),
    ("Не бойтесь отказаться от хорошего ради великого.", "Джон Рокфеллер"),
    ("Дружба, основанная на бизнесе, лучше, чем бизнес, основанный на дружбе.", "Джон Рокфеллер"),
    ("Секрет успеха в постоянстве цели.", "Бенджамин Дизраэли"),
    ("Возможности умножаются по мере их использования.", "Сунь Цзы"),
    ("Победа любит подготовку.", "Наполеон Бонапарт"),
    ("Не ждите. Время никогда не будет идеальным.", "Наполеон Хилл"),
    ("За каждой удачей стоит много неудач.", "Илон Маск"),
    ("Когда что-то достаточно важно, вы делаете это, даже если шансы не в вашу пользу.", "Илон Маск"),
    ("Провал — это вариант. Если вы не терпите неудач, значит, вы недостаточно инновационны.", "Илон Маск"),
    ("Упорство — самое важное качество предпринимателя.", "Илон Маск"),
    ("Я всегда выбирал людей умнее себя.", "Ли Якокка"),
    ("Лучшие инвестиции — в себя.", "Бенджамин Франклин"),
    ("Знание — сила. Но применённое знание — это власть.", "Фрэнсис Бэкон"),
    ("Клиент всегда прав — особенно когда он уходит к конкурентам.", "Маршалл Филд"),
    ("Доверие строится годами, разрушается за минуты.", "Уоррен Баффет"),
    ("Я предпочитаю приблизительно правильный ответ, чем точно неправильный.", "Чарли Мангер"),
    ("Инвертируй, всегда инвертируй.", "Чарли Мангер"),
    ("Покупай страх, продавай жадность.", "Натан Ротшильд"),
    ("Человек, умирающий богатым, умирает опозоренным.", "Эндрю Карнеги"),
    ("Успех — это умение идти от неудачи к неудаче, не теряя энтузиазма.", "Уинстон Черчилль"),
    ("Сначала они тебя не замечают, потом смеются над тобой, потом борются с тобой. Потом ты побеждаешь.", "Махатма Ганди"),
    ("Стратегия без тактики — самый медленный путь к победе. Тактика без стратегии — шум перед поражением.", "Сунь Цзы"),
    ("Первое поколение зарабатывает, второе тратит, третье разоряется.", "Эндрю Карнеги"),
    ("В долгосрочной перспективе мы все мертвы. Действуй сейчас.", "Джон Мейнард Кейнс"),
    ("Не нанимайте людей, которым нужно управлять. Нанимайте тех, кто сам знает, что делать.", "Стив Джобс"),
    ("Самая опасная идея в бизнесе — думать, что вы знаете, чего хочет клиент.", "Питер Друкер"),
    ("Если хочешь идти быстро — иди один. Если хочешь идти далеко — иди вместе.", "Африканская пословица"),
    ("Не количество часов в работе, а количество работы в часах.", "Эштон Катчер"),
]

CAPABILITIES_TEXT = """🤖 ЧТО УМЕЕТ ТВОЙ ПОМОЩНИК

📅 КАЛЕНДАРЬ
• Добавить событие в Google Calendar
• Удалить событие из календаря
• Показать события на любую дату

⏰ НАПОМИНАНИЯ
• Одноразовые напоминания (в любое время)
• Повторяющиеся напоминания (каждый день, по дням недели, по числам)
• Управление списком напоминаний

🛒 СПИСОК ПОКУПОК
• Добавить товары в список
• Показать текущий список
• Удалить отдельный товар или очистить всё

👥 КОНТАКТЫ
• Сохранить контакт (имя, Telegram, телефон)
• Найти контакт по имени
• Показать всю книгу контактов
• Удалить контакт

💬 TELEGRAM-СООБЩЕНИЯ
• Написать сообщение контакту прямо сейчас
• Запланировать сообщение на нужное время

🔍 ПОИСК В ИНТЕРНЕТЕ
• Новости и актуальные события
• Погода в любом городе
• Курсы валют
• Спорт: расписание, результаты, счёт
• Любые вопросы требующие свежих данных

🖼 ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ
• Создать картинку по описанию (DALL-E 3)

🎤 ГОЛОС
• Принимать голосовые сообщения
• Отвечать голосом на любой запрос

📷 ФОТО
• Анализировать и описывать фотографии

☀️ УТРЕННИЙ БРИФИНГ (каждый день в 6:00)
• Календарь на день
• Погода в Челнах (Open-Meteo)
• Курсы валют ЦБ РФ (USD, EUR, KGS)
• 5 новостей: вайб-кодинг, ИИ, экономика, крипта, недвижимость
• Цитата великого предпринимателя

💬 УМНЫЙ РАЗГОВОР
• Отвечает на любые вопросы
• Помогает с текстами, идеями, анализом
• Помнит историю разговора"""

INSTRUCTIONS_TEXT = """📖 ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ

━━━━━━━━━━━━━━━━
📅 КАЛЕНДАРЬ

Добавить событие:
"Добавь встречу с партнёром 15 апреля в 14:00"
"Запиши врача на 20 апреля в 10 утра"

Посмотреть события:
"Что у меня запланировано на завтра?"
"Покажи события на 15 апреля"

Удалить событие:
"Удали встречу с партнёром 15 апреля"

━━━━━━━━━━━━━━━━
⏰ НАПОМИНАНИЯ

Одноразовое:
"Напомни позвонить маме в 18:00"
"Напомни про оплату счёта 30 апреля в 9:00"

Повторяющееся:
"Напоминай каждый день в 8:00 выпить воду"
"Каждую пятницу в 17:00 напоминай про отчёт"
"Каждое 1 число месяца в 10:00 — оплата аренды"

Управление:
/reminders — список всех напоминаний
"Удали напоминание #3"

━━━━━━━━━━━━━━━━
🛒 СПИСОК ПОКУПОК

"Добавь в список молоко, хлеб и яйца"
"Что у меня в списке покупок?"
"Удали молоко из списка"
"Очисти список покупок"
/shopping — быстро посмотреть список

━━━━━━━━━━━━━━━━
👥 КОНТАКТЫ

Добавить:
/contact Вася Петров @vasya 89991234567
"Сохрани контакт: Иван Иванов, телеграм @ivan"

Найти:
"Найди контакт Вася"
/contacts — все контакты

Удалить:
"Удали контакт Вася"

━━━━━━━━━━━━━━━━
💬 ОТПРАВКА СООБЩЕНИЙ

Сейчас:
"Напиши Васе: увидимся в 7 вечера"
"Отправь Ивану что встреча перенесена"

По расписанию:
"Напиши Васе завтра в 9 утра: доброе утро!"
"В пятницу в 18:00 отправь Ивану напоминание про встречу"

⚠️ Контакт должен быть сохранён заранее

━━━━━━━━━━━━━━━━
🔍 ПОИСК И ВОПРОСЫ

Просто пишите или говорите голосом:
"Какой курс доллара сегодня?"
"Кто играет в КХЛ сегодня?"
"Погода в Москве на выходные"
"Последние новости про биткоин"
"Объясни что такое вайб-кодинг"

━━━━━━━━━━━━━━━━
🎤 ГОЛОСОВЫЕ СООБЩЕНИЯ

Просто отправьте голосовое — помощник поймёт и ответит тоже голосом.

━━━━━━━━━━━━━━━━
📷 ФОТО

Отправьте фото (можно с подписью):
• Без подписи — опишет что на фото
• С подписью — ответит на ваш вопрос про фото

━━━━━━━━━━━━━━━━
🖼 КАРТИНКИ

"Нарисуй закат над горами"
"Сгенерируй логотип для кофейни"
"Создай изображение: офис будущего"

━━━━━━━━━━━━━━━━
⚙️ СЛУЖЕБНЫЕ КОМАНДЫ

/briefing — получить утренний брифинг прямо сейчас
/forget — очистить историю разговора
/help — что умеет помощник
/instructions — эта инструкция"""


# ─────────────────────────────────────────────
#  БД
# ─────────────────────────────────────────────

def init_db():
    os.makedirs("/app/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item TEXT,
            done INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            phone TEXT,
            notes TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS recurring_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            text TEXT,
            cron TEXT,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            message TEXT,
            send_at TEXT,
            sent INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_message(user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()


def get_history(user_id, limit=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


def clear_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def add_shopping_items(user_id, items):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for item in items:
        c.execute("INSERT INTO shopping_list (user_id, item) VALUES (?, ?)", (user_id, item.strip()))
    conn.commit()
    conn.close()


def get_shopping_list(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT item FROM shopping_list WHERE user_id=? AND done=0 ORDER BY id", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


def delete_shopping_item(user_id, item):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shopping_list WHERE user_id=? AND item LIKE ?", (user_id, f"%{item}%"))
    conn.commit()
    conn.close()


def clear_shopping_list(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shopping_list WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def save_contact(user_id, name, username=None, phone=None, notes=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM contacts WHERE user_id=? AND name LIKE ?", (user_id, f"%{name}%"))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE contacts SET username=?, phone=?, notes=? WHERE id=?",
                  (username, phone, notes, existing[0]))
    else:
        c.execute("INSERT INTO contacts (user_id, name, username, phone, notes) VALUES (?, ?, ?, ?, ?)",
                  (user_id, name, username, phone, notes))
    conn.commit()
    conn.close()


def find_contact(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, username, phone, notes FROM contacts WHERE user_id=? AND name LIKE ?",
              (user_id, f"%{name}%"))
    row = c.fetchone()
    conn.close()
    if row:
        return {"name": row[0], "username": row[1], "phone": row[2], "notes": row[3]}
    return None


def get_all_contacts(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, username, phone, notes FROM contacts WHERE user_id=? ORDER BY name", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"name": r[0], "username": r[1], "phone": r[2], "notes": r[3]} for r in rows]


def delete_contact(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM contacts WHERE user_id=? AND name LIKE ?", (user_id, f"%{name}%"))
    conn.commit()
    conn.close()


def save_recurring_reminder(user_id, chat_id, text, cron, description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO recurring_reminders (user_id, chat_id, text, cron, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, chat_id, text, cron, description)
    )
    reminder_id = c.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def get_recurring_reminders(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, text, cron, description FROM recurring_reminders WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "text": r[1], "cron": r[2], "description": r[3]} for r in rows]


def get_all_recurring_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, chat_id, text, cron FROM recurring_reminders")
    rows = c.fetchall()
    conn.close()
    return rows


def delete_recurring_reminder(user_id, reminder_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM recurring_reminders WHERE user_id=? AND id=?", (user_id, reminder_id))
    conn.commit()
    conn.close()


def save_scheduled_message(user_id, username, message, send_at):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO scheduled_messages (user_id, username, message, send_at) VALUES (?, ?, ?, ?)",
        (user_id, username, message, send_at)
    )
    msg_id = c.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def mark_scheduled_message_sent(msg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE scheduled_messages SET sent=1 WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  УМНЫЙ ПОИСК (только для новостей и спорта)
# ─────────────────────────────────────────────

async def search_web(query: str, include_domains: list = None, max_results: int = 5) -> str:
    try:
        kwargs = {"query": query, "max_results": max_results}
        if include_domains:
            kwargs["include_domains"] = include_domains
        result = tavily_client.search(**kwargs)
        texts = []
        for r in result.get("results", []):
            title = r.get("title", "")
            content = r.get("content", "")[:500]
            url = r.get("url", "")
            texts.append(f"[{title}]\n{content}\nИсточник: {url}")
        return "\n\n".join(texts) if texts else ""
    except Exception as e:
        print(f"search_web error: {e}")
        return ""


async def smart_search(user_text: str) -> str:
    tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(tz)
    now_str = now.strftime("%d.%m.%Y %H:%M")
    today_str = now.strftime("%d.%m.%Y")

    try:
        resp = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=200,
            system=f"""Сегодня {now_str} (московское время).
Определи, нужен ли поиск в интернете для ответа на сообщение пользователя.

Поиск НУЖЕН: новости, спорт (результаты/расписание/счёт/матчи), цены, афиша, любые актуальные данные.
Поиск НЕ НУЖЕН: погода (есть отдельный модуль), курсы валют (есть отдельный модуль), обычный разговор, написать текст/код, объяснения понятий, математика, личные вопросы.

Если поиск нужен — верни JSON:
{{"search": true, "query": "поисковый запрос", "topic": "sports|news|general"}}

Если поиск не нужен — верни JSON:
{{"search": false}}

Только JSON, без пояснений.""",
            messages=[{"role": "user", "content": user_text}]
        )
        data = json.loads(resp.content[0].text.strip())
    except Exception as e:
        print(f"smart_search decision error: {e}")
        return ""

    if not data.get("search"):
        return ""

    query = data.get("query", user_text)
    topic = data.get("topic", "general")

    text_lower = user_text.lower()
    if any(kw in text_lower for kw in DATE_KEYWORDS):
        query = f"{query} {today_str}"

    domain_map = {
        "sports": SPORTS_DOMAINS,
        "news": NEWS_DOMAINS,
    }
    domains = domain_map.get(topic)
    return await search_web(query, include_domains=domains)


# ─────────────────────────────────────────────
#  ПОГОДА — Open-Meteo (те же модели что iPhone)
# ─────────────────────────────────────────────

async def get_weather(lat: float = CHELNY_LAT, lon: float = CHELNY_LON, city_name: str = "Набережных Челнах") -> str:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,precipitation_probability,weathercode,windspeed_10m,apparent_temperature"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode,sunrise,sunset"
            f"&timezone=Europe%2FMoscow"
            f"&forecast_days=1"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()

        hourly = data["hourly"]
        times = hourly["time"]
        temps = hourly["temperature_2m"]
        feels = hourly["apparent_temperature"]
        precip = hourly["precipitation_probability"]
        codes = hourly["weathercode"]
        wind = hourly["windspeed_10m"]

        daily = data["daily"]
        t_max = daily["temperature_2m_max"][0]
        t_min = daily["temperature_2m_min"][0]
        day_code = daily["weathercode"][0]
        max_precip = daily["precipitation_probability_max"][0]

        def get_hour_idx(hour):
            target = f"T{hour:02d}:00"
            for i, t in enumerate(times):
                if t.endswith(target):
                    return i
            return 0

        morning_idx = get_hour_idx(8)
        afternoon_idx = get_hour_idx(14)
        evening_idx = get_hour_idx(20)

        def fmt_hour(idx):
            desc = WMO_CODES.get(int(codes[idx]), "")
            p = int(precip[idx])
            w = int(wind[idx])
            t = temps[idx]
            f = feels[idx]
            line = f"{t:+.0f}°C (ощущ. {f:+.0f}°C), {desc}, ветер {w} км/ч"
            if p > 20:
                line += f", осадки {p}%"
            return line

        day_desc = WMO_CODES.get(int(day_code), "")
        result = f"Погода в {city_name}:\n"
        result += f"🌅 Утро 08:00:  {fmt_hour(morning_idx)}\n"
        result += f"☀️ День 14:00:  {fmt_hour(afternoon_idx)}\n"
        result += f"🌆 Вечер 20:00: {fmt_hour(evening_idx)}\n"
        result += f"📊 День: макс {t_max:+.0f}°C / мин {t_min:+.0f}°C, {day_desc}"
        if max_precip > 20:
            result += f", осадки до {max_precip}%"
        return result

    except Exception as e:
        print(f"get_weather error: {e}")
        return "Погода недоступна"


# ─────────────────────────────────────────────
#  КУРСЫ ВАЛЮТ — официальный XML API ЦБ РФ
# ─────────────────────────────────────────────

async def get_currency() -> str:
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                content = await resp.read()

        # ЦБ РФ отдаёт XML в кодировке windows-1251
        xml_text = content.decode("windows-1251")
        root = ET.fromstring(xml_text)

        rates = {}
        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode").text
            value_str = valute.find("Value").text.replace(",", ".")
            nominal = int(valute.find("Nominal").text)

            if char_code in ("USD", "EUR", "KGS"):
                rate = float(value_str) / nominal
                rates[char_code] = rate

        date_str = root.attrib.get("Date", "")

        result = f"Курс ЦБ РФ на {date_str}:\n"
        result += f"USD: {rates.get('USD', 0):.2f} руб\n"
        result += f"EUR: {rates.get('EUR', 0):.2f} руб\n"
        result += f"KGS: {rates.get('KGS', 0):.4f} руб  (100 сом = {rates.get('KGS', 0) * 100:.2f} руб)"
        return result

    except Exception as e:
        print(f"get_currency error: {e}")
        return "Курсы недоступны"


# ─────────────────────────────────────────────
#  GOOGLE CALENDAR
# ─────────────────────────────────────────────

def get_calendar_service():
    if not GOOGLE_CREDENTIALS:
        return None
    try:
        creds_data = json.loads(base64.b64decode(GOOGLE_CREDENTIALS).decode())
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes")
        )
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"Calendar error: {e}")
        return None


async def get_today_events():
    service = get_calendar_service()
    if not service:
        return []
    try:
        tz = pytz.timezone("Europe/Moscow")
        now = datetime.now(tz)
        time_min = now.replace(hour=0, minute=0, second=0).isoformat()
        time_max = now.replace(hour=23, minute=59, second=59).isoformat()
        events = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        return events.get("items", [])
    except Exception as e:
        print(f"Calendar events error: {e}")
        return []


async def create_calendar_event(title, start_datetime, reminder_minutes=60):
    service = get_calendar_service()
    if not service:
        return "Google Calendar не подключён"
    try:
        tz = pytz.timezone("Europe/Moscow")
        if isinstance(start_datetime, str):
            start_dt = tz.localize(datetime.strptime(start_datetime, "%Y-%m-%d %H:%M"))
        else:
            start_dt = start_datetime
        end_dt = start_dt + timedelta(hours=1)
        event = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Moscow"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Moscow"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": reminder_minutes},
                    {"method": "popup", "minutes": 1440},
                ]
            }
        }
        event = service.events().insert(calendarId="primary", body=event).execute()
        return f"Событие добавлено в Google Calendar!\n{title}\n{start_dt.strftime('%d.%m.%Y %H:%M')}"
    except Exception as e:
        return f"Ошибка: {str(e)}"


async def delete_calendar_event(title, date):
    service = get_calendar_service()
    if not service:
        return "Google Calendar не подключён"
    try:
        tz = pytz.timezone("Europe/Moscow")
        date_dt = datetime.strptime(date, "%Y-%m-%d")
        time_min = tz.localize(date_dt).isoformat()
        time_max = tz.localize(date_dt.replace(hour=23, minute=59)).isoformat()
        events = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            q=title
        ).execute()
        items = events.get("items", [])
        if not items:
            return f"Событие не найдено: {title} на {date}"
        for item in items:
            service.events().delete(calendarId="primary", eventId=item["id"]).execute()
        return f"Событие удалено: {title}"
    except Exception as e:
        return f"Ошибка: {str(e)}"


async def list_calendar_events(date):
    service = get_calendar_service()
    if not service:
        return "Google Calendar не подключён"
    try:
        tz = pytz.timezone("Europe/Moscow")
        date_dt = datetime.strptime(date, "%Y-%m-%d")
        time_min = tz.localize(date_dt).isoformat()
        time_max = tz.localize(date_dt.replace(hour=23, minute=59)).isoformat()
        events = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        items = events.get("items", [])
        if not items:
            return f"На {date_dt.strftime('%d.%m.%Y')} событий нет"
        result = f"События на {date_dt.strftime('%d.%m.%Y')}:\n\n"
        for item in items:
            start = item["start"].get("dateTime", item["start"].get("date"))
            if "T" in start:
                dt = datetime.fromisoformat(start)
                if dt.tzinfo is None:
                    dt = tz.localize(dt)
                else:
                    dt = dt.astimezone(tz)
                start_time = dt.strftime("%H:%M")
            else:
                start_time = "весь день"
            result += f"{start_time} — {item['summary']}\n"
        return result
    except Exception as e:
        return f"Ошибка: {str(e)}"


# ─────────────────────────────────────────────
#  УТРЕННИЙ БРИФИНГ
# ─────────────────────────────────────────────

async def get_news_by_topic(topic_query: str, topic_label: str,
                            domains: list, today: str) -> str:
    try:
        raw = ""
        if domains:
            raw = await search_web(f"{topic_query} {today}", include_domains=domains, max_results=3)
        if not raw:
            raw = await search_web(f"{topic_query} {today}", max_results=3)
        if not raw:
            return f"Нет данных по теме: {topic_label}"
        response = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=120,
            system=f"Из текста выбери ОДНУ самую важную и свежую новость на тему «{topic_label}». "
                   f"Перескажи её одним ёмким предложением своими словами на русском языке. "
                   f"Только факт из текста — не додумывай. Без источников и ссылок.",
            messages=[{"role": "user", "content": raw}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"get_news_by_topic error ({topic_label}): {e}")
        return f"Нет данных по теме: {topic_label}"


async def get_five_news(today: str) -> dict:
    topics = [
        {
            "key": "vibe_coding",
            "label": "Вайб-кодинг",
            "query": "vibe coding AI programming tools cursor windsurf latest news",
            "domains": None,
            "emoji": "💻",
        },
        {
            "key": "ai",
            "label": "Искусственный интеллект",
            "query": "искусственный интеллект AI нейросети OpenAI Anthropic Google новости",
            "domains": TECH_DOMAINS + NEWS_DOMAINS,
            "emoji": "🤖",
        },
        {
            "key": "economy",
            "label": "Экономика",
            "query": "экономика мировая Россия рынки ставки ВВП новости",
            "domains": FINANCE_DOMAINS + NEWS_DOMAINS,
            "emoji": "📊",
        },
        {
            "key": "crypto",
            "label": "Криптовалюта",
            "query": "bitcoin ethereum crypto криптовалюта рынок новости",
            "domains": CRYPTO_DOMAINS,
            "emoji": "₿",
        },
        {
            "key": "realty",
            "label": "Недвижимость",
            "query": "недвижимость рынок жильё ипотека цены квартиры Россия новости",
            "domains": REALTY_DOMAINS + NEWS_DOMAINS,
            "emoji": "🏠",
        },
    ]
    results = {}
    for t in topics:
        news_text = await get_news_by_topic(
            topic_query=t["query"],
            topic_label=t["label"],
            domains=t["domains"],
            today=today,
        )
        results[t["key"]] = {"emoji": t["emoji"], "label": t["label"], "text": news_text}
    return results


async def send_morning_briefing(chat_id):
    try:
        tz = pytz.timezone("Europe/Moscow")
        now = datetime.now(tz)
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        day_name = days[now.weekday()]
        date_str = f"{now.day} {months[now.month - 1]} {now.year}"
        today_str = now.strftime("%d.%m.%Y")

        await bot_instance.send_message(chat_id=chat_id, text="Готовлю утренний брифинг...")

        events = await get_today_events()
        weather = await get_weather()        # Open-Meteo — без API ключа
        currency = await get_currency()      # ЦБ РФ XML — официальный
        five_news = await get_five_news(today_str)
        quote_text, quote_author = random.choice(ENTREPRENEUR_QUOTES)

        briefing = "☀️ Доброе утро, Алмаз!\n\n"
        briefing += f"📆 {day_name}, {date_str}\n"
        briefing += "━━━━━━━━━━━━━━━━\n\n"

        briefing += "📅 КАЛЕНДАРЬ НА СЕГОДНЯ:\n"
        if events:
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                if "T" in start:
                    dt = datetime.fromisoformat(start)
                    if dt.tzinfo is None:
                        dt = tz.localize(dt)
                    else:
                        dt = dt.astimezone(tz)
                    start_time = dt.strftime("%H:%M")
                else:
                    start_time = "весь день"
                briefing += f"  🕐 {start_time} — {event['summary']}\n"
        else:
            briefing += "  Событий нет\n"

        briefing += "\n🌤 ПОГОДА В ЧЕЛНАХ:\n"
        for line in weather.split("\n"):
            if line.strip():
                briefing += f"  {line}\n"

        briefing += "\n💰 КУРСЫ ВАЛЮТ (ЦБ РФ):\n"
        for line in currency.split("\n"):
            if line.strip():
                briefing += f"  {line}\n"

        briefing += "\n📰 НОВОСТИ:\n"
        for i, key in enumerate(["vibe_coding", "ai", "economy", "crypto", "realty"], start=1):
            item = five_news[key]
            briefing += f"\n  {i}. {item['emoji']} {item['label'].upper()}\n"
            briefing += f"  {item['text']}\n"

        briefing += "\n━━━━━━━━━━━━━━━━\n"
        briefing += f"💎 «{quote_text}»\n"
        briefing += f"    — {quote_author}"

        await bot_instance.send_message(chat_id=chat_id, text=briefing)
    except Exception as e:
        print(f"Briefing error: {e}")
        await bot_instance.send_message(chat_id=chat_id, text=f"Ошибка брифинга: {str(e)}")


# ─────────────────────────────────────────────
#  TELEGRAM USERBOT
# ─────────────────────────────────────────────

async def find_recipient(client, contact):
    if contact.get("username"):
        return contact["username"]
    if contact.get("phone"):
        try:
            result = await client(ImportContactsRequest([
                InputPhoneContact(client_id=0, phone=contact["phone"],
                                  first_name=contact["name"], last_name="")
            ]))
            if result.users:
                return result.users[0]
        except Exception as e:
            print(f"Phone lookup error: {e}")
    if contact.get("name"):
        try:
            name_lower = contact["name"].lower()
            async for dialog in client.iter_dialogs():
                if dialog.name and name_lower.split()[0] in dialog.name.lower():
                    return dialog.entity
        except Exception as e:
            print(f"Dialog lookup error: {e}")
    return None


async def send_telegram_userbot(contact_info, message):
    try:
        client = TelegramClient(StringSession(TELEGRAM_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return "UserBot не авторизован"
        recipient = await find_recipient(client, contact_info)
        if recipient is None:
            await client.disconnect()
            return f"Не удалось найти {contact_info.get('name')} в Telegram"
        await client.send_message(recipient, message)
        await client.disconnect()
        return f"Сообщение отправлено {contact_info.get('name')}"
    except Exception as e:
        return f"Ошибка: {str(e)}"


async def send_scheduled_message(msg_id, contact_info, message):
    await send_telegram_userbot(contact_info, message)
    mark_scheduled_message_sent(msg_id)


# ─────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ AI-ФУНКЦИИ
# ─────────────────────────────────────────────

async def parse_cron(text):
    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=100,
        system="""Преобразуй описание повторяющегося напоминания в cron выражение.
Формат cron: минуты часы день_месяца месяц день_недели
Примеры:
- каждый день в 9:00 -> 0 9 * * *
- каждый понедельник в 10:00 -> 0 10 * * 1
- каждое 1 число месяца в 12:00 -> 0 12 1 * *
- каждую пятницу в 18:00 -> 0 18 * * 5
Верни ТОЛЬКО cron выражение, без пояснений.""",
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text.strip()


async def parse_action(text, user_id):
    contacts = get_all_contacts(user_id)
    contacts_info = ""
    if contacts:
        contacts_info = "\n\nКнига контактов пользователя:\n"
        for c in contacts:
            contacts_info += f"- {c['name']}: username={c['username']}, телефон={c['phone']}\n"

    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        system=f"""Ты определяешь действие из текста. Текущее время: {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M')}{contacts_info}

Если просят добавить событие в календарь — верни JSON:
{{"action": "calendar", "title": "название события", "datetime": "YYYY-MM-DD HH:MM", "reminder_minutes": 60}}

Если просят удалить событие из календаря — верни JSON:
{{"action": "delete_calendar", "title": "название события", "date": "YYYY-MM-DD"}}

Если просят показать события календаря на дату — верни JSON:
{{"action": "list_calendar", "date": "YYYY-MM-DD"}}

Если просят поставить ОДНОРАЗОВОЕ напоминание — верни JSON:
{{"action": "reminder", "datetime": "YYYY-MM-DD HH:MM", "text": "текст напоминания"}}

Если просят поставить ПОВТОРЯЮЩЕЕСЯ напоминание — верни JSON:
{{"action": "recurring_reminder", "text": "текст напоминания", "description": "описание расписания"}}

Если просят показать повторяющиеся напоминания — верни JSON:
{{"action": "recurring_list"}}

Если просят удалить повторяющееся напоминание — верни JSON:
{{"action": "recurring_delete", "id": номер}}

Если просят добавить в список покупок — верни JSON:
{{"action": "shopping_add", "items": ["товар1", "товар2"]}}

Если просят показать список покупок — верни JSON:
{{"action": "shopping_list"}}

Если просят удалить товар из списка покупок — верни JSON:
{{"action": "shopping_delete", "item": "название товара"}}

Если просят очистить список покупок — верни JSON:
{{"action": "shopping_clear"}}

Если просят сохранить контакт — верни JSON:
{{"action": "contact_save", "name": "Имя Фамилия", "username": "@username", "phone": "номер", "notes": "заметки"}}

Если просят показать контакты — верни JSON:
{{"action": "contact_list"}}

Если просят найти контакт — верни JSON:
{{"action": "contact_find", "name": "имя"}}

Если просят удалить контакт — верни JSON:
{{"action": "contact_delete", "name": "имя"}}

Если просят написать сообщение кому-то ПРЯМО СЕЙЧАС — верни JSON:
{{"action": "send_telegram", "contact_name": "имя из книги контактов", "message": "текст сообщения"}}

Если просят написать сообщение кому-то В ОПРЕДЕЛЁННОЕ ВРЕМЯ — верни JSON:
{{"action": "send_telegram_scheduled", "contact_name": "имя из книги контактов", "message": "текст сообщения", "datetime": "YYYY-MM-DD HH:MM"}}

Если просят показать курс валют / курс доллара / курс евро / курс сома — верни JSON:
{{"action": "currency"}}

Если просят погоду (без уточнения города) — верни JSON:
{{"action": "weather_chelny"}}

Если просят погоду в конкретном городе — верни JSON:
{{"action": "weather_city", "city": "название города"}}

Если ничего из вышеперечисленного — верни:
{{"action": "none"}}

Только JSON, без пояснений.""",
        messages=[{"role": "user", "content": text}]
    )
    try:
        return json.loads(response.content[0].text.strip())
    except Exception:
        return {"action": "none"}


async def needs_image(text):
    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=10,
        system="Ты определяешь нужно ли генерировать картинку. Отвечай только YES или NO. "
               "YES если просят нарисовать, создать изображение, сгенерировать картинку.",
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text.strip().upper() == "YES"


async def generate_image(prompt):
    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return response.data[0].url


async def text_to_voice(text, file_path):
    clean_text = text.replace("**", "").replace("##", "").replace("#", "").replace("*", "")
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=clean_text[:4000]
    )
    response.stream_to_file(file_path)


async def send_reminder(chat_id, text):
    await bot_instance.send_message(chat_id=chat_id, text=f"⏰ Напоминание: {text}")


# ─────────────────────────────────────────────
#  ГЕОКОДИРОВАНИЕ ГОРОДА (для погоды по запросу)
# ─────────────────────────────────────────────

async def geocode_city(city: str):
    """Возвращает (lat, lon, display_name) или None."""
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=ru&format=json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        return r["latitude"], r["longitude"], r.get("name", city)
    except Exception as e:
        print(f"geocode_city error: {e}")
        return None


# ─────────────────────────────────────────────
#  КОМАНДЫ БОТА
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await update.message.reply_text(
        f"Привет! Я твой личный помощник 🤖\n\n"
        f"Твой chat_id: {chat_id}\n\n"
        "Быстрые команды:\n"
        "/help — что умею\n"
        "/instructions — как пользоваться\n"
        "/contact Имя @username телефон — добавить контакт\n"
        "/contacts — все контакты\n"
        "/shopping — список покупок\n"
        "/reminders — напоминания\n"
        "/briefing — утренний брифинг\n"
        "/forget — очистить историю\n\n"
        "Или просто пиши / говори голосом что нужно сделать!"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(CAPABILITIES_TEXT)


async def cmd_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(INSTRUCTIONS_TEXT)


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await update.message.reply_text("Готовлю брифинг...")
    await send_morning_briefing(chat_id)


async def cmd_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "Использование:\n"
            "/contact Имя Фамилия @username телефон\n\n"
            "Примеры:\n"
            "/contact Вася Петров @vasya 89991234567\n"
            "/contact Вася Петров @vasya\n"
            "/contact Вася Петров 89991234567"
        )
        return

    name_parts, username, phone = [], None, None
    for arg in args:
        if arg.startswith("@"):
            username = arg
        elif arg.startswith("8") and len(arg) >= 10 and arg[1:].isdigit():
            phone = arg
        elif arg.startswith("+7") and len(arg) >= 11:
            phone = arg
        else:
            name_parts.append(arg)

    name = " ".join(name_parts) if name_parts else None
    if not name:
        await update.message.reply_text("Укажите имя контакта")
        return

    save_contact(user_id, name, username, phone)
    result = f"Контакт сохранён: {name}"
    if username:
        result += f"\nTelegram: {username}"
    if phone:
        result += f"\nТелефон: {phone}"
    await update.message.reply_text(result)


async def cmd_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    contacts = get_all_contacts(user_id)
    if not contacts:
        await update.message.reply_text("Книга контактов пуста\n\nДобавьте: /contact Имя @username")
        return
    result = "Ваши контакты:\n\n"
    for c in contacts:
        result += f"{c['name']}\n"
        if c['username']:
            result += f"   Telegram: {c['username']}\n"
        if c['phone']:
            result += f"   Телефон: {c['phone']}\n"
        if c['notes']:
            result += f"   Заметки: {c['notes']}\n"
        result += "\n"
    await update.message.reply_text(result)


async def cmd_shopping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    items = get_shopping_list(user_id)
    if not items:
        await update.message.reply_text("Список покупок пуст")
        return
    await update.message.reply_text("Список покупок:\n\n" + "\n".join(f"- {i}" for i in items))


async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reminders = get_recurring_reminders(user_id)
    if not reminders:
        await update.message.reply_text("Повторяющихся напоминаний нет")
        return
    result = "Повторяющиеся напоминания:\n\n"
    for r in reminders:
        result += f"#{r['id']} — {r['description']}\n{r['text']}\n\n"
    result += "Для удаления скажите: удали напоминание #номер"
    await update.message.reply_text(result)


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    clear_history(user_id)
    await update.message.reply_text("История разговора очищена!")


# ─────────────────────────────────────────────
#  ОБРАБОТКА СООБЩЕНИЙ
# ─────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Слушаю...")
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    os.makedirs("voice_files", exist_ok=True)
    file_path = f"voice_files/{voice.file_id}.ogg"
    await file.download_to_drive(file_path)
    with open(file_path, "rb") as audio_file:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="ru"
        )
    text = transcript.text
    await update.message.reply_text(f"Ты сказал: {text}")
    os.remove(file_path)
    await process_message(update, context, text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Анализирую фото...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    os.makedirs("voice_files", exist_ok=True)
    file_path = f"voice_files/{photo.file_id}.jpg"
    await file.download_to_drive(file_path)
    with open(file_path, "rb") as image_file:
        image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")
    os.remove(file_path)
    caption = update.message.caption or "Что на этом фото? Опиши подробно."
    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="Ты личный помощник. Отвечай на русском языке.",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": caption}
            ]
        }]
    )
    assistant_message = response.content[0].text
    await update.message.reply_text(assistant_message)
    voice_path = f"voice_files/response_{update.message.from_user.id}.mp3"
    try:
        await text_to_voice(assistant_message, voice_path)
        with open(voice_path, "rb") as vf:
            await update.message.reply_voice(voice=vf)
        os.remove(voice_path)
    except Exception as e:
        print(f"TTS error: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, update.message.text)


async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    await update.message.reply_text("Думаю...")

    action_data = await parse_action(text, user_id)

    if action_data.get("action") == "calendar":
        await update.message.reply_text("Добавляю в Google Calendar...")
        result = await create_calendar_event(
            title=action_data["title"],
            start_datetime=action_data["datetime"],
            reminder_minutes=action_data.get("reminder_minutes", 60)
        )
        await update.message.reply_text(result)
        return

    if action_data.get("action") == "delete_calendar":
        await update.message.reply_text("Удаляю из Google Calendar...")
        result = await delete_calendar_event(title=action_data["title"], date=action_data["date"])
        await update.message.reply_text(result)
        return

    if action_data.get("action") == "list_calendar":
        await update.message.reply_text("Смотрю календарь...")
        result = await list_calendar_events(date=action_data["date"])
        await update.message.reply_text(result)
        return

    if action_data.get("action") == "reminder":
        try:
            tz = pytz.timezone("Europe/Moscow")
            reminder_time = tz.localize(datetime.strptime(action_data["datetime"], "%Y-%m-%d %H:%M"))
            scheduler.add_job(send_reminder, trigger=DateTrigger(run_date=reminder_time),
                              args=[chat_id, action_data["text"]])
            await update.message.reply_text(
                f"⏰ Напоминание установлено!\n{action_data['datetime']}\n{action_data['text']}"
            )
            return
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {str(e)}")
            return

    if action_data.get("action") == "recurring_reminder":
        try:
            cron = await parse_cron(action_data["description"])
            reminder_id = save_recurring_reminder(
                user_id, chat_id, action_data["text"], cron, action_data["description"]
            )
            cron_parts = cron.split()
            scheduler.add_job(
                send_reminder,
                trigger=CronTrigger(
                    minute=cron_parts[0], hour=cron_parts[1],
                    day=cron_parts[2], month=cron_parts[3],
                    day_of_week=cron_parts[4], timezone="Europe/Moscow"
                ),
                args=[chat_id, action_data["text"]],
                id=f"recurring_{reminder_id}"
            )
            await update.message.reply_text(
                f"🔁 Повторяющееся напоминание установлено!\n"
                f"{action_data['description']}\n{action_data['text']}\nID: {reminder_id}"
            )
            return
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {str(e)}")
            return

    if action_data.get("action") == "recurring_list":
        reminders = get_recurring_reminders(user_id)
        if not reminders:
            await update.message.reply_text("Повторяющихся напоминаний нет")
        else:
            result = "Повторяющиеся напоминания:\n\n"
            for r in reminders:
                result += f"#{r['id']} — {r['description']}\n{r['text']}\n\n"
            await update.message.reply_text(result)
        return

    if action_data.get("action") == "recurring_delete":
        reminder_id = action_data.get("id")
        delete_recurring_reminder(user_id, reminder_id)
        try:
            scheduler.remove_job(f"recurring_{reminder_id}")
        except Exception:
            pass
        await update.message.reply_text(f"Напоминание #{reminder_id} удалено!")
        return

    if action_data.get("action") == "shopping_add":
        items = action_data.get("items", [])
        add_shopping_items(user_id, items)
        await update.message.reply_text("Добавлено в список покупок:\n" + "\n".join(f"- {i}" for i in items))
        return

    if action_data.get("action") == "shopping_list":
        items = get_shopping_list(user_id)
        if not items:
            await update.message.reply_text("Список покупок пуст")
        else:
            await update.message.reply_text("Список покупок:\n\n" + "\n".join(f"- {i}" for i in items))
        return

    if action_data.get("action") == "shopping_delete":
        delete_shopping_item(user_id, action_data["item"])
        await update.message.reply_text(f"Удалено из списка: {action_data['item']}")
        return

    if action_data.get("action") == "shopping_clear":
        clear_shopping_list(user_id)
        await update.message.reply_text("Список покупок очищен!")
        return

    if action_data.get("action") == "contact_save":
        save_contact(user_id, name=action_data.get("name"), username=action_data.get("username"),
                     phone=action_data.get("phone"), notes=action_data.get("notes"))
        await update.message.reply_text(f"Контакт сохранён: {action_data.get('name')}")
        return

    if action_data.get("action") == "contact_list":
        contacts = get_all_contacts(user_id)
        if not contacts:
            await update.message.reply_text("Книга контактов пуста")
        else:
            result = "Ваши контакты:\n\n"
            for c in contacts:
                result += f"{c['name']}\n"
                if c['username']:
                    result += f"   Telegram: {c['username']}\n"
                if c['phone']:
                    result += f"   Телефон: {c['phone']}\n"
                if c['notes']:
                    result += f"   Заметки: {c['notes']}\n"
                result += "\n"
            await update.message.reply_text(result)
        return

    if action_data.get("action") == "contact_find":
        contact = find_contact(user_id, action_data.get("name"))
        if not contact:
            await update.message.reply_text(f"Контакт не найден: {action_data.get('name')}")
        else:
            result = f"{contact['name']}\n"
            if contact['username']:
                result += f"Telegram: {contact['username']}\n"
            if contact['phone']:
                result += f"Телефон: {contact['phone']}\n"
            if contact['notes']:
                result += f"Заметки: {contact['notes']}\n"
            await update.message.reply_text(result)
        return

    if action_data.get("action") == "contact_delete":
        delete_contact(user_id, action_data.get("name"))
        await update.message.reply_text(f"Контакт удалён: {action_data.get('name')}")
        return

    if action_data.get("action") == "send_telegram":
        contact_name = action_data.get("contact_name")
        message = action_data.get("message")
        contact = find_contact(user_id, contact_name)
        if not contact:
            await update.message.reply_text(f"Контакт не найден: {contact_name}\nДобавьте через /contact")
            return
        await update.message.reply_text(f"Отправляю сообщение {contact['name']}...")
        result = await send_telegram_userbot(contact, message)
        await update.message.reply_text(f"{result}\n\nТекст:\n{message}")
        return

    if action_data.get("action") == "send_telegram_scheduled":
        contact_name = action_data.get("contact_name")
        message = action_data.get("message")
        send_at = action_data.get("datetime")
        contact = find_contact(user_id, contact_name)
        if not contact:
            await update.message.reply_text(f"Контакт не найден: {contact_name}\nДобавьте через /contact")
            return
        try:
            tz = pytz.timezone("Europe/Moscow")
            send_time = tz.localize(datetime.strptime(send_at, "%Y-%m-%d %H:%M"))
            msg_id = save_scheduled_message(user_id, contact_name, message, send_at)
            scheduler.add_job(send_scheduled_message, trigger=DateTrigger(run_date=send_time),
                              args=[msg_id, contact, message], id=f"scheduled_msg_{msg_id}")
            await update.message.reply_text(
                f"📅 Сообщение запланировано!\nКому: {contact['name']}\nКогда: {send_at}\nТекст:\n{message}"
            )
            return
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {str(e)}")
            return

    # ── Курс валют — прямо с ЦБ РФ ──
    if action_data.get("action") == "currency":
        await update.message.reply_text("Запрашиваю курс ЦБ РФ...")
        result = await get_currency()
        await update.message.reply_text(result)
        return

    # ── Погода в Челнах ──
    if action_data.get("action") == "weather_chelny":
        await update.message.reply_text("Получаю погоду...")
        result = await get_weather()
        await update.message.reply_text(result)
        return

    # ── Погода в произвольном городе ──
    if action_data.get("action") == "weather_city":
        city = action_data.get("city", "")
        await update.message.reply_text(f"Получаю погоду для {city}...")
        geo = await geocode_city(city)
        if not geo:
            await update.message.reply_text(f"Не удалось найти город: {city}")
            return
        lat, lon, display_name = geo
        result = await get_weather(lat=lat, lon=lon, city_name=display_name)
        await update.message.reply_text(result)
        return

    # ── Генерация изображения ──
    if await needs_image(text):
        await update.message.reply_text("Генерирую картинку...")
        try:
            image_url = await generate_image(text)
            await update.message.reply_photo(photo=image_url, caption="Вот твоя картинка!")
        except Exception as e:
            await update.message.reply_text(f"Ошибка генерации: {str(e)}")
        return

    # ── Умный поиск (новости, спорт) ──
    search_result = await smart_search(text)
    if search_result:
        await update.message.reply_text("🔍 Нашёл информацию, формирую ответ...")

    # ── Ответ Claude ──
    tz = pytz.timezone("Europe/Moscow")
    now_str = datetime.now(tz).strftime("%d.%m.%Y %H:%M")

    if search_result:
        system_prompt = (
            f"Ты личный помощник. Отвечай на русском языке.\n"
            f"Сейчас {now_str} МСК.\n\n"
            f"ПРАВИЛО: Отвечай СТРОГО на основе результатов поиска из сообщения.\n"
            f"ЗАПРЕЩЕНО додумывать команды, счета, цены, даты и любые конкретные факты.\n"
            f"Если нужных данных в поиске нет — честно скажи об этом.\n"
            f"Используй эмодзи где уместно."
        )
        user_content = (
            f"Вопрос: {text}\n\n"
            f"=== РЕЗУЛЬТАТЫ ПОИСКА (отвечай только на их основе) ===\n"
            f"{search_result}\n"
            f"======================================================="
        )
    else:
        system_prompt = (
            f"Ты личный помощник. Отвечай на русском языке.\n"
            f"Сейчас {now_str} МСК.\n"
            f"Давай конкретные ответы. Используй эмодзи где уместно."
        )
        user_content = text

    history = get_history(user_id)
    history.append({"role": "user", "content": user_content})

    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=history
    )
    assistant_message = response.content[0].text

    save_message(user_id, "user", text)
    save_message(user_id, "assistant", assistant_message)

    await update.message.reply_text(assistant_message)

    # ── Голосовой ответ ──
    os.makedirs("voice_files", exist_ok=True)
    voice_path = f"voice_files/response_{user_id}.mp3"
    try:
        await text_to_voice(assistant_message, voice_path)
        with open(voice_path, "rb") as vf:
            await update.message.reply_voice(voice=vf)
        os.remove(voice_path)
    except Exception as e:
        print(f"TTS error: {e}")


# ─────────────────────────────────────────────
#  ЗАПУСК
# ─────────────────────────────────────────────

def main():
    global bot_instance
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_instance = app.bot

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("instructions", cmd_instructions))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("contact", cmd_contact))
    app.add_handler(CommandHandler("contacts", cmd_contacts))
    app.add_handler(CommandHandler("shopping", cmd_shopping))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def on_startup(application):
        scheduler.start()
        for row in get_all_recurring_reminders():
            reminder_id, user_id, chat_id, text, cron = row
            try:
                cron_parts = cron.split()
                scheduler.add_job(
                    send_reminder,
                    trigger=CronTrigger(
                        minute=cron_parts[0], hour=cron_parts[1],
                        day=cron_parts[2], month=cron_parts[3],
                        day_of_week=cron_parts[4], timezone="Europe/Moscow"
                    ),
                    args=[chat_id, text],
                    id=f"recurring_{reminder_id}"
                )
            except Exception as e:
                print(f"Error loading reminder {reminder_id}: {e}")

        if MY_CHAT_ID:
            scheduler.add_job(
                send_morning_briefing,
                trigger=CronTrigger(hour=6, minute=0, timezone="Europe/Moscow"),
                args=[int(MY_CHAT_ID)],
                id="morning_briefing"
            )
            print("Утренний брифинг запланирован на 6:00 МСК")

        await application.bot.set_my_commands([
            BotCommand("start", "Главное меню"),
            BotCommand("help", "Что умеет помощник"),
            BotCommand("instructions", "Инструкция по использованию"),
            BotCommand("contact", "Добавить контакт"),
            BotCommand("contacts", "Все контакты"),
            BotCommand("shopping", "Список покупок"),
            BotCommand("reminders", "Повторяющиеся напоминания"),
            BotCommand("briefing", "Утренний брифинг сейчас"),
            BotCommand("forget", "Очистить историю"),
        ])

    app.post_init = on_startup
    print("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
