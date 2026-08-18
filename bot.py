import os
import io
import re
import logging
import asyncio
from typing import Optional
from collections import defaultdict
import time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from google import genai
from google.genai import types

# ---------- تنظیمات ----------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

MODEL_NAME = "gemini-3.5-flash"
SYSTEM_PROMPT = "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به فارسی و روان پاسخ می‌دهی."
MAX_HISTORY = 10
MAX_RETRIES = 3

client = genai.Client(api_key=GEMINI_API_KEY)
chat_config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)

# ---------- لاگ با فیلتر توکن ----------
class TokenFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(
            r'bot\d+:[A-Za-z0-9_-]+', 
            '[TOKEN_REDACTED]', 
            str(record.msg)
        )
        return True

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.addFilter(TokenFilter())

# ---------- حافظه و مدیریت ----------
user_sessions: dict[int, "genai.chats.Chat"] = {}
user_last_message: dict[int, float] = {}

def new_chat():
    return client.chats.create(model=MODEL_NAME, config=chat_config)

def get_session(chat_id: int):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = new_chat()
    return user_sessions[chat_id]

def trim_history(chat_id: int):
    session = user_sessions.get(chat_id)
    if session is None:
        return
    history = session.get_history()
    if len(history) > MAX_HISTORY * 2:
        trimmed = history[-MAX_HISTORY * 2:]
        user_sessions[chat_id] = client.chats.create(
            model=MODEL_NAME, config=chat_config, history=trimmed
        )

# ---------- Retry برای 429 ----------
async def send_with_retry(session, message, max_retries=MAX_RETRIES) -> Optional[str]:
    for attempt in range(max_retries):
        try:
            response = session.send_message(message)
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and "retryDelay" in error_str:
                import re
                match = re.search(r'retryDelay":\s*"(\d+)s', error_str)
                wait_time = int(match.group(1)) if match else (2 ** attempt)
                logger.warning(f"Rate limit, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            elif "429" in error_str:
                wait_time = 2 ** attempt
                logger.warning(f"Rate limit (no delay), waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            else:
                raise
    return None

# ---------- دستورات ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = new_chat()
    await update.message.reply_text(
        "سلام! 👋\n"
        "متن یا عکس بفرست تا باهاش صحبت کنم.\n"
        "برای پاک کردن حافظه‌ی مکالمه: /reset"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = new_chat()
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد. ✅")

# ---------- پیام‌های متنی ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # محدودیت نرخ
    now = time.time()
    if chat_id in user_last_message:
        if now - user_last_message[chat_id] < 1.5:
            await update.message.reply_text("⚠️ لطفاً کمی صبر کن بین پیام‌ها.")
            return
    user_last_message[chat_id] = now
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        session = get_session(chat_id)
        answer = await send_with_retry(session, update.message.text)
        
        if answer is None:
            answer = "❌ سقف استفاده روزانه پر شده. چند ساعت بعد تلاش کن."
        else:
            trim_history(chat_id)
    except Exception as e:
        logger.error(f"Gemini text error: {e}")
        answer = "❌ مشکلی در ارتباط با هوش مصنوعی پیش اومد."

    await update.message.reply_text(answer)

# ---------- پیام‌های عکس ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # محدودیت حجم
    photo = update.message.photo[-1]
    if photo.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ حجم عکس بیشتر از ۲۰ مگابایت است.")
        return
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        tg_file = await photo.get_file()
        image_bytes = bytes(await tg_file.download_as_bytearray())
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        
        caption = update.message.caption
        if not caption:
            caption = "این عکس رو توضیح بده."

        session = get_session(chat_id)
        answer = await send_with_retry(session, [caption, image_part])
        
        if answer is None:
            answer = "❌ سقف استفاده روزانه پر شده. چند ساعت بعد تلاش کن."
        else:
            trim_history(chat_id)
    except Exception as e:
        logger.error(f"Gemini image error: {e}")
        answer = "❌ مشکلی در پردازش عکس پیش اومد."

    await update.message.reply_text(answer)

# ---------- Error Handler ----------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ خطایی رخ داد. لطفاً دوباره تلاش کن."
        )

# ---------- اجرای ربات ----------
async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(error_handler)
    
    # حذف webhook برای جلوگیری از Conflict
    await app.bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("ربات در حال اجراست...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
