"""
Анализатор победителей — выделение паттернов из успешных парсированных постов.

Анализирует:
- Топ-эмодзи в успешных постах
- Средняя длина текста
- Наиболее частые ключевые слова
- Структуры текста (начало, CTA)
- Соотношение вопросов/восклицаний
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import Counter
import logging

logger = logging.getLogger(__name__)

# Пороги для определения "победителя"
MIN_VIEWS_THRESHOLD = 500  # Минимум просмотров
MIN_FORWARDS_RATIO = 0.01  # Минимум ratio forwards/views
EXCELLENT_VIEWS_THRESHOLD = 5000  # "Отличный" пост


def load_scraped_posts() -> List[Dict]:
    """Загрузить посты из telegram-parser"""
    parser_path = "/root/telegram-parser/output/scraped_posts.json"
    if not os.path.exists(parser_path):
        logger.warning(f"Parser output not found: {parser_path}")
        return []

    try:
        with open(parser_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading parser data: {e}")
        return []


def filter_winning_posts(posts: List[Dict], days: int = 7) -> List[Dict]:
    """
    Отфильтровать "победительные" посты за последние N дней.

    Критерии:
    - Хотя бы MIN_VIEWS_THRESHOLD просмотров
    - Хотя бы MIN_FORWARDS_RATIO ratio forwards/views
    """
    cutoff_date = datetime.now() - timedelta(days=days)
    winners = []

    for post in posts:
        try:
            # Парсим дату
            date_str = post.get("date", "")
            if "T" in date_str:
                post_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                post_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

            if post_date.replace(tzinfo=None) < cutoff_date:
                continue

            views = post.get("views", 0)
            forwards = post.get("forwards", 0)

            # Критерии победителя
            if views >= MIN_VIEWS_THRESHOLD:
                if forwards > 0 or views >= EXCELLENT_VIEWS_THRESHOLD:
                    winners.append(post)
        except (ValueError, TypeError):
            continue

    return winners


def extract_emojis(text: str) -> List[str]:
    """Извлечь все эмодзи из текста"""
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F9FF"  # Emoji
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "]+"
    )
    return emoji_pattern.findall(text)


def extract_keywords(text: str) -> List[str]:
    """Извлечь ключевые слова из текста"""
    # Перечень важных слов для недвижимости
    keywords = [
        # Финансы
        "платёж", "платеж", "взнос", "ипотека", "ипотек", "рассрочка", "кредит",
        "млн", "тыс", "₽", "рубл", "стоимост", "цен", "дорог", "дешев",
        # Свойства
        "метр", "м²", "кв", "комнат", "спальн", "кухн", "ванн", "балкон",
        # Локация
        "метро", "м.", "район", "ул.", "наб.", "проспект", "шоссе", "центр",
        # События
        "старт", "новое", "акци", "скидк", "выгод", "предложен",
        # Эмоции
        "хотел", "получи", "удивительн", "редк", "уникальн", "идеально",
        "класс", "вид", "готовый", "ремонт", "рядом", "парк", "инфраструктур"
    ]

    text_lower = text.lower()
    found = []
    for kw in keywords:
        if kw in text_lower:
            found.append(kw)

    return found


def analyze_text_structure(text: str) -> Dict:
    """Анализ структуры текста"""
    lines = text.split("\n")

    # Начало текста (первая строка)
    first_line = lines[0] if lines else ""

    # Наличие вопросов/восклицаний
    question_count = text.count("?")
    exclamation_count = text.count("!")

    # Наличие списков
    has_bullets = bool(re.search(r"^[\-•\–\*]", text, re.MULTILINE))
    has_numbering = bool(re.search(r"^\d+[\.\)]", text, re.MULTILINE))

    # Наличие ссылок
    has_links = bool(re.search(r"https?://|t\.me/|tg://", text))

    return {
        "first_line_length": len(first_line),
        "text_length": len(text),
        "lines_count": len(lines),
        "questions": question_count,
        "exclamations": exclamation_count,
        "has_bullets": has_bullets,
        "has_numbering": has_numbering,
        "has_links": has_links,
        "avg_line_length": len(text) / len(lines) if lines else 0,
    }


def analyze_winners(posts: List[Dict], days: int = 7) -> Dict:
    """
    Основная функция анализа.

    Args:
        posts: список парсированных постов
        days: за сколько дней анализировать

    Returns:
        Словарь с результатами анализа
    """
    winners = filter_winning_posts(posts, days=days)

    if not winners:
        return {
            "status": "no_data",
            "message": f"Нет постов с {MIN_VIEWS_THRESHOLD}+ просмотров за {days} дней",
            "count": 0
        }

    # === Анализ эмодзи ===
    all_emojis = []
    for post in winners:
        text = post.get("text", "")
        emojis = extract_emojis(text)
        all_emojis.extend(emojis)

    emoji_counter = Counter(all_emojis)
    top_emojis = emoji_counter.most_common(10)

    # === Анализ ключевых слов ===
    all_keywords = []
    for post in winners:
        text = post.get("text", "")
        keywords = extract_keywords(text)
        all_keywords.extend(keywords)

    keyword_counter = Counter(all_keywords)
    top_keywords = keyword_counter.most_common(15)

    # === Анализ структуры ===
    structures = []
    for post in winners:
        text = post.get("text", "")
        struct = analyze_text_structure(text)
        structures.append(struct)

    avg_text_length = sum(s["text_length"] for s in structures) / len(structures) if structures else 0
    avg_lines = sum(s["lines_count"] for s in structures) / len(structures) if structures else 0
    avg_questions = sum(s["questions"] for s in structures) / len(structures) if structures else 0
    avg_exclamations = sum(s["exclamations"] for s in structures) / len(structures) if structures else 0

    # === Каналы с наиболее успешными постами ===
    channels = Counter(post.get("channel", "unknown") for post in winners)
    top_channels = channels.most_common(5)

    # === Метрики успеха ===
    avg_views = sum(p.get("views", 0) for p in winners) / len(winners)
    avg_forwards = sum(p.get("forwards", 0) for p in winners) / len(winners)
    total_views = sum(p.get("views", 0) for p in winners)

    return {
        "status": "success",
        "analyzed_posts": len(winners),
        "date_range_days": days,
        "generated_at": datetime.now().isoformat(),

        # Метрики
        "metrics": {
            "total_views": total_views,
            "avg_views": round(avg_views, 0),
            "avg_forwards": round(avg_forwards, 1),
            "avg_text_length": round(avg_text_length, 0),
            "avg_lines": round(avg_lines, 1),
            "avg_questions": round(avg_questions, 2),
            "avg_exclamations": round(avg_exclamations, 2),
        },

        # Топ элементы
        "top_emojis": [
            {"emoji": emoji, "count": count}
            for emoji, count in top_emojis
        ],
        "top_keywords": [
            {"keyword": kw, "count": count}
            for kw, count in top_keywords
        ],
        "top_channels": [
            {"channel": channel, "posts": count}
            for channel, count in top_channels
        ],

        # Структурные паттерны
        "structure_patterns": {
            "has_bullets_percent": round(
                sum(1 for s in structures if s["has_bullets"]) / len(structures) * 100, 1
            ) if structures else 0,
            "has_numbering_percent": round(
                sum(1 for s in structures if s["has_numbering"]) / len(structures) * 100, 1
            ) if structures else 0,
            "has_links_percent": round(
                sum(1 for s in structures if s["has_links"]) / len(structures) * 100, 1
            ) if structures else 0,
        }
    }


def format_winners_report(analysis: Dict) -> str:
    """Форматировать результаты анализа для показа в боте"""

    if analysis.get("status") != "success":
        return f"⚠️ {analysis.get('message', 'Ошибка анализа')}"

    report = f"""📊 *АНАЛИЗ УСПЕШНЫХ ПОСТОВ* ({analysis['analyzed_posts']} постов за {analysis['date_range_days']} дн.)

