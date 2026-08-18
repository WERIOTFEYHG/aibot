تغییرات نسبت به نسخه‌ی قبلی:

۱. کتابخانه از google-generativeai (منسوخ‌شده) به google-genai (SDK جدید و رسمی گوگل) تغییر کرد.
۲. مدل از gemini-2.0-flash (که در ۱ ژوئن ۲۰۲۶ کاملاً غیرفعال شد) به gemini-3.5-flash تغییر کرد.
۳. ساختار چت (session) و ارسال عکس مطابق API جدید google-genai بازنویسی شد.

نصب و اجرا روی Railway مثل قبل است:
1) این پوشه (bot.py, requirements.txt, Procfile) را در ریپازیتوری قرار دهید.
2) متغیرهای محیطی TELEGRAM_BOT_TOKEN و GEMINI_API_KEY را در Railway ست کنید.
3) دیپلوی کنید.

اگر باز هم خطا دیدید، حتماً لاگ‌های Railway را چک کنید؛ خط دقیق خطا (مثلاً 401، 404، quota exceeded) آنجا ثبت می‌شود.
