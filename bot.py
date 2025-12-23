"""
Glavnoe Bot - Telegram бот для агентства лидгена в недвижимости
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage

import config
from handlers import lot_handler, content_handler, metrics_handler, client_handler

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
    """Приветствие"""
    await message.answer(
        "🏢 **Glavnoe Bot**\n\n"
        "Я помогаю агентству создавать контент и рекламные пакеты для недвижимости.\n\n"
        "**Управление клиентами:**\n"
        "/clients — список клиентов\n"
        "/newclient — создать нового клиента\n\n"
        "**Работа с контентом:**\n"
        "/lot — добавить новый лот\n"
        "/plan — создать контент-план\n"
        "/metrics — обновить метрики\n\n"
        "/help — подробная справка",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Справка"""
    help_text = """
📖 **Как пользоваться:**

1️⃣ **Добавить лот**: /lot
   Отправь данные в формате из glavnoe-bot-context.md

2️⃣ **Создать план**: /plan
   Бот сформирует контент-план на 7-10 дней

3️⃣ **Обновить метрики**: /metrics
   Укажи post_id и количество заявок

**Формат лота:**
```
CLIENT: client_slug
LOT_NAME: ЖК Пример
LOT_LINK: https://...
COMMENT_FROM_CLIENT: описание
PRESENTATION: url или NONE
CONDITIONS:
  - DOWNPAYMENT: сумма
  - MONTHLY_PAYMENT: сумма
  - DISCOUNT: сумма
  - SALES_START: YES/NO
REQUEST: AUTO
```
    """
    await message.answer(help_text, parse_mode="Markdown")


# === Регистрация хендлеров ===
client_handler.register_handlers(dp)
lot_handler.register_handlers(dp)
content_handler.register_handlers(dp)
metrics_handler.register_handlers(dp)


# === Запуск ===
async def main():
    logger.info("🚀 Запуск Glavnoe Bot...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
