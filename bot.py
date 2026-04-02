import os
import anthropic
from openai import OpenAI
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from tavily import TavilyClient

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

conversation_history = {}

async def search_web(query):
    try:
        result = tavily_client.search(query=query, max_results=5)
        texts = []
        for r in result.get("results", []):
            texts.append(f"- {r['title']}: {r['content'][:300]}")
        return "\n".join(texts)
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный помощник 🤖\n\n"
        "Могу искать информацию в интернете, 2ГИС, Яндекс картах.\n"
        "Пиши текстом или отправляй голосовые сообщения!"
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

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, update.message.text)

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    await update.message.reply_text("⏳ Думаю...")

    search_result = ""
    keywords = ["найди", "найти", "поиск", "где", "адрес", "телефон", "номер", 
                "2гис", "яндекс", "карта", "рядом", "ресторан", "кафе", "магазин",
                "ледовый", "дворец", "больница", "аптека", "школа", "км", "километр"]
    
    if any(word in text.lower() for word in keywords):
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
        
Если тебе предоставлены результаты поиска — используй их для ответа.
Когда даёшь список мест, организаций или контактов — форматируй красиво с номерами.
Будь конкретным и полезным. Используй эмодзи где уместно.""",
        messages=messages
    )

    assistant_message = response.content[0].text

    conversation_history[user_id].append({"role": "user", "content": text})
    conversation_history[user_id].append({"role": "assistant", "content": assistant_message})

    await update.message.reply_text(assistant_message)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен! Нажми Ctrl+C чтобы остановить.")
    app.run_polling()

if __name__ == "__main__":
    main()