*Метрики:*
• Всего просмотров: {analysis['metrics']['total_views']:,}
• Средний просмотр: {analysis['metrics']['avg_views']:.0f}
• Средние пересылки: {analysis['metrics']['avg_forwards']:.1f}
• Средняя длина: {analysis['metrics']['avg_text_length']:.0f} символов
• Среднее строк: {analysis['metrics']['avg_lines']:.1f}
• Вопросов на пост: {analysis['metrics']['avg_questions']:.2f}
• Восклицаний на пост: {analysis['metrics']['avg_exclamations']:.2f}

*Топ эмодзи:*
"""

    for item in analysis['top_emojis'][:5]:
        report += f"• {item['emoji']} — {item['count']} раз\n"

    report += f"\n*Топ ключевые слова:*\n"
    for item in analysis['top_keywords'][:8]:
        report += f"• {item['keyword']} — {item['count']} раз\n"

    report += f"\n*Структурные паттерны:*\n"
    patterns = analysis['structure_patterns']
    report += f"• Списки (•): {patterns['has_bullets_percent']:.0f}%\n"
    report += f"• Нумерация: {patterns['has_numbering_percent']:.0f}%\n"
    report += f"• Ссылки: {patterns['has_links_percent']:.0f}%\n"

    report += f"\n*Лучшие каналы:*\n"
    for item in analysis['top_channels'][:3]:
        report += f"• @{item['channel']} — {item['posts']} постов\n"

    report += f"\n💡 *РЕКОМЕНДАЦИИ:*\n"
    report += "• Используй топ-эмодзи в начале постов\n"
    report += "• Включай ключевые слова из топа\n"

    if patterns['has_bullets_percent'] > 50:
        report += "• Структурируй текст списками\n"
    if patterns['has_links_percent'] > 50:
        report += "• Добавляй ссылки для CTA\n"
    if analysis['metrics']['avg_exclamations'] > 1.5:
        report += "• Используй восклицания для энергии\n"

    return report


def save_winners_markdown(client_slug: str, analysis: Dict) -> bool:
    """
    Сохранить результаты анализа в WINNERS.md клиента.

    Returns:
        True если успешно, False если ошибка
    """
    if analysis.get("status") != "success":
        return False

    winners_path = f"/root/glavnoe-bot/docs/CLIENTS/{client_slug}/WINNERS.md"

    try:
        # Создаём содержимое файла
        content = f"""# 🏆 Анализ Побеждающих Постов — {client_slug}

