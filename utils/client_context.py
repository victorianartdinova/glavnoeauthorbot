"""
Утилита для работы с контекстом клиентов
"""
import os
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
