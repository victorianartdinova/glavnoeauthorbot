#!/usr/bin/env python3
"""
Smoke-check для Glavnoe Bot

Проверяет:
- Загрузку конфигурации
- Валидность env
- Идентичность бота через Telegram getMe
- Отсутствие конфликтующих переменных
"""
import sys
import asyncio
from pathlib import Path

# Добавляем корень проекта в PATH
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str):
    """Красивый заголовок секции"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_env_file():
    """Проверка наличия .env файла"""
    print_section("1. Проверка .env файла")

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        print(f"✅ Файл .env найден: {env_path}")
        return True
    else:
        print(f"❌ Файл .env НЕ НАЙДЕН: {env_path}")
        print("   Создайте файл .env на основе .env.example")
        return False


def check_config_loading():
    """Проверка загрузки конфигурации"""
    print_section("2. Загрузка конфигурации")

    try:
        from config import (
            BOT_IDENTITY,
            EXPECTED_BOT_USERNAME,
            EXPECTED_PRODUCT_NAME,
            TELEGRAM_BOT_TOKEN,
            CLAUDE_API_KEY,
            redact_secret,
        )

        print(f"✅ Конфигурация загружена успешно")
        print(f"   Identity: {BOT_IDENTITY.value}")
        print(f"   Product Name: {EXPECTED_PRODUCT_NAME}")
        print(f"   Expected Username: @{EXPECTED_BOT_USERNAME}")
        print(f"   Bot Token: {redact_secret(TELEGRAM_BOT_TOKEN)}")
        print(f"   Claude API Key: {redact_secret(CLAUDE_API_KEY)}")
        return True

    except ValueError as e:
        print(f"❌ Ошибка валидации конфигурации:")
        print(f"   {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка при загрузке:")
        print(f"   {e}")
        return False


async def check_bot_identity():
    """Проверка идентичности бота через Telegram getMe"""
    print_section("3. Валидация идентичности бота")

    try:
        from config import validate_bot_identity, EXPECTED_BOT_USERNAME

        bot = await validate_bot_identity()
        me = await bot.get_me()

        print(f"✅ Telegram API доступен")
        print(f"✅ Bot ID: {me.id}")
        print(f"✅ Username: @{me.username}")
        print(f"✅ First Name: {me.first_name}")

        if me.username == EXPECTED_BOT_USERNAME:
            print(f"✅ Идентичность подтверждена: @{me.username}")
            await bot.session.close()
            return True
        else:
            print(f"❌ Идентичность НЕ СОВПАДАЕТ!")
            print(f"   Ожидается: @{EXPECTED_BOT_USERNAME}")
            print(f"   Получено: @{me.username}")
            await bot.session.close()
            return False

    except ValueError as e:
        print(f"❌ Ошибка валидации:")
        print(f"   {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при проверке идентичности:")
        print(f"   {e}")
        return False


def check_forbidden_env():
    """Проверка на запрещённые env-переменные"""
    print_section("4. Проверка на конфликтующие env")

    import os

    forbidden_keys = [
        "VIRAL_BOT_TOKEN",
        "VIRALE_BOT_TOKEN",
        "VIRAL_API_KEY",
        "VIKA_BOT_TOKEN",
        "AGILE_BOT_TOKEN",
        "BOT_TOKEN",  # legacy
    ]

    found = []
    for key in forbidden_keys:
        if os.getenv(key):
            found.append(key)

    if found:
        print(f"❌ Найдены запрещённые переменные:")
        for key in found:
            print(f"   - {key}")
        print("\n   Удалите их из .env файла!")
        return False
    else:
        print("✅ Конфликтующие переменные не найдены")
        return True


def main():
    """Главная функция"""
    print("\n" + "🏥" * 20)
    print("     GLAVNOE BOT - HEALTH CHECK")
    print("🏥" * 20)

    checks = [
        ("ENV файл", check_env_file()),
        ("Конфигурация", check_config_loading()),
        ("Запрещённые env", check_forbidden_env()),
    ]

    # Асинхронная проверка идентичности
    identity_ok = asyncio.run(check_bot_identity())
    checks.append(("Идентичность бота", identity_ok))

    # Итоги
    print_section("ИТОГИ")

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)

    for name, ok in checks:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status} — {name}")

    print("\n" + "=" * 60)
    if passed == total:
        print(f"🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ({passed}/{total})")
        print("   Бот готов к запуску!")
        sys.exit(0)
    else:
        print(f"❌ ПРОВЕРКИ НЕ ПРОЙДЕНЫ ({passed}/{total})")
        print("   Исправьте ошибки перед запуском бота")
        sys.exit(1)


if __name__ == "__main__":
    main()
