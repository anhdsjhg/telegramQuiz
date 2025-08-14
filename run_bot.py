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

async def setup_bot_commands(app):
    # Удаляем webhook, чтобы polling работал
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_my_commands([
        BotCommand("start", "Тестілеуді бастау"),
        BotCommand("results", "Нәтижелерді көру"),
    ])

def main():
    app = ApplicationBuilder().token("8490466804:AAEYScC-GkuMKE-MXdVKlhitKKLFJpz1P9I").build()

    # Регистрируем хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("results", show_results))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^[1-4]$"))
    app.add_handler(CallbackQueryHandler(handle_quiz_selection, pattern="^quiz_"))
    app.add_handler(CallbackQueryHandler(handle_variant_selection, pattern="^variant_"))
    app.add_handler(CallbackQueryHandler(handle_quiz_repeat, pattern="^again$"))
    app.add_handler(CallbackQueryHandler(show_results, pattern="^view_results$"))

    # Выполняем асинхронную настройку перед запуском
    app.post_init = setup_bot_commands

    print("Бот запущен")
    app.run_polling(close_loop=False)  # Не закрываем общий event loop

if __name__ == "__main__":
    main()
