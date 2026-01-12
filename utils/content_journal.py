"""
Журнал контента — хранение опубликованных и запланированных постов
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import config


def get_journal_dir() -> str:
    """Путь к директории журналов"""
    return os.path.join(config.BASE_DIR, "data", "content_journal")


def get_client_journal_path(client_slug: str) -> str:
    """Путь к журналу клиента"""
    return os.path.join(get_journal_dir(), client_slug, "journal.json")


def ensure_journal_dir(client_slug: str):
    """Создать директории если не существуют"""
    journal_dir = os.path.join(get_journal_dir(), client_slug)
    os.makedirs(journal_dir, exist_ok=True)


def generate_entry_id() -> str:
    """Генерирует уникальный ID записи"""
    return f"entry_{uuid.uuid4().hex[:8]}"


def load_journal(client_slug: str) -> List[Dict]:
    """
    Загрузить журнал клиента.

    Returns:
        Список записей журнала
    """
    journal_path = get_client_journal_path(client_slug)

    if not os.path.exists(journal_path):
        return []

    with open(journal_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_journal(client_slug: str, entries: List[Dict]):
    """Сохранить журнал клиента"""
    ensure_journal_dir(client_slug)
    journal_path = get_client_journal_path(client_slug)

    with open(journal_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def add_entry(
    client_slug: str,
    date: str,
    format_type: str,
    text: str,
    status: str = "published",
    source: str = "bot_generated"
) -> str:
    """
    Добавить запись в журнал.

    Args:
        client_slug: slug клиента
        date: дата публикации (YYYY-MM-DD)
        format_type: формат (lidgen, case, meme, expert, digest, live, circle, podcast)
        text: полный текст поста
        status: planned | published
        source: bot_generated | forwarded | from_plan

    Returns:
        ID записи
    """
    entries = load_journal(client_slug)

    entry_id = generate_entry_id()
    entry = {
        "id": entry_id,
        "date": date,
        "format": format_type,
        "text": text,
        "status": status,
        "source": source,
        "created_at": datetime.now().isoformat()
    }

    entries.append(entry)
    save_journal(client_slug, entries)

    return entry_id


def update_entry(client_slug: str, entry_id: str, updates: Dict) -> bool:
    """
    Обновить запись в журнале.

    Args:
        client_slug: slug клиента
        entry_id: ID записи
        updates: dict с обновлениями

    Returns:
        True если успешно
    """
    entries = load_journal(client_slug)

    for entry in entries:
        if entry["id"] == entry_id:
            entry.update(updates)
            save_journal(client_slug, entries)
            return True

    return False


def delete_entry(client_slug: str, entry_id: str) -> bool:
    """Удалить запись из журнала"""
    entries = load_journal(client_slug)

    for i, entry in enumerate(entries):
        if entry["id"] == entry_id:
            entries.pop(i)
            save_journal(client_slug, entries)
            return True

    return False


def get_entries_by_date(client_slug: str, date: str) -> List[Dict]:
    """Получить записи за конкретную дату"""
    entries = load_journal(client_slug)
    return [e for e in entries if e["date"] == date]


def get_entries_by_week(client_slug: str, week_start: datetime) -> Dict[str, List[Dict]]:
    """
    Получить записи за неделю, сгруппированные по дням.

    Args:
        client_slug: slug клиента
        week_start: начало недели (понедельник)

    Returns:
        Dict: {date_str: [entries]}
    """
    entries = load_journal(client_slug)

    week_end = week_start + timedelta(days=6)

    result = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        result[date_str] = []

    for entry in entries:
        entry_date = entry["date"]
        if entry_date in result:
            result[entry_date].append(entry)

    return result


def get_week_start(date: datetime = None) -> datetime:
    """Получить начало недели (понедельник)"""
    if date is None:
        date = datetime.now()

    # Понедельник = 0, Воскресенье = 6
    days_since_monday = date.weekday()
    return date - timedelta(days=days_since_monday)


def format_journal_calendar(client_slug: str, week_start: datetime) -> str:
    """
    Форматировать журнал в виде календаря недели.

    Returns:
        Текст календаря для отображения
    """
    week_data = get_entries_by_week(client_slug, week_start)

    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    lines = [f"📅 *Журнал контента*"]
    lines.append(f"Неделя: {week_start.strftime('%d.%m')} — {(week_start + timedelta(days=6)).strftime('%d.%m')}")
    lines.append("")

    for i, (date_str, entries) in enumerate(week_data.items()):
        day = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = weekdays[i]
        day_display = day.strftime("%d.%m")

        if entries:
            # Есть записи
            status_icons = []
            for e in entries:
                if e["status"] == "published":
                    status_icons.append("✅")
                else:
                    status_icons.append("📝")

            formats = [e["format"].upper()[:3] for e in entries]
            lines.append(f"{' '.join(status_icons)} *{weekday} {day_display}*: {', '.join(formats)}")
        else:
            # Пусто
            lines.append(f"⬜ {weekday} {day_display}: —")

    # Статистика
    all_entries = [e for entries in week_data.values() for e in entries]
    published = len([e for e in all_entries if e["status"] == "published"])
    planned = len([e for e in all_entries if e["status"] == "planned"])

    lines.append("")
    lines.append(f"✅ Опубликовано: {published} | 📝 В плане: {planned}")

    return "\n".join(lines)


# Маппинг форматов
FORMAT_MAP = {
    "lidgen": "Лидген",
    "case": "Кейс",
    "meme": "Мем",
    "expert": "Эксперт",
    "digest": "Дайджест",
    "live": "Live",
    "circle": "Кружок",
    "podcast": "Подкаст",
}

FORMAT_EMOJI = {
    "lidgen": "🏢",
    "case": "📈",
    "meme": "😂",
    "expert": "💡",
    "digest": "📰",
    "live": "📱",
    "circle": "🎙",
    "podcast": "🎤",
}


def get_format_display(format_type: str) -> str:
    """Получить отображаемое название формата"""
    return FORMAT_MAP.get(format_type.lower(), format_type)


def get_format_emoji(format_type: str) -> str:
    """Получить эмодзи формата"""
    return FORMAT_EMOJI.get(format_type.lower(), "📝")
