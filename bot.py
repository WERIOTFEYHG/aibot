import os
import logging
from groq import Groq
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده است.")
if not GROQ_API_KEY:
    raise RuntimeError("متغیر محیطی GROQ_API_KEY تنظیم نشده است.")

groq_client = Groq(api_key=GROQ_API_KEY)

# هر کاربر یک تاریخچه‌ی کوتاه مکالمه دارد (در حافظه، نه دیتابیس)
user_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 10  # تعداد پیام‌های نگه‌داشته‌شده برای هر کاربر

SYSTEM_PROMPT = (
    "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به زبان فارسی پاسخ می‌دهی، "
    "مگر اینکه کاربر به زبان دیگری بنویسد."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "سلام! من یه ربات هوش مصنوعی هستم 🤖\n"
        "هر سوالی داری بپرس تا جواب بدم.\n"
        "برای پاک کردن حافظه‌ی مکالمه از /reset استفاده کن."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد ✅")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text

    history = user_histories.setdefault(user_id, [])
    history.append({"role": "user", "content": user_text})
    history[:] = history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        reply_text = response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001
        logger.exception("Groq API error")
        reply_text = f"مشکلی پیش اومد، دوباره امتحان کن.\n(خطا: {exc})"

    history.append({"role": "assistant", "content": reply_text})
    history[:] = history[-MAX_HISTORY:]

    await update.message.reply_text(reply_text)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
