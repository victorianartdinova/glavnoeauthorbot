"""
Утилиты для экранирования Markdown в Telegram
"""


def escape_md(text: str) -> str:
    """Экранирование спецсимволов для Telegram Markdown"""
    if not text:
        return ""
    return (
        text
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("`", "\\`")
    )
