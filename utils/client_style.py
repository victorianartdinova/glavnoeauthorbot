"""
Утилита для управления стилем клиента и проверки качества постов
"""
import json
import os
import re
import random
from typing import Optional, List, Dict, Any
from collections import deque

import config

# Кэш последних использованных хуков для каждого клиента
_client_hook_history: Dict[str, deque] = {}


def load_style_config(client_slug: str) -> Optional[Dict[str, Any]]:
    """Загрузить конфигурацию стиля клиента"""
    config_path = os.path.join(config.CLIENTS_DIR, client_slug, "STYLE_CONFIG.json")

    if not os.path.exists(config_path):
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_post_length_requirements(client_slug: str) -> Dict[str, int]:
    """Получить требования к длине поста"""
    style = load_style_config(client_slug)

    if style and "post_length" in style:
        return style["post_length"]

    # Дефолты
    return {
        "min_words": 60,
        "target_words": 100,
        "max_words": 180
    }


def get_banned_phrases(client_slug: str) -> List[str]:
    """Получить список запрещённых фраз"""
    style = load_style_config(client_slug)

    if style and "banned_phrases" in style:
        return style["banned_phrases"]

    return []


def get_banned_openers(client_slug: str) -> List[str]:
    """Получить список запрещённых начальных фраз"""
    style = load_style_config(client_slug)

    if style and "banned_openers" in style:
        return style["banned_openers"]

    return []


def get_hook_templates(client_slug: str) -> List[str]:
    """Получить шаблоны хуков для клиента"""
    style = load_style_config(client_slug)

    if style and "hook_templates" in style:
        return style["hook_templates"]

    return []


def get_random_hook_template(client_slug: str) -> Optional[str]:
    """Получить случайный шаблон хука, избегая повторов"""
    templates = get_hook_templates(client_slug)

    if not templates:
        return None

    # Инициализируем историю если нужно
    if client_slug not in _client_hook_history:
        _client_hook_history[client_slug] = deque(maxlen=5)

    history = _client_hook_history[client_slug]

    # Фильтруем недавно использованные
    available = [t for t in templates if t not in history]

    if not available:
        available = templates

    choice = random.choice(available)
    history.append(choice)

    return choice


def validate_post(post: str, client_slug: str) -> Dict[str, Any]:
    """
    Валидация поста на соответствие требованиям клиента

    Returns:
        {
            "valid": bool,
            "issues": List[str],
            "word_count": int,
            "suggestions": List[str]
        }
    """
    issues = []
    suggestions = []

    # Подсчёт слов
    words = post.split()
    word_count = len(words)

    # Проверка длины
    length_req = get_post_length_requirements(client_slug)
    min_words = length_req.get("min_words", 60)
    max_words = length_req.get("max_words", 180)
    target_words = length_req.get("target_words", 100)

    if word_count < min_words:
        issues.append(f"Пост слишком короткий: {word_count} слов (мин. {min_words})")
        suggestions.append("Добавь больше деталей: локация, преимущества, условия")

    if word_count > max_words:
        issues.append(f"Пост слишком длинный: {word_count} слов (макс. {max_words})")
        suggestions.append("Сократи текст, убери повторы")

    # Проверка запрещённых фраз
    banned = get_banned_phrases(client_slug)
    post_lower = post.lower()

    for phrase in banned:
        if phrase.lower() in post_lower:
            issues.append(f"Запрещённая фраза: '{phrase}'")
            suggestions.append(f"Замени '{phrase}' на более оригинальную формулировку")

    # Проверка начальных фраз
    banned_openers = get_banned_openers(client_slug)
    first_line = post.split('\n')[0].strip() if post else ""

    for opener in banned_openers:
        if first_line.lower().startswith(opener.lower()):
            issues.append(f"Банальное начало: '{opener}'")
            suggestions.append("Начни с хука: вопрос, цифра, интрига")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "word_count": word_count,
        "target_words": target_words,
        "suggestions": suggestions
    }


def get_style_prompt_section(client_slug: str) -> str:
    """
    Сформировать секцию промпта для стиля клиента

    Returns:
        Строка с инструкциями по стилю для Claude
    """
    style = load_style_config(client_slug)

    if not style:
        return ""

    sections = []

    # Требования к длине
    if "post_length" in style:
        pl = style["post_length"]
        sections.append(f"""ДЛИНА ПОСТА:
- Минимум {pl.get('min_words', 80)} слов
- Цель: {pl.get('target_words', 120)} слов
- Максимум {pl.get('max_words', 200)} слов
- НЕ обрезай пост, если он в пределах нормы""")

    # Запрещённые фразы
    if "banned_phrases" in style and style["banned_phrases"]:
        banned_list = ", ".join([f'"{p}"' for p in style["banned_phrases"]])
        sections.append(f"""ЗАПРЕЩЁННЫЕ ФРАЗЫ:
{banned_list}
- Эти фразы делают текст банальным — НЕ ИСПОЛЬЗУЙ их""")

    # Запрещённые начала
    if "banned_openers" in style and style["banned_openers"]:
        openers_list = ", ".join([f'"{p}"' for p in style["banned_openers"]])
        sections.append(f"""ЗАПРЕЩЁННЫЕ НАЧАЛА:
{openers_list}
- Начинай с хука: цифра, вопрос, интрига, эмодзи+факт""")

    # Примеры хуков
    if "hook_templates" in style and style["hook_templates"]:
        hooks = random.sample(style["hook_templates"], min(5, len(style["hook_templates"])))
        hooks_text = "\n".join([f"  • {h}" for h in hooks])
        sections.append(f"""ПРИМЕРЫ ХУКОВ (для вдохновения, не копируй дословно):
{hooks_text}""")

    # Заметки о стиле
    if "style_notes" in style:
        notes = style["style_notes"]
        notes_text = "\n".join([f"  • {k}: {v}" for k, v in notes.items()])
        sections.append(f"""СТИЛЬ КЛИЕНТА:
{notes_text}""")

    return "\n\n".join(sections)


def fix_post_issues(post: str, client_slug: str) -> str:
    """
    Автоматическое исправление простых проблем в посте

    Returns:
        Исправленный пост
    """
    result = post

    # Удаляем запрещённые фразы
    banned = get_banned_phrases(client_slug)
    for phrase in banned:
        # Заменяем с учётом регистра
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        result = pattern.sub("", result)

    # Убираем двойные пробелы
    result = re.sub(r' +', ' ', result)

    # Убираем пустые строки подряд
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()
