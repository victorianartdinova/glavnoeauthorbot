"""
Glavnoe Bot - Telegram бот для агентства лидгена в недвижимости
"""
import asyncio
import logging
import socket

# Принудительно используем IPv4 (IPv6 блокирован на сервере)
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4_only

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

import config
from handlers import lot_handler, content_handler, metrics_handler, client_handler, plan_handler, journal_handler, meme_handler


def get_clients_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура выбора клиента (внизу экрана)"""
    from utils.client_context import list_clients
    clients = list_clients()

    keyboard = []
    # Клиенты по 2 в ряд
    for i in range(0, len(clients), 2):
        row = [KeyboardButton(text=f"👤 {clients[i]}")]
        if i + 1 < len(clients):
            row.append(KeyboardButton(text=f"👤 {clients[i+1]}"))
        keyboard.append(row)

    # Кнопка помощи
    keyboard.append([KeyboardButton(text="❓ Помощь")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_actions_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура действий (внизу экрана)"""
    return ReplyKeyboardMarkup(keyboard=[
        [
            KeyboardButton(text="📝 Пост"),
            KeyboardButton(text="🎨 ТЗ дизайнеру"),
        ],
        [
            KeyboardButton(text="📅 Контент-план"),
            KeyboardButton(text="🎙 Кружок"),
        ],
        [
            KeyboardButton(text="😂 Мем"),
            KeyboardButton(text="📓 Журнал"),
        ],
        [
            KeyboardButton(text="📱 Live"),
            KeyboardButton(text="🎤 Voice"),
        ],
        [
            KeyboardButton(text="⬅️ Сменить клиента"),
        ],
    ], resize_keyboard=True)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# === Команды ===

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветствие — выбор клиента"""
    await message.answer(
        "🏢 *GLAVNOE Bot*\n\n"
        "Контент и реклама для недвижимости\n\n"
        "👇 Выбери клиента:",
        parse_mode="Markdown",
        reply_markup=get_clients_keyboard()
    )


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    """Показать меню — выбор клиента"""
    await message.answer(
        "👇 Выбери клиента:",
        reply_markup=get_clients_keyboard()
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Справка"""
    await message.answer(
        "❓ *Справка*\n\n"
        "*КОНТЕНТ:*\n"
        "📝 Пост — написать пост (лидген, кружок, дайджест)\n"
        "🎨 ТЗ дизайнеру — 3 варианта текстов\n"
        "📅 Контент-план — на 7 дней\n"
        "🎙 Кружок — ТЗ для записи\n"
        "📱 Live — подводка к Instagram\n"
        "🎤 Voice — подводка к голосовому\n\n"
        "*УПРАВЛЕНИЕ:*\n"
        "🏠 Лот — добавить объект\n"
        "📊 Метрики — статистика\n\n"
        "💡 /start — выбор клиента",
        parse_mode="Markdown",
        reply_markup=get_clients_keyboard()
    )


# === Обработчики Reply-кнопок ===

@dp.message(F.text == "❓ Помощь")
async def btn_help(message: types.Message):
    await cmd_help(message)


@dp.message(F.text == "⬅️ Сменить клиента")
async def btn_change_client(message: types.Message, state: FSMContext):
    """Назад к выбору клиента"""
    await state.clear()
    await message.answer(
        "👇 Выбери клиента:",
        reply_markup=get_clients_keyboard()
    )


@dp.message(F.text.startswith("👤 "))
async def btn_select_client(message: types.Message, state: FSMContext):
    """Выбор клиента — показать действия"""
    client_slug = message.text.replace("👤 ", "")
    await state.update_data(current_client=client_slug)
    await message.answer(
        f"✅ Клиент: *{client_slug}*\n\n"
        "👇 Выбери действие:",
        parse_mode="Markdown",
        reply_markup=get_actions_keyboard()
    )


async def check_client_selected(message: types.Message, state: FSMContext) -> str | None:
    """Проверить, выбран ли клиент"""
    data = await state.get_data()
    client = data.get("current_client")
    if not client:
        await message.answer(
            "⚠️ Сначала выбери клиента",
            reply_markup=get_clients_keyboard()
        )
        return None
    return client


@dp.message(F.text == "📝 Пост")
async def btn_post(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.content_handler import cmd_post
        await cmd_post(message, state)


@dp.message(F.text == "🎨 ТЗ дизайнеру")
async def btn_brief(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        await message.answer(
            f"🎨 *ТЗ для дизайнера* ({client})\n\n"
            "Отправь данные по шаблону:\n\n"
            "🔗 *Ссылка:* https://jk-example.ru\n"
            "💰 *Цена:* от 25 млн\n"
            "💳 *ПВ/платёж:* от 2.5 млн / 150 тыс/мес\n"
            "🏷 *Скидка:* -10% до конца месяца\n"
            "✨ *Особенности:* терраса, вид на парк",
            parse_mode="Markdown"
        )
        from handlers.content_handler import ContentStates
        await state.set_state(ContentStates.waiting_for_brief_data)


@dp.message(F.text == "📅 Контент-план")
async def btn_plan(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.content_handler import cmd_plan
        await cmd_plan(message, state)


@dp.message(F.text == "🎙 Кружок")
async def btn_circle(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.content_handler import cmd_circle
        await cmd_circle(message, state)


@dp.message(F.text == "📱 Live")
async def btn_live(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.content_handler import cmd_live
        await cmd_live(message, state)


@dp.message(F.text == "🎤 Voice")
async def btn_voice(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.content_handler import cmd_voice_intro
        await cmd_voice_intro(message, state)


@dp.message(F.text == "😂 Мем")
async def btn_meme(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.meme_handler import cmd_meme
        await cmd_meme(message, state)


@dp.message(F.text == "📓 Журнал")
async def btn_journal(message: types.Message, state: FSMContext):
    client = await check_client_selected(message, state)
    if client:
        from handlers.journal_handler import cmd_journal
        await cmd_journal(message, state)


# === Регистрация хендлеров ===
client_handler.register_handlers(dp)
lot_handler.register_handlers(dp)
content_handler.register_handlers(dp)
plan_handler.register_handlers(dp)
journal_handler.register_handlers(dp)
meme_handler.register_handlers(dp)
metrics_handler.register_handlers(dp)


# === Запуск ===
async def main():
    logger.info("🚀 Запуск Glavnoe Bot...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
