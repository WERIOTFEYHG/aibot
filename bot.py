"""
ربات تلگرامی هوش مصنوعی با Google Gemini (رایگان)
- متن و عکس هر دو با یک مدل (Gemini) پردازش می‌شن، نیازی به دو تا سرویس جدا نیست.

مدل: gemini-2.0-flash (سریع، رایگان با محدودیت نرخ در حد کافی برای یک ربات شخصی)

روی Railway:
    1) این فایل را با نام bot.py در ریپازیتوری بگذارید (کنار requirements.txt و Procfile).
    2) در بخش Variables پروژه‌ی Railway دو متغیر زیر را ست کنید:
       TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
    3) Start Command: python bot.py

کلید رایگان Gemini از اینجا بگیرید: https://aistudio.google.com/apikey
توکن تلگرام از @BotFather بگیرید.
"""

import os
import io
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from PIL import Image
import google.generativeai as genai

# ---------- تنظیمات ----------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

MODEL_NAME = "gemini-2.0-flash"
SYSTEM_PROMPT = "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به فارسی و روان پاسخ می‌دهی."
MAX_HISTORY = 10  # تعداد پیام‌های اخیر هر کاربر که در حافظه نگه می‌داریم

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# حافظه‌ی مکالمه‌ی هر کاربر: chat_id -> Gemini ChatSession
user_sessions: dict[int, "genai.ChatSession"] = {}


def get_session(chat_id: int) -> "genai.ChatSession":
    if chat_id not in user_sessions:
        user_sessions[chat_id] = model.start_chat(history=[])
    return user_sessions[chat_id]


def trim_history(chat_id: int):
    """جلوگیری از رشد بی‌حد تاریخچه‌ی مکالمه."""
    session = user_sessions.get(chat_id)
    if session and len(session.history) > MAX_HISTORY * 2:
        session.history = session.history[-MAX_HISTORY * 2 :]


# ---------- دستورات ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_chat.id] = model.start_chat(history=[])
    await update.message.reply_text(
        "سلام! 👋\n"
        "متن یا عکس بفرست تا باهاش صحبت کنم.\n"
        "برای پاک کردن حافظه‌ی مکالمه: /reset"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_chat.id] = model.start_chat(history=[])
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد. ✅")


# ---------- پیام‌های متنی ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        session = get_session(chat_id)
        response = session.send_message(update.message.text)
        answer = response.text
        trim_history(chat_id)
    except Exception as e:
        logger.error(f"Gemini text error: {e}")
        answer = "❌ مشکلی در ارتباط با هوش مصنوعی پیش اومد. دوباره امتحان کن."

    await update.message.reply_text(answer)


# ---------- پیام‌های عکس ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        photo = update.message.photo[-1]  # بزرگ‌ترین سایز
        tg_file = await photo.get_file()
        image_bytes = bytes(await tg_file.download_as_bytearray())
        image = Image.open(io.BytesIO(image_bytes))

        caption = update.message.caption or "این عکس رو توضیح بده."

        session = get_session(chat_id)
        response = session.send_message([caption, image])
        answer = response.text
        trim_history(chat_id)
    except Exception as e:
        logger.error(f"Gemini image error: {e}")
        answer = "❌ مشکلی در پردازش عکس پیش اومد. دوباره امتحان کن."

    await update.message.reply_text(answer)


# ---------- اجرای ربات ----------
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
