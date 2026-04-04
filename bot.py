import os
import base64
import anthropic
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from tavily import TavilyClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
conversation_history = {}
bot_instance = None

def get_calendar_service():
    if not GOOGLE_CREDENTIALS:
        return None
    try:
       import base64 as b64
creds_data = json.loads(b64.b64decode(GOOGLE_CREDENTIALS).decode())
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

async def create_calendar_event(title, start_datetime, end_datetime=None, reminder_minutes=60):
    service = get_calendar_service()
    if not service:
        return "❌ Google Calendar не подключён"
    try:
        tz = pytz.timezone("Europe/Moscow")
        if isinstance(start_datetime, str):
            start_dt = tz.localize(datetime.strptime(start_datetime, "%Y-%m-%d %H:%M"))
        else:
            start_dt = start_datetime
        if end_datetime is None:
            from datetime import timedelta
            end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = end_datetime
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
        return f"✅ Событие добавлено в Google Calendar!\n📅 {title}\n⏰ {start_dt.strftime('%d.%m.%Y %H:%M')}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

async def send_reminder(chat_id, text):
    await bot_instance.send_message(chat_id=chat_id, text=f"⏰ Напоминание: {text}")

async def search_web(query):
    try:
        result = tavily_client.search(query=query, max_results=5)
        texts = []
        for r in result.get("results", []):
            texts.append(f"- {r['title']}: {r['content'][:300]}")
        return "\n".join(texts)
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

async def needs_search(text):
    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=10,
        system="Ты определяешь нужен ли поиск в интернете. Отвечай только YES или NO.",
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text.strip().upper() == "YES"

async def needs_image(text):
    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=10,
        system="Ты определяешь нужно ли генерировать картинку. Отвечай только YES или NO. YES если просят нарисовать, создать изображение, сгенерировать картинку.",
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text.strip().upper() == "YES"

async def parse_action(text):
    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=f"""Ты определяешь действие из текста. Текущее время: {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M')}
        
Если просят добавить событие в календарь — верни JSON:
{{"action": "calendar", "title": "название события", "datetime": "YYYY-MM-DD HH:MM", "reminder_minutes": 60}}

Если просят поставить напоминание — верни JSON:
{{"action": "reminder", "datetime": "YYYY-MM-DD HH:MM", "text": "текст напоминания"}}

Если ничего из вышеперечисленного — верни:
{{"action": "none"}}

Только JSON, без пояснений.""",
        messages=[{"role": "user", "content": text}]
    )
    try:
        return json.loads(response.content[0].text.strip())
    except:
        return {"action": "none"}

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный помощник 🤖\n\n"
        "Умею:\n"
        "🎙 Принимать голосовые сообщения\n"
        "🔍 Искать информацию в интернете\n"
        "🖼 Анализировать фотографии\n"
        "🎨 Генерировать картинки\n"
        "⏰ Ставить напоминания\n"
        "📅 Добавлять события в Google Calendar\n"
        "🔊 Отвечать голосом\n\n"
        "Пример: 'добавь в календарь встречу с остеопатом 9 апреля в 10:00, напомни за день'"
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎙 Слушаю...")
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    os.makedirs("voice_files", exist_ok=True)
    file_path = f"voice_files/{voice.file_id}.ogg"
    await file.download_to_drive(file_path)
    with open(file_path, "rb") as audio_file:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ru"
        )
    text = transcript.text
    await update.message.reply_text(f"🗣 Ты сказал: {text}")
    os.remove(file_path)
    await process_message(update, context, text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖼 Анализирую фото...")
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
    os.makedirs("voice_files", exist_ok=True)
    voice_path = f"voice_files/response_{update.message.from_user.id}.mp3"
    await text_to_voice(assistant_message, voice_path)
    with open(voice_path, "rb") as voice_file:
        await update.message.reply_voice(voice=voice_file)
    os.remove(voice_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, update.message.text)

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    await update.message.reply_text("⏳ Думаю...")

    action_data = await parse_action(text)

    if action_data.get("action") == "calendar":
        await update.message.reply_text("📅 Добавляю в Google Calendar...")
        result = await create_calendar_event(
            title=action_data["title"],
            start_datetime=action_data["datetime"],
            reminder_minutes=action_data.get("reminder_minutes", 60)
        )
        await update.message.reply_text(result)
        return

    if action_data.get("action") == "reminder":
        try:
            tz = pytz.timezone("Europe/Moscow")
            reminder_time = tz.localize(datetime.strptime(action_data["datetime"], "%Y-%m-%d %H:%M"))
            scheduler.add_job(
                send_reminder,
                trigger=DateTrigger(run_date=reminder_time),
                args=[chat_id, action_data["text"]]
            )
            await update.message.reply_text(f"✅ Напоминание установлено!\n⏰ {action_data['datetime']}\n📝 {action_data['text']}")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            return

    if await needs_image(text):
        await update.message.reply_text("🎨 Генерирую картинку...")
        try:
            image_url = await generate_image(text)
            await update.message.reply_photo(photo=image_url, caption="Вот твоя картинка! 🎨")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка генерации: {str(e)}")
        return

    search_result = ""
    if await needs_search(text):
        await update.message.reply_text("🔍 Ищу в интернете...")
        search_result = await search_web(text)

    messages = conversation_history[user_id].copy()
    user_content = text
    if search_result:
        user_content = f"{text}\n\nРезультаты поиска:\n{search_result}"
    messages.append({"role": "user", "content": user_content})
    if len(messages) > 20:
        messages = messages[-20:]

    response = anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system="""Ты личный помощник. Отвечай на русском языке.
Если тебе предоставлены результаты поиска — используй их.
Давай конкретные ответы. Используй эмодзи где уместно.""",
        messages=messages
    )
    assistant_message = response.content[0].text
    conversation_history[user_id].append({"role": "user", "content": text})
    conversation_history[user_id].append({"role": "assistant", "content": assistant_message})
    await update.message.reply_text(assistant_message)

    os.makedirs("voice_files", exist_ok=True)
    voice_path = f"voice_files/response_{user_id}.mp3"
    await text_to_voice(assistant_message, voice_path)
    with open(voice_path, "rb") as voice_file:
        await update.message.reply_voice(voice=voice_file)
    os.remove(voice_path)

def main():
    global bot_instance
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_instance = app.bot
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    async def start_scheduler(application):
        scheduler.start()

    app.post_init = start_scheduler
    print("Бот запущен! Нажми Ctrl+C чтобы остановить.")
    app.run_polling()

if __name__ == "__main__":
    main()
