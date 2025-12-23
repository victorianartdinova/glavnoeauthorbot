"""
Обработчик обновления метрик
"""
from aiogram import types, Dispatcher
from aiogram.filters import Command


async def cmd_metrics(message: types.Message):
    """Команда /metrics - обновление метрик постов"""
    await message.answer(
        "📊 **Обновление метрик**\n\n"
        "⏳ Функция в разработке.\n"
        "Формат:\n"
        "```\n"
        "POST_ID: client-P20251222-01\n"
        "LEADS_WEEK: 5\n"
        "QUALITY: good\n"
        "```",
        parse_mode="Markdown"
    )


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.message.register(cmd_metrics, Command("metrics"))
