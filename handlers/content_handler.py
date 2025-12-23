"""
Обработчик создания контента
"""
from aiogram import types, Dispatcher
import json
import os
from datetime import datetime

import config


async def cmd_plan(message: types.Message):
    """Команда /plan - создание контент-плана"""
    # Получаем все лоты со статусом READY_FOR_CONTENT
    # TODO: реализовать логику генерации плана через Claude API

    await message.answer(
        "📋 **Создание контент-плана...**\n\n"
        "⏳ Функция в разработке.\n"
        "Бот будет:\n"
        "1. Собирать лоты READY_FOR_CONTENT\n"
        "2. Формировать план на 7-10 дней\n"
        "3. Генерировать посты через Claude API\n"
        "4. Создавать AdPack для подходящих лотов",
        parse_mode="Markdown"
    )


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.register_message_handler(cmd_plan, commands=['plan'])