*Последнее обновление:* {analysis['generated_at']}
*Анализировано:* {analysis['analyzed_posts']} постов за {analysis['date_range_days']} дней

---

## 📈 Метрики Успеха

| Метрика | Значение |
|---------|---------|
| Всего просмотров | {analysis['metrics']['total_views']:,} |
| Средний пост | {analysis['metrics']['avg_views']:.0f} просмотров |
| Средние пересылки | {analysis['metrics']['avg_forwards']:.1f} |
| Средняя длина | {analysis['metrics']['avg_text_length']:.0f} символов |

---

## 🎯 Топ-10 Эмодзи

"""
        for i, item in enumerate(analysis['top_emojis'][:10], 1):
            content += f"{i}. {item['emoji']} — {item['count']} использований\n"

        content += f"\n## 🔑 Топ-15 Ключевых Слов\n\n"
        for i, item in enumerate(analysis['top_keywords'][:15], 1):
            content += f"{i}. `{item['keyword']}` — {item['count']} упоминаний\n"

        content += f"\n## 🏗️ Структурные Паттерны\n\n"
        patterns = analysis['structure_patterns']
        content += f"- **Списки с буллетами:** {patterns['has_bullets_percent']:.0f}%\n"
        content += f"- **Нумерованные списки:** {patterns['has_numbering_percent']:.0f}%\n"
        content += f"- **Содержат ссылки:** {patterns['has_links_percent']:.0f}%\n"

        content += f"\n## 👑 Топ Каналы для Вдохновения\n\n"
        for item in analysis['top_channels'][:5]:
            content += f"- [@{item['channel']}](https://t.me/{item['channel']}) — {item['posts']} успешных постов\n"

        content += f"\n## 💡 Рекомендации на Неделю\n\n"
        content += "**Применяй в своих постах:**\n"
        content += f"1. Начинай с одного из топ-3 эмодзи: "
        top_3_emojis = " ".join([item['emoji'] for item in analysis['top_emojis'][:3]])
        content += f"{top_3_emojis}\n"
        content += f"2. Включай ключевые слова: {', '.join([item['keyword'] for item in analysis['top_keywords'][:5]])}\n"

        if patterns['has_bullets_percent'] > 50:
            content += "3. Структурируй идеи списками для лучшей читаемости\n"
        if patterns['has_links_percent'] > 50:
            content += "3. Добавляй ссылки для CTA и навигации\n"

        content += "\n---\n"
        content += "*Автоматически сгенерировано ботом @glavnoeauthor_bot*\n"

        # Сохраняем файл
        os.makedirs(os.path.dirname(winners_path), exist_ok=True)
        with open(winners_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Saved winners report for {client_slug}")
        return True

    except Exception as e:
        logger.error(f"Error saving winners markdown: {e}")
        return False
