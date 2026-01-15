"""
Валидация идентичности бота на старте
"""
import asyncio
import socket
import logging
from aiogram import Bot

from .settings import (
    TELEGRAM_BOT_TOKEN,
    BOT_IDENTITY,
    EXPECTED_BOT_USERNAME,
    EXPECTED_PRODUCT_NAME,
    redact_secret,
)


logger = logging.getLogger(__name__)


def setup_ipv4_only():
    """
    Принудительно используем IPv4 (IPv6 блокирован на сервере)
    Вызывается ПЕРЕД созданием Bot
    """
    _orig_getaddrinfo = socket.getaddrinfo

    def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _getaddrinfo_ipv4_only


async def validate_bot_identity() -> Bot:
    """
    Валидирует идентичность бота через Telegram getMe()

    Проверяет:
    - Токен валиден
    - Username совпадает с ожидаемым
    - Бот существует и активен

    Returns:
        Bot: инициализированный бот с проверенной идентичностью

    Raises:
        ValueError: если идентичность не совпадает
        Exception: если токен невалиден или другие ошибки API
    """
    setup_ipv4_only()

    logger.info(f"🔍 Проверка идентичности бота...")
    logger.info(f"   Identity: {BOT_IDENTITY.value}")
    logger.info(f"   Expected Username: @{EXPECTED_BOT_USERNAME}")
    logger.info(f"   Product Name: {EXPECTED_PRODUCT_NAME}")
    logger.info(f"   Token: {redact_secret(TELEGRAM_BOT_TOKEN)}")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    try:
        me = await bot.get_me()

        logger.info(f"✅ Telegram getMe() успешно:")
        logger.info(f"   ID: {me.id}")
        logger.info(f"   Username: @{me.username}")
        logger.info(f"   First Name: {me.first_name}")

        # КРИТИЧЕСКАЯ ПРОВЕРКА: username должен совпадать
        if me.username != EXPECTED_BOT_USERNAME:
            error_msg = (
                f"❌ ОШИБКА ИДЕНТИЧНОСТИ БОТА!\n"
                f"\n"
                f"   Ожидается:  @{EXPECTED_BOT_USERNAME} ({EXPECTED_PRODUCT_NAME})\n"
                f"   Получено:   @{me.username}\n"
                f"\n"
                f"   Проверьте:\n"
                f"   1. Правильный ли токен в .env?\n"
                f"   2. Нет ли смешивания .env от разных ботов?\n"
                f"   3. Используется ли правильный .env файл?\n"
                f"\n"
                f"   Токен: {redact_secret(TELEGRAM_BOT_TOKEN)}\n"
            )
            logger.error(error_msg)
            await bot.session.close()
            raise ValueError(error_msg)

        logger.info(f"✅ Идентичность подтверждена: @{me.username}")
        return bot

    except ValueError:
        # Пробрасываем ошибку валидации дальше
        raise
    except Exception as e:
        error_msg = f"❌ Ошибка при проверке идентичности: {e}"
        logger.error(error_msg)
        await bot.session.close()
        raise


def validate_bot_identity_sync() -> None:
    """
    Синхронная обёртка для валидации (для использования в старых местах)

    Raises:
        ValueError: если идентичность не совпадает
    """
    try:
        asyncio.run(validate_bot_identity())
    except KeyboardInterrupt:
        raise
    except Exception:
        raise
