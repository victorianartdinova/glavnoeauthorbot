"""
Источники референсов для мемов — чтение из telegram-parser
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re


# Пути к данным парсера (несколько вариантов для fallback)
PARSER_OUTPUT_PATHS = [
    "/root/telegram-parser/output/scraped_posts.json",
    "/home/telegram-parser/output/scraped_posts.json",
    os.path.expanduser("~/telegram-parser/output/scraped_posts.json"),
]

# Fallback данные (если парсер не работает)
FALLBACK_MEME_POSTS = [
    {
        "text": "Когда смотришь на цены на недвижимость 📊\nvs\nЕсли бы была своя квартира 🏠",
        "channel": "real_estate_memes",
        "date": "2025-01-22",
        "views": 5000
    },
    {
        "text": "Я: хочу квартиру у метро\nРиелтор: это в соседнем районе за 100м 💸",
        "channel": "property_humor",
        "date": "2025-01-21",
        "views": 3200
    },
    {
        "text": "Первый взнос be like: вот твои деньги 💸\nТвои деньги: 😭",
        "channel": "real_estate_jokes",
        "date": "2025-01-20",
        "views": 4100
    },
    {
        "text": "Ипотека на 30 лет? 😨\nПлатёж каждый месяц? 😱\nВ моём возрасте?! 💀",
        "channel": "realty_memes",
        "date": "2025-01-19",
        "views": 2800
    }
]


def load_scraped_posts() -> List[Dict]:
    """
    Загрузить посты из telegram-parser.
    Если парсер не работает, используем fallback примеры.

    Returns:
        Список постов
    """
    import logging
    logger = logging.getLogger(__name__)

    # Пробуем все возможные пути
    for path in PARSER_OUTPUT_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    posts = json.load(f)
                    if posts:  # Проверяем что не пусто
                        logger.info(f"Loaded {len(posts)} posts from {path}")
                        return posts
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load posts from {path}: {e}")
                continue

    # Если парсер не работает, используем fallback примеры
    logger.warning("Telegram parser not available, using fallback meme examples")
    return FALLBACK_MEME_POSTS


def get_recent_posts(days: int = 7) -> List[Dict]:
    """
    Получить посты за последние N дней.

    Args:
        days: количество дней

    Returns:
        Список постов
    """
    posts = load_scraped_posts()

    cutoff_date = datetime.now() - timedelta(days=days)

    recent = []
    for post in posts:
        try:
            # Парсим дату из разных форматов
            date_str = post.get("date", "")
            if "T" in date_str:
                post_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                post_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

            if post_date.replace(tzinfo=None) >= cutoff_date:
                recent.append(post)
        except (ValueError, TypeError):
            continue

    # Сортируем по дате (новые первые)
    recent.sort(key=lambda x: x.get("date", ""), reverse=True)

    return recent


def is_meme_candidate(post: Dict) -> bool:
    """
    Проверить, подходит ли пост для адаптации в мем.

    Критерии:
    - Длина < 500 символов
    - Есть эмодзи или восклицания
    - Темы: цены, ипотека, выбор, ожидание/реальность
    """
    text = post.get("text", "") or ""

    # Слишком длинные не подходят
    if len(text) > 500:
        return False

    # Слишком короткие тоже
    if len(text) < 30:
        return False

    # Должны быть эмодзи или восклицания
    has_emoji = bool(re.search(r'[\U0001F300-\U0001F9FF]', text))
    has_exclamation = "!" in text or "?" in text

    if not (has_emoji or has_exclamation):
        return False

    # Тематические слова для мемов
    meme_keywords = [
        # Финансы/цены
        "цен", "дорог", "дешев", "млн", "₽", "рубл", "платёж", "взнос",
        "ипотек", "рассрочк", "кредит", "ставк",
        # Эмоции/ситуации
        "ожидан", "реальн", "думал", "оказал", "хотел", "получил",
        "когда", "если", "пока", "уже",
        # Выбор
        "выбор", "выбира", "сравн", "лучше", "хуже",
        # Проблемы
        "проблем", "ошибк", "боль", "страх", "сложн",
        # Ирония
        "😂", "🤣", "😅", "🙃", "😏", "🤔", "💀", "☠️"
    ]

    text_lower = text.lower()
    keyword_count = sum(1 for kw in meme_keywords if kw in text_lower)

    # Минимум 2 ключевых слова
    return keyword_count >= 2


def filter_meme_candidates(posts: List[Dict]) -> List[Dict]:
    """
    Отфильтровать посты, подходящие для мемов.

    Returns:
        Список подходящих постов
    """
    return [p for p in posts if is_meme_candidate(p)]


def get_top_references(n: int = 3, days: int = 7) -> List[Dict]:
    """
    Получить топ-N референсов для мемов.

    Args:
        n: количество референсов
        days: за сколько дней искать

    Returns:
        Список лучших референсов
    """
    recent = get_recent_posts(days=days)
    candidates = filter_meme_candidates(recent)

    # Сортируем по просмотрам (популярные = хорошие мемы)
    candidates.sort(key=lambda x: x.get("views", 0), reverse=True)

    return candidates[:n]


def format_reference_preview(post: Dict, index: int) -> str:
    """
    Форматировать референс для превью пользователю.

    Args:
        post: данные поста
        index: номер референса (1, 2, 3)

    Returns:
        Текст превью
    """
    text = post.get("text", "")[:200]
    channel = post.get("channel", "unknown")
    views = post.get("views", 0)
    date = post.get("date", "")[:10]

    # Обрезаем текст красиво
    if len(post.get("text", "")) > 200:
        text += "..."

    return (
        f"*{index}. @{channel}* ({views} просм.)\n"
        f"{text}"
    )


def get_reference_by_index(references: List[Dict], index: int) -> Optional[Dict]:
    """Получить референс по индексу (1-based)"""
    if 1 <= index <= len(references):
        return references[index - 1]
    return None
