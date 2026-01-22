"""
Модуль обучения бота на основе успешного контента.
Отслеживает успешные посты и использует их как примеры для генерации новых.
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Путь к базе успешных примеров контента
LEARNING_DB_PATH = "/home/user/glavnoeauthorbot/data/learning_examples.json"


def load_learning_db() -> Dict:
    """
    Загрузить базу данных с успешными примерами контента.

    Returns:
        dict с примерами по клиентам и форматам
    """
    if not os.path.exists(LEARNING_DB_PATH):
        return {"examples": {}, "stats": {}}

    try:
        with open(LEARNING_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"examples": {}, "stats": {}}


def save_learning_db(db: Dict) -> bool:
    """Сохранить базу данных обучения"""
    try:
        os.makedirs(os.path.dirname(LEARNING_DB_PATH), exist_ok=True)
        with open(LEARNING_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        logger.error(f"Failed to save learning DB: {e}")
        return False


def extract_post_features(post_text: str) -> Dict:
    """
    Извлечь характеристики поста для анализа.

    Args:
        post_text: текст поста

    Returns:
        dict с характеристиками
    """
    import re

    features = {
        "length": len(post_text),
        "has_emoji": bool(re.search(r'[\U0001F300-\U0001F9FF]', post_text)),
        "has_numbers": bool(re.search(r'\d+', post_text)),
        "has_questions": "?" in post_text,
        "has_exclamations": "!" in post_text,
        "paragraphs": len([p for p in post_text.split('\n') if p.strip()]),
        "avg_line_length": len(post_text) / max(1, len([p for p in post_text.split('\n') if p.strip()])),
    }

    # Анализ ключевых тем
    themes = {
        "financial": any(w in post_text.lower() for w in ["платёж", "взнос", "ипотека", "млн", "₽"]),
        "location": any(w in post_text.lower() for w in ["метро", "мин", "рядом", "район"]),
        "lifestyle": any(w in post_text.lower() for w in ["комфорт", "уют", "просторно", "стиль"]),
        "urgency": any(w in post_text.lower() for w in ["осталось", "последний", "скоро", "сейчас"]),
    }

    features["themes"] = themes

    return features


def register_successful_post(
    client_slug: str,
    post_text: str,
    format_type: str,
    metrics: Dict = None
) -> bool:
    """
    Зарегистрировать успешный пост в базе обучения.

    Args:
        client_slug: слаг клиента
        post_text: текст поста
        format_type: формат (lidgen, expert, circle, etc)
        metrics: dict с метриками успешности (views, likes, comments)

    Returns:
        True если успешно сохранено
    """
    if metrics is None:
        metrics = {}

    db = load_learning_db()

    # Создаём структуру если её нет
    if client_slug not in db["examples"]:
        db["examples"][client_slug] = {}
    if format_type not in db["examples"][client_slug]:
        db["examples"][client_slug][format_type] = []

    # Извлекаем характеристики
    features = extract_post_features(post_text)

    # Создаём запись
    example = {
        "text": post_text[:500],  # Сохраняем первые 500 символов
        "full_length": len(post_text),
        "features": features,
        "metrics": metrics,
        "timestamp": datetime.now().isoformat(),
        "success_score": calculate_success_score(metrics)
    }

    db["examples"][client_slug][format_type].append(example)

    # Ограничиваем количество примеров (последние 20 для каждого формата)
    db["examples"][client_slug][format_type] = db["examples"][client_slug][format_type][-20:]

    # Обновляем статистику
    if client_slug not in db["stats"]:
        db["stats"][client_slug] = {}

    db["stats"][client_slug][format_type] = {
        "count": len(db["examples"][client_slug][format_type]),
        "avg_success": sum(e["success_score"] for e in db["examples"][client_slug][format_type]) / max(1, len(db["examples"][client_slug][format_type])),
        "last_update": datetime.now().isoformat()
    }

    return save_learning_db(db)


def calculate_success_score(metrics: Dict) -> float:
    """
    Рассчитать оценку успешности поста.

    Args:
        metrics: dict с метриками (views, likes, comments, ctr, etc)

    Returns:
        оценка от 0 до 100
    """
    score = 0.0

    # Просмотры (максимум 100 за 10k просмотров)
    views = metrics.get("views", 0)
    score += min(100, (views / 10000) * 100) * 0.5

    # CTR (максимум 100 за 10%)
    ctr = metrics.get("ctr", 0)
    score += min(100, ctr * 10) * 0.3

    # Комментарии (максимум 100 за 100 комментариев)
    comments = metrics.get("comments", 0)
    score += min(100, (comments / 100) * 100) * 0.2

    return score


def get_best_examples(
    client_slug: str,
    format_type: str,
    limit: int = 3
) -> List[Dict]:
    """
    Получить лучшие примеры для формата и клиента.

    Args:
        client_slug: слаг клиента
        format_type: формат контента
        limit: сколько примеров вернуть

    Returns:
        список лучших примеров, отсортированных по успеху
    """
    db = load_learning_db()

    if client_slug not in db["examples"] or format_type not in db["examples"][client_slug]:
        return []

    examples = db["examples"][client_slug][format_type]

    # Сортируем по успеху
    examples_sorted = sorted(examples, key=lambda x: x.get("success_score", 0), reverse=True)

    return examples_sorted[:limit]


def get_learning_context(client_slug: str, format_type: str) -> str:
    """
    Получить контекст обучения для промпта.
    Возвращает примеры успешных постов для использования в генерации.

    Args:
        client_slug: слаг клиента
        format_type: формат контента

    Returns:
        текст для добавления в промпт
    """
    examples = get_best_examples(client_slug, format_type, limit=2)

    if not examples:
        return ""

    context = "ПРИМЕРЫ УСПЕШНЫХ ПОСТОВ ДЛЯ ЭТОГО КЛИЕНТА:\n\n"

    for i, example in enumerate(examples, 1):
        score = example.get("success_score", 0)
        context += f"Пример {i} (успешность: {score:.0f}/100):\n"
        context += f"{example['text']}\n"
        context += f"(Характеристики: {example['features'].get('length')} символов, "

        themes = [t for t, v in example['features'].get('themes', {}).items() if v]
        if themes:
            context += f"темы: {', '.join(themes)}"
        context += ")\n\n"

    context += "Постарайся использовать ПОХОЖИЙ СТИЛЬ в своём посте, но создай НОВЫЙ контент.\n\n"

    return context


def update_post_metrics(
    client_slug: str,
    format_type: str,
    example_index: int,
    new_metrics: Dict
) -> bool:
    """
    Обновить метрики существующего примера (если пост уже опубликован и собраны новые метрики).

    Args:
        client_slug: слаг клиента
        format_type: формат
        example_index: индекс примера в списке
        new_metrics: новые метрики

    Returns:
        True если успешно обновлено
    """
    db = load_learning_db()

    if (client_slug not in db["examples"] or
        format_type not in db["examples"][client_slug] or
        example_index >= len(db["examples"][client_slug][format_type])):
        return False

    example = db["examples"][client_slug][format_type][example_index]
    example["metrics"].update(new_metrics)
    example["success_score"] = calculate_success_score(example["metrics"])

    return save_learning_db(db)


def get_learning_stats(client_slug: str) -> Dict:
    """
    Получить статистику обучения для клиента.

    Args:
        client_slug: слаг клиента

    Returns:
        dict со статистикой по форматам
    """
    db = load_learning_db()

    if client_slug not in db["stats"]:
        return {}

    return db["stats"][client_slug]
