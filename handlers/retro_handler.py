"""
Обработчик команды /retro — показ еженедельного анализа победителей.
"""

import os
import logging
from aiogram import types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from utils.client_context import list_clients
from utils.winner_analyzer import (
    load_scraped_posts,
    analyze_winners,
    format_winners_report,
    save_winners_markdown,
)
from utils.scheduler import trigger_winners_analysis_now, get_scheduler_status

logger = logging.getLogger(__name__)


class RetroStates(StatesGroup):
    """Состояния для FSM команды /retro"""
    waiting_for_client = State()


async def cmd_retro(message: types.Message, state: FSMContext):
    """
    Команда /retro — показ еженедельного анализа победителей.

    Форматы:
    - /retro — показать анализ для текущего/единственного клиента
    - /retro force — принудительно запустить анализ сейчас
    """

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    # === RETRO FORCE ===
    if args and args[0].lower() == "force":
        await message.answer("⏳ Запускаю анализ победителей прямо сейчас...")

        try:
            await trigger_winners_analysis_now()
            await message.answer(
                "✅ Анализ завершён и сохранён в WINNERS.md всех клиентов"
            )
        except Exception as e:
            logger.error(f"Error forcing analysis: {e}")
            await message.answer(f"❌ Ошибка: {str(e)}")

        return

    # === RETRO STATUS ===
    if args and args[0].lower() == "status":
        status = get_scheduler_status()
        await message.answer(f"📊 Статус планировщика:\n\n{status}")
        return

    # === RETRO {client} ===
    if args and args[0].lower() != "help":
        client_slug = args[0].lower()
        await show_retro_for_client(message, client_slug)
        return

    # === RETRO (нужно выбрать клиента) ===
    clients = list_clients()

    if not clients:
        await message.answer(
            "❌ Нет клиентов.\n\n"
            "Создай клиента через /newclient"
        )
        return

    # Если один клиент — сразу показываем
    if len(clients) == 1:
        await show_retro_for_client(message, clients[0])
        return

    # Иначе спрашиваем
    clients_list = "\n".join([f"• {c}" for c in clients])
    await message.answer(
        f"📊 *Анализ Победителей*\n\n"
        f"Выбери клиента (напиши его slug):\n{clients_list}\n\n"
        f"*Команды:*\n"
        f"• /retro {{slug}} — показать анализ\n"
        f"• /retro force — пересчитать сейчас\n"
        f"• /retro status — статус планировщика",
        parse_mode="Markdown",
    )
    await state.set_state(RetroStates.waiting_for_client)


async def show_retro_for_client(message: types.Message, client_slug: str):
    """Показать анализ для конкретного клиента"""

    # Проверяем, существует ли WINNERS.md
    winners_path = f"/root/glavnoe-bot/docs/CLIENTS/{client_slug}/WINNERS.md"

    if not os.path.exists(winners_path):
        # Генерируем анализ на лету
        await message.answer("⏳ Анализирую победителей (первый раз)...")

        try:
            posts = load_scraped_posts()
            if not posts:
                await message.answer(
                    "❌ Нет парсированных постов.\n\n"
                    "Парсер запускается каждый понедельник в 09:00 UTC.\n"
                    "Используй /retro force для принудительного запуска."
                )
                return

            analysis = analyze_winners(posts, days=7)

            if analysis.get("status") != "success":
                await message.answer(
                    f"⚠️ {analysis.get('message', 'Недостаточно данных')}"
                )
                return

            # Сохраняем для будущих запросов
            save_winners_markdown(client_slug, analysis)

        except Exception as e:
            logger.error(f"Error generating analysis: {e}")
            await message.answer(f"❌ Ошибка анализа: {str(e)}")
            return
    else:
        # Читаем существующий отчёт
        try:
            with open(winners_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Отправляем по частям (ограничение Telegram)
            max_length = 4000
            if len(content) > max_length:
                parts = [
                    content[i : i + max_length] for i in range(0, len(content), max_length)
                ]
                for part in parts:
                    await message.answer(part, parse_mode="Markdown")
            else:
                await message.answer(content, parse_mode="Markdown")

            return
        except Exception as e:
            logger.error(f"Error reading winners file: {e}")
            await message.answer(f"❌ Ошибка чтения отчёта: {str(e)}")
            return


async def process_retro_client_choice(message: types.Message, state: FSMContext):
    """Обработка выбора клиента для ретро"""
    client_slug = message.text.strip().lower()
    clients = list_clients()

    if client_slug not in clients:
        await message.answer(
            f"❌ Клиент '{client_slug}' не найден.\n\n"
            f"Доступные клиенты: {', '.join(clients)}"
        )
        return

    await state.clear()
    await show_retro_for_client(message, client_slug)


async def cmd_retro_help(message: types.Message):
    """Справка по команде /retro"""
    await message.answer(
        "📊 *Анализ Победителей*\n\n"
        "*Команды:*\n"
        "• /retro — показать анализ для текущего клиента\n"
        "• /retro {slug} — показать анализ конкретного клиента\n"
        "• /retro force — пересчитать анализ прямо сейчас\n"
        "• /retro status — статус планировщика\n\n"
        "*Что показывает:*\n"
        "• Топ-эмодзи в успешных постах\n"
        "• Ключевые слова\n"
        "• Структурные паттерны (списки, ссылки)\n"
        "• Лучшие каналы для вдохновения\n"
        "• Рекомендации на неделю",
        parse_mode="Markdown",
    )


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.message.register(cmd_retro, Command("retro"))
    dp.message.register(cmd_retro_help, Command("retro_help"))
    dp.message.register(
        process_retro_client_choice,
        RetroStates.waiting_for_client
    )

    logger.info("✅ Retro handlers registered")
