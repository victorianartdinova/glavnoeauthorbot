"""
Конфигурация Glavnoe Bot
Единственный источник правды для всех настроек с защитой от смешивания env
"""
import os
import re
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv


class BotIdentity(str, Enum):
    """Идентификатор бота - защита от смешивания"""
    GLAVNOE = "GLAVNOE"


def redact_secret(value: str, show_chars: int = 5) -> str:
    """Скрывает секретные значения для логов"""
    if not value or len(value) <= show_chars * 2:
        return "***"
    return f"{value[:show_chars]}...{value[-show_chars:]}"


def validate_env_isolation():
    """
    Проверяет, что env не содержит смешанных переменных от разных ботов

    Raises:
        ValueError: если найдены конфликтующие переменные
    """
    # Загружаем env
    load_dotenv()

    # Запрещённые ключи (от других ботов)
    forbidden_keys = [
        "VIRAL_BOT_TOKEN",
        "VIRALE_BOT_TOKEN",
        "VIRAL_API_KEY",
        "VIKA_BOT_TOKEN",
        "AGILE_BOT_TOKEN",
    ]

    found_forbidden = []
    for key in forbidden_keys:
        if os.getenv(key):
            found_forbidden.append(key)

    if found_forbidden:
        raise ValueError(
            f"❌ Найдены запрещённые env-переменные от других ботов:\n"
            f"   {', '.join(found_forbidden)}\n"
            f"   Удалите их из .env файла. Используйте только TELEGRAM_BOT_TOKEN."
        )

    # Проверка legacy ключей
    legacy_keys = {
        "BOT_TOKEN": "TELEGRAM_BOT_TOKEN",
    }

    found_legacy = []
    for old_key, new_key in legacy_keys.items():
        if os.getenv(old_key):
            found_legacy.append((old_key, new_key))

    if found_legacy:
        warnings = "\n".join([f"   {old} → используйте {new}" for old, new in found_legacy])
        raise ValueError(
            f"❌ Найдены устаревшие env-ключи:\n{warnings}\n"
            f"   Переименуйте их в .env файле."
        )


# Валидация изоляции ПЕРЕД загрузкой любых настроек
validate_env_isolation()


# === Bot Identity ===
BOT_IDENTITY = BotIdentity.GLAVNOE
EXPECTED_BOT_USERNAME = os.getenv("EXPECTED_BOT_USERNAME", "glavnoeauthor_bot")
EXPECTED_PRODUCT_NAME = os.getenv("EXPECTED_PRODUCT_NAME", "GLAVNOE Bot")


# === Telegram Bot ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError(
        "❌ TELEGRAM_BOT_TOKEN environment variable is required\n"
        f"   Добавьте его в .env файл для {EXPECTED_PRODUCT_NAME}"
    )

# Рабочий чат команды
TEAM_CHAT_ID = int(os.getenv("TEAM_CHAT_ID", "-1002367799345"))

# Ветки (threads) по клиентам
CLIENT_THREADS = {
    "apple_real_estate": 13130,
    "artem_solodkov": 21173,
    "nadejda_dmitruk": 17408,
}

# Оператор (публикует посты)
OPERATOR_USERNAME = os.getenv("OPERATOR_USERNAME", "ksandrbloger")

# Админ (для /dev команды)
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0")) or None


# === Claude API ===
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
if not CLAUDE_API_KEY:
    raise ValueError(
        "❌ ANTHROPIC_API_KEY environment variable is required\n"
        "   Добавьте его в .env файл"
    )


# === Пути ===
BASE_DIR = Path(__file__).parent.parent.absolute()
DOCS_DIR = BASE_DIR / "docs"
CLIENTS_DIR = DOCS_DIR / "CLIENTS"
CONTEXT_FILE = BASE_DIR / "glavnoe-bot-context.md"


# === Telegram Ads условия ===
AD_ELIGIBILITY_RULES = {
    "downpayment_max": 10_000_000,
    "monthly_payment_max": 200_000,
    "discount_min": 5_000_000,
    "sales_start": True
}


# === Форматы контента ===
CONTENT_FORMATS = [
    "лидген",
    "дайджест",
    "живой обзор",
    "кейс",
    "анонс",
    "FAQ"
]


# === Углы (angle_tag) ===
CONTENT_ANGLES = [
    "выгода",
    "доступность",
    "событие",
    "локация",
    "редкость",
    "готовность",
    "инвест",
    "семья"
]


# === Feature Flags (по умолчанию OFF) ===
ENABLE_LOT_CARD = os.getenv("ENABLE_LOT_CARD", "0") == "1"
ENABLE_PACKAGE_BY_LOT = os.getenv("ENABLE_PACKAGE_BY_LOT", "0") == "1"
ENABLE_BRIEF_SHORT = os.getenv("ENABLE_BRIEF_SHORT", "0") == "1"
ENABLE_PLAN_EXPORT = os.getenv("ENABLE_PLAN_EXPORT", "0") == "1"
