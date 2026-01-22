#!/usr/bin/env python3
"""
Тестовый скрипт для проверки идентичности бота
"""
import asyncio
import sys
import os
from pathlib import Path

# Добавляем текущую директорию в PATH
sys.path.insert(0, str(Path(__file__).parent))

from aiogram import Bot
import config


async def test_bot_identity():
    """Проверяет идентичность бота через getMe"""
    print("=" * 60)
    print("ПРОВЕРКА ИДЕНТИЧНОСТИ GLAVNOE BOT")
    print("=" * 60)

    # Проверка env
    print("\n1. ENV файл:")
    env_path = Path(__file__).parent / ".env"
    print(f"   Путь: {env_path}")
    print(f"   Существует: {env_path.exists()}")

    # Проверка токена
    print("\n2. Токен из конфигурации:")
    token = config.TELEGRAM_BOT_TOKEN
    if token:
        print(f"   Токен: {token[:10]}...{token[-10:]}")
    else:
        print("   ❌ Токен НЕ НАЙДЕН!")
        return

    # Проверка других параметров
    print("\n3. Конфигурация:")
    print(f"   TEAM_CHAT_ID: {config.TEAM_CHAT_ID}")
    print(f"   CLIENT_THREADS: {list(config.CLIENT_THREADS.keys())}")

    # Telegram getMe
    print("\n4. Telegram getMe():")
    try:
        # Принудительно используем IPv4 (как в bot.py)
        import socket
        _orig_getaddrinfo = socket.getaddrinfo
        def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
            return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        socket.getaddrinfo = _getaddrinfo_ipv4_only

        bot = Bot(token=token)
        me = await bot.get_me()

        print(f"   ✓ ID: {me.id}")
        print(f"   ✓ Username: @{me.username}")
        print(f"   ✓ First Name: {me.first_name}")
        print(f"   ✓ Is Bot: {me.is_bot}")

        # Проверка на правильность
        print("\n5. Валидация:")
        expected_username = "glavnoeauthor_bot"
        if me.username == expected_username:
            print(f"   ✅ Username совпадает: @{me.username}")
        else:
            print(f"   ❌ Username НЕ СОВПАДАЕТ!")
            print(f"      Ожидается: @{expected_username}")
            print(f"      Получено: @{me.username}")

        await bot.session.close()

    except Exception as e:
        print(f"   ❌ Ошибка при вызове getMe: {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_bot_identity())
