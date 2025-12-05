import os
import django
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# Настройка Django окружения
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telegramquiz.settings")
django.setup()

from bot.telegram_logic import (
    start,
    handle_quiz_selection,
    handle_variant_selection,
    handle_answer,
    handle_quiz_repeat,
    show_results,
    handle_text_message
)

# Получаем токен
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise ValueError("Не найден TOKEN в переменных окружения")

# Создаём приложение бота
app = ApplicationBuilder().token(TOKEN).build()

# Регистрируем хендлеры
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("results", show_results))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
app.add_handler(CallbackQueryHandler(handle_answer, pattern="^[1-4]$"))
app.add_handler(CallbackQueryHandler(handle_quiz_selection, pattern="^quiz_"))
app.add_handler(CallbackQueryHandler(handle_variant_selection, pattern="^variant_"))
app.add_handler(CallbackQueryHandler(handle_quiz_repeat, pattern="^again$"))
app.add_handler(CallbackQueryHandler(show_results, pattern="^view_results$"))

# Асинхронная функция инициализации и запуска polling
async def main_async():
    # Удаляем старый webhook
    await app.bot.delete_webhook(drop_pending_updates=True)

    # Устанавливаем команды бота
    await app.bot.set_my_commands([
        BotCommand("start", "Тестілеуді бастау"),
        BotCommand("results", "Нәтижелерді көру"),
    ])

    print("Бот запущен")

    # Запуск polling (асинхронно)
    await app.run_polling()


if __name__ == "__main__":
    if os.environ.get("RUN_BOT", "false").lower() == "true":
        import asyncio
        # Используем уже существующий event loop Render
        asyncio.get_event_loop().run_until_complete(main_async())
    else:
        print("RUN_BOT=false — бот не запущен.")
