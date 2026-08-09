import os
import sys
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# بررسی نصب بودن پکیج‌های لازم - قبل از هر کار دیگه‌ای
try:
    from groq import Groq
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
except ModuleNotFoundError as exc:
    logger.error(
        "پکیج مورد نیاز نصب نیست: %s\n"
        "مطمئن شو فایل requirements.txt کنار bot.py هست و روی Railway "
        "در مرحله‌ی Build دستور 'pip install -r requirements.txt' اجرا شده.",
        exc,
    )
    sys.exit(1)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    logger.error("متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده. آن را در Railway > Variables اضافه کن.")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.error("متغیر محیطی GROQ_API_KEY تنظیم نشده. آن را در Railway > Variables اضافه کن.")
    sys.exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)

# هر چت (خصوصی یا گروه) یک تاریخچه‌ی کوتاه مکالمه دارد (در حافظه، نه دیتابیس)
chat_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 10  # تعداد پیام‌های نگه‌داشته‌شده برای هر چت

# حالت هر چت: "normal" یا "translate"
chat_modes: dict[int, str] = {}

BOT_NAME = "مکسی"
OWNER_NAME = "اکساندر"

SYSTEM_PROMPT = (
    f"اسم تو {BOT_NAME} هست، یک دستیار هوش مصنوعی. "
    f"صاحب و سازنده‌ی تو {OWNER_NAME} هست. اگه کسی پرسید صاحبت کیه یا کی ساختتت، "
    f"بگو {OWNER_NAME}. "
    "همیشه مودب، دوستانه و مفید باش و به زبان فارسی پاسخ بده، "
    "مگر اینکه کاربر به زبان دیگری پیام بده."
)

TRANSLATE_SYSTEM_PROMPT = (
    "تو یک مترجم حرفه‌ای هستی. متنی که کاربر می‌فرسته رو ترجمه کن. "
    "اگه متن فارسی نیست، به فارسیِ روان، طبیعی و بدون هیچ خطای گرامری ترجمه کن. "
    "اگه متن فارسیه، به انگلیسیِ روان و طبیعی ترجمه کن. "
    "ترجمه باید کاملاً طبیعی و روان باشه، انگار یک نویسنده‌ی بومی نوشته، نه ترجمه‌ی تحت‌اللفظی. "
    "فقط و فقط متن ترجمه‌شده رو برگردون، بدون هیچ توضیح، مقدمه، یا علامت نقل‌قول اضافه."
)

TRANSLATE_TRIGGERS = ("/ترجمه",)
TRANSLATE_EXIT_TRIGGERS = ("/عادی", "/خروج")


def is_group_chat(update: Update) -> bool:
    return update.effective_chat.type in ("group", "supergroup")


async def should_respond_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """تو گروه فقط وقتی جواب بده که منشن یا ریپلای شده باشه."""
    message = update.message
    bot_username = context.bot.username

    # ریپلای به پیام ربات
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        return True

    # منشن مستقیم با @username
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention_text = message.text[entity.offset: entity.offset + entity.length]
                if mention_text.lower() == f"@{bot_username}".lower():
                    return True

    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"سلام! من {BOT_NAME} هستم 🤖\n"
        "هر سوالی داری بپرس تا جواب بدم.\n"
        "تو گروه فقط وقتی منشنم کنی یا روی پیامم ریپلای بزنی جواب می‌دم.\n"
        "برای ترجمه بنویس /ترجمه و برای خروج ازش /عادی.\n"
        "برای پاک کردن حافظه‌ی مکالمه از /reset استفاده کن."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_histories.pop(chat_id, None)
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد ✅")


async def handle_translate(update: Update, chat_id: int, user_text: str) -> None:
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        translated = response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001
        logger.exception("Groq translate error")
        translated = f"مشکلی پیش اومد، دوباره امتحان کن.\n(خطا: {exc})"

    await update.message.reply_text(translated)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    # تو گروه‌ها فقط وقتی منشن یا ریپلای بشیم جواب بده
    if is_group_chat(update):
        if not await should_respond_in_group(update, context):
            return

    chat_id = update.effective_chat.id
    user_text = update.message.text

    # حذف منشن از ابتدای متن (مثلاً "@Maxi_bot سلام" -> "سلام")
    if context.bot.username:
        user_text = user_text.replace(f"@{context.bot.username}", "").strip()

    # فعال‌سازی حالت ترجمه
    if user_text.strip() in TRANSLATE_TRIGGERS:
        chat_modes[chat_id] = "translate"
        await update.message.reply_text(
            "🌐 حالت ترجمه فعال شد.\n"
            "هر متنی بفرستی، روان و طبیعی ترجمه می‌کنم.\n"
            "برای خروج از این حالت، /عادی رو بزن."
        )
        return

    # خروج از حالت ترجمه
    if user_text.strip() in TRANSLATE_EXIT_TRIGGERS:
        chat_modes[chat_id] = "normal"
        await update.message.reply_text("✅ برگشتیم به حالت عادی.")
        return

    # اگه تو حالت ترجمه هستیم، هر متنی رو ترجمه کن
    if chat_modes.get(chat_id) == "translate":
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await handle_translate(update, chat_id, user_text)
        return

    history = chat_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    history[:] = history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
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
