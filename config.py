"""
Конфигурация Glavnoe Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Claude API (берётся из окружения Claude Code на сервере)
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Рабочий чат команды
TEAM_CHAT_ID = -1002367799345

# Ветки (threads) по клиентам
CLIENT_THREADS = {
    "apple_real_estate": 13130,
    "artem_solodkov": 21173,
    "nadejda_dmitruk": 17408,
}

# Оператор (публикует посты)
OPERATOR_USERNAME = "ksandrbloger"

# Админ (для /dev команды)
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0")) or None

# TG Booster API (токены хранятся в файлах клиентов)
# Каждый клиент имеет свой токен в docs/CLIENTS/{client}/tg_booster.json

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
CLIENTS_DIR = os.path.join(DOCS_DIR, "CLIENTS")
CONTEXT_FILE = os.path.join(BASE_DIR, "glavnoe-bot-context.md")

# Telegram Ads условия
AD_ELIGIBILITY_RULES = {
    "downpayment_max": 10_000_000,
    "monthly_payment_max": 200_000,
    "discount_min": 5_000_000,
    "sales_start": True
}

# Форматы контента
CONTENT_FORMATS = [
    "лидген",
    "дайджест",
    "живой обзор",
    "кейс",
    "анонс",
    "FAQ"
]

# Углы (angle_tag)
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
