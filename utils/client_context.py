"""
Утилита для работы с контекстом клиентов
"""
import os
import re
import shutil
from typing import Optional

import config


def create_client(client_slug: str) -> bool:
    """Создать папку нового клиента из шаблона"""
    template_dir = os.path.join(config.CLIENTS_DIR, "_TEMPLATE")
    client_dir = os.path.join(config.CLIENTS_DIR, client_slug)

    if os.path.exists(client_dir):
        return False  # Клиент уже существует

    # Копируем шаблон
    shutil.copytree(template_dir, client_dir)

    # Обновляем PROFILE.md с client_slug
    profile_path = os.path.join(client_dir, "PROFILE.md")
    with open(profile_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("client_slug", client_slug)
    content = content.replace("[Название компании]", f"Клиент {client_slug}")

    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def load_client_context(client_slug: str) -> Optional[dict]:
    """
    Загрузить полный контекст клиента

    Returns:
        dict с ключами: profile, tone_of_voice, goals, context
        None если клиент не найден
    """
    client_dir = os.path.join(config.CLIENTS_DIR, client_slug)

    if not os.path.exists(client_dir):
        return None

    context = {}

    # Загружаем каждый файл
    files = {
        "profile": "PROFILE.md",
        "tone_of_voice": "TONE_OF_VOICE.md",
        "goals": "GOALS.md",
        "context": "CONTEXT.md"
    }

    for key, filename in files.items():
        file_path = os.path.join(client_dir, filename)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                context[key] = f.read()
        else:
            context[key] = ""

    return context


def get_client_prompt(client_slug: str) -> str:
    """
    Сформировать промпт для Claude API с контекстом клиента

    Returns:
        Строка с полным контекстом для передачи в Claude
    """
    context = load_client_context(client_slug)

    if not context:
        return ""

    prompt = f"""
# КОНТЕКСТ КЛИЕНТА: {client_slug}

## ПРОФИЛЬ КОМПАНИИ
{context['profile']}

## TONE OF VOICE (КАК ПИСАТЬ)
{context['tone_of_voice']}

## ЦЕЛИ И СТРАТЕГИЯ
{context['goals']}

## КОНТЕКСТ РЫНКА
{context['context']}

---

ВАЖНО:
- Пиши СТРОГО в стиле этого бренда
- Используй их формулировки и подход
- Следуй всем правилам и запретам из ToV
- Учитывай цели и боли аудитории
"""

    return prompt


def get_client_designer(client_slug: str) -> Optional[str]:
    """Извлечь username дизайнера из PROFILE.md"""
    context = load_client_context(client_slug)
    if not context or not context.get("profile"):
        return None

    match = re.search(r'\*\*Дизайнер:\*\*\s*@(\w+)', context['profile'])
    return f"@{match.group(1)}" if match else None


def list_clients() -> list:
    """Получить список всех клиентов"""
    if not os.path.exists(config.CLIENTS_DIR):
        return []

    clients = []
    for item in os.listdir(config.CLIENTS_DIR):
        path = os.path.join(config.CLIENTS_DIR, item)
        if os.path.isdir(path) and item != "_TEMPLATE":
            clients.append(item)

    return sorted(clients)


def get_client_lots(client_slug: str, status: str = None) -> list:
    """
    Получить лоты клиента

    Args:
        client_slug: идентификатор клиента
        status: фильтр по статусу (READY_FOR_CONTENT, NEED_FACTS, USED)

    Returns:
        Список лотов
    """
    import json

    lots_file = os.path.join(config.CLIENTS_DIR, client_slug, "lots.json")

    if not os.path.exists(lots_file):
        return []

    with open(lots_file, "r", encoding="utf-8") as f:
        lots = json.load(f)

    if status:
        lots = [lot for lot in lots if lot.get("status") == status]

    return lots


def get_client_channels(client_slug: str) -> list:
    """
    Получить каналы конкурентов клиента

    Returns:
        Список каналов для парсинга
    """
    import json

    channels_file = os.path.join(config.CLIENTS_DIR, client_slug, "channels.json")

    if not os.path.exists(channels_file):
        return []

    with open(channels_file, "r", encoding="utf-8") as f:
        return json.load(f)


def add_client_channel(client_slug: str, channel: str) -> bool:
    """
    Добавить канал конкурента клиенту

    Args:
        client_slug: идентификатор клиента
        channel: @username канала

    Returns:
        True если добавлен, False если уже существует
    """
    import json

    client_dir = os.path.join(config.CLIENTS_DIR, client_slug)
    channels_file = os.path.join(client_dir, "channels.json")

    if not os.path.exists(client_dir):
        return False

    # Загружаем существующие
    if os.path.exists(channels_file):
        with open(channels_file, "r", encoding="utf-8") as f:
            channels = json.load(f)
    else:
        channels = []

    # Нормализуем (убираем @)
    channel = channel.lstrip("@")

    if channel in channels:
        return False

    channels.append(channel)

    with open(channels_file, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

    return True


# Дефолтные эмодзи (если у клиента нет EMOJIS.json)
DEFAULT_EMOJIS = {
    "header_emojis": {
        "apartment": "🏢",
        "family": "🏡",
        "hot": "🔥",
        "intrigue": "👀",
        "water": "🌊",
        "park": "🌳",
        "city": "🏙",
        "premium": "✨"
    },
    "structure_emojis": {
        "location": "📍",
        "finance": "💰",
        "feature": "▪️",
        "cta": "⚪️",
        "date": "📅",
        "format": "🎬",
        "type": "📢"
    },
    "format_labels": {
        "GIF_SINGLE": "ГИФ",
        "GIF_SLIDER": "ГИФ (слайдеры)",
        "STATIC": "Статика"
    }
}


def get_client_emojis(client_slug: str) -> dict:
    """
    Получить кастомные эмодзи клиента

    Args:
        client_slug: идентификатор клиента

    Returns:
        dict с эмодзи или дефолтные значения
    """
    import json

    emojis_file = os.path.join(config.CLIENTS_DIR, client_slug, "EMOJIS.json")

    if os.path.exists(emojis_file):
        with open(emojis_file, "r", encoding="utf-8") as f:
            return json.load(f)

    return DEFAULT_EMOJIS


def get_emoji_prompt_section(client_slug: str) -> str:
    """
    Сформировать секцию промпта с эмодзи клиента

    Returns:
        Строка для добавления в system_prompt
    """
    emojis = get_client_emojis(client_slug)
    header = emojis.get("header_emojis", {})

    emoji_lines = []
    for key, emoji in header.items():
        labels = {
            "apartment": "стандартная квартира/апартаменты",
            "family": "семейная квартира, дом",
            "hot": "старт продаж, скидка, горячее предложение",
            "intrigue": 'интрига, "как реально выглядит"',
            "water": "у воды (река, набережная, бассейн)",
            "park": "у парка, природа",
            "city": "виды на город, Сити",
            "premium": "премиум, элит, пентхаус"
        }
        label = labels.get(key, key)
        emoji_lines.append(f"{emoji} — {label}")

    return "\n".join(emoji_lines)
