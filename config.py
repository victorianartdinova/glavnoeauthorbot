"""
Конфигурация Glavnoe Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8499202304:AAF2FULsVpXGapbC3yvXpCdX3kvOgcdNvyU")

# Claude API (берётся из окружения Claude Code на сервере)
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

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
