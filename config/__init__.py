"""
Модуль конфигурации Glavnoe Bot
Единственный источник правды для всех настроек
"""
from .settings import *
from .validation import validate_bot_identity

__all__ = [
    # Bot Identity
    'BOT_IDENTITY',
    'EXPECTED_BOT_USERNAME',
    'EXPECTED_PRODUCT_NAME',

    # Telegram
    'TELEGRAM_BOT_TOKEN',
    'TEAM_CHAT_ID',
    'CLIENT_THREADS',
    'OPERATOR_USERNAME',
    'ADMIN_USER_ID',
    'ALLOWED_USERS',

    # Claude API
    'CLAUDE_API_KEY',

    # Paths
    'BASE_DIR',
    'DOCS_DIR',
    'CLIENTS_DIR',
    'CONTEXT_FILE',

    # Business Rules
    'AD_ELIGIBILITY_RULES',
    'CONTENT_FORMATS',
    'CONTENT_ANGLES',

    # Feature Flags
    'ENABLE_LOT_CARD',
    'ENABLE_PACKAGE_BY_LOT',
    'ENABLE_BRIEF_SHORT',
    'ENABLE_PLAN_EXPORT',

    # Validation
    'validate_bot_identity',
]
