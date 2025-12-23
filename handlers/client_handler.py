"""
Обработчик управления клиентами
"""
from aiogram import types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.client_context import create_client, list_clients


class ClientStates(StatesGroup):
    waiting_for_client_slug = State()


async def cmd_clients(message: types.Message):
    """Команда /clients - список всех клиентов"""
    clients = list_clients()

    if not clients:
        await message.answer(
            "📋 **Клиенты не найдены**\n\n"
            "Используй /newclient чтобы создать первого клиента.",
            parse_mode="Markdown"
        )
        return

    client_list = "\n".join([f"• `{c}`" for c in clients])

    await message.answer(
        f"📋 **Список клиентов ({len(clients)}):**\n\n"
        f"{client_list}\n\n"
        f"**Команды:**\n"
        f"/newclient — создать нового клиента",
        parse_mode="Markdown"
    )


async def cmd_newclient(message: types.Message, state: FSMContext):
    """Команда /newclient - создать нового клиента"""
    await state.set_state(ClientStates.waiting_for_client_slug)
    await message.answer(
        "🆕 **Создание нового клиента**\n\n"
        "Отправь `client_slug` — короткое имя клиента (латиница, без пробелов).\n\n"
        "Примеры:\n"
        "• `client1`\n"
        "• `alfabank`\n"
        "• `pik_comfort`\n\n"
        "Это имя будет использоваться в системе.",
        parse_mode="Markdown"
    )


async def process_new_client(message: types.Message, state: FSMContext):
    """Обработка создания нового клиента"""
    client_slug = message.text.strip().lower()

    # Валидация
    if not client_slug.replace("_", "").isalnum():
        await message.answer(
            "❌ **Ошибка**\n\n"
            "Используй только латинские буквы, цифры и подчёркивание.\n"
            "Например: `client1`, `alfabank`",
            parse_mode="Markdown"
        )
        return

    # Создание клиента
    success = create_client(client_slug)

    if not success:
        await message.answer(
            f"❌ **Клиент `{client_slug}` уже существует!**\n\n"
            f"Выбери другое имя.",
            parse_mode="Markdown"
        )
        return

    await message.answer(
        f"✅ **Клиент `{client_slug}` создан!**\n\n"
        f"📂 Папка: `docs/CLIENTS/{client_slug}/`\n\n"
        f"**Следующий шаг:**\n"
        f"Заполни файлы контекста:\n"
        f"• `PROFILE.md` — о компании\n"
        f"• `TONE_OF_VOICE.md` — стиль и голос\n"
        f"• `GOALS.md` — цели и KPI\n"
        f"• `CONTEXT.md` — рынок и конкуренты\n\n"
        f"После этого можно добавлять лоты командой /lot",
        parse_mode="Markdown"
    )

    await state.clear()


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.message.register(cmd_clients, Command("clients"))
    dp.message.register(cmd_newclient, Command("newclient"))
    dp.message.register(process_new_client, ClientStates.waiting_for_client_slug)
