"""
Индекс истории контента — выжимка из журнала за последние N дней
для быстрого доступа и антиповторов
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import Counter

import config
from utils.content_journal import load_journal


def get_memory_dir() -> str:
    """Путь к директории памяти"""
    return os.path.join(config.BASE_DIR, "data", "memory")


def get_history_index_path(client_slug: str) -> str:
    """Путь к файлу индекса истории"""
    return os.path.join(get_memory_dir(), client_slug, "history_index.json")


def ensure_memory_dir(client_slug: str):
    """Создать директории если не существуют"""
    memory_dir = os.path.join(get_memory_dir(), client_slug)
    os.makedirs(memory_dir, exist_ok=True)


def get_default_index() -> Dict:
    """Дефолтная структура индекса"""
    return {
        "last_updated": None,
        "period_days": 30,
        "entries": [],
        "stats": {
            "formats": {},
            "hooks": {},
            "ctas": {},
            "angles": {}
        }
    }


def load_history_index(client_slug: str) -> Dict:
    """Загрузить индекс истории"""
    index_path = get_history_index_path(client_slug)

    if not os.path.exists(index_path):
        return get_default_index()

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return get_default_index()


def save_history_index(client_slug: str, index: Dict):
    """Сохранить индекс истории"""
    ensure_memory_dir(client_slug)
    index_path = get_history_index_path(client_slug)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def extract_topics_from_text(text: str) -> List[str]:
    """
    Извлечь ключевые темы/топики из текста поста.

    Returns:
        Список ключевых слов/тем
    """
    topics = []

    # Ищем ключевые паттерны
    patterns = {
        "рассрочка": r"рассрочк[аиуе]",
        "ипотека": r"ипотек[аиуе]",
        "инвестиция": r"инвестиц|доходност",
        "локация": r"метро|минут|район|центр|парк",
        "премиум": r"премиум|элит|люкс|бизнес.класс",
        "скидка": r"скидк[аиуе]|акци[яию]",
        "офис": r"офис[аыеов]|коммерч",
        "апартаменты": r"апартамент",
        "квартира": r"квартир[аыеу]",
        "пентхаус": r"пентхаус",
        "видовой": r"вид[аыеу]|панорам",
        "готовность": r"готов|сдач[аи]|ключ",
    }

    text_lower = text.lower()
    for topic, pattern in patterns.items():
        if re.search(pattern, text_lower):
            topics.append(topic)

    return topics


def extract_hook_type(text: str) -> str:
    """
    Определить тип хука из текста.

    Returns:
        financial|location|premium|emotional|urgency|unknown
    """
    text_lower = text.lower()

    # Финансовый хук — цены, рассрочка, ипотека
    if re.search(r"рассрочк|ипотек|платёж|взнос|цен[аыеу]|от \d+|млн", text_lower):
        return "financial"

    # Локационный хук — метро, район, близость
    if re.search(r"минут[аыуе]? (до|пешком|на)|метро|мцк|мцд|район|центр", text_lower):
        return "location"

    # Премиум хук — статус, эксклюзив
    if re.search(r"премиум|элит|люкс|статус|уникальн|редк", text_lower):
        return "premium"

    # Срочность — ограниченное время
    if re.search(r"последн|осталось|только до|успей|заканчива", text_lower):
        return "urgency"

    # Эмоциональный — образ жизни
    if re.search(r"представь|мечт|жизнь|комфорт|уют", text_lower):
        return "emotional"

    # Quality-gate: не смогли определить — возвращаем unknown
    return "unknown"


def extract_cta(text: str) -> Optional[str]:
    """
    Извлечь CTA (call-to-action) из текста.

    Returns:
        Текст CTA или None
    """
    # Ищем паттерн "Напишите «XXX»"
    match = re.search(r'[Нн]апиши(?:те)?\s*[«""]([^»""]+)[»""]', text)
    if match:
        return match.group(1).upper()

    return None


def extract_angle(text: str) -> str:
    """
    Извлечь угол/подход поста.

    Returns:
        Краткое описание угла или unknown
    """
    text_lower = text.lower()

    angles = {
        "рассрочка 0%": r"рассрочк[аиуе]\s*0\s*%",
        "рассрочка": r"рассрочк[аиуе]",
        "ипотека льготная": r"льготн[аяое]+\s*ипотек|ипотек[аиуе]\s*\d+\s*%",
        "ипотека": r"ипотек[аиуе]",
        "скидка": r"скидк[аиуе]",
        "инвестиция": r"инвестиц|доходност|окупаемост",
        "локация метро": r"минут[аыуе]?\s*(до\s*)?метро",
        "локация центр": r"центр|кремл|красн[аяое]+\s*площад",
        "вид панорама": r"панорам|вид[аыеу]\s*на",
        "готовность": r"готов[аыеи]|ключ[аиуе]",
        "последние": r"последн[иеяй]+|осталось",
    }

    for angle, pattern in angles.items():
        if re.search(pattern, text_lower):
            return angle

    # Quality-gate: не смогли определить — возвращаем unknown
    return "unknown"


def build_index_entry(journal_entry: Dict) -> Dict:
    """
    Создать запись индекса из записи журнала.

    Args:
        journal_entry: запись из content_journal

    Returns:
        Компактная запись для индекса
    """
    text = journal_entry.get("text", "")

    return {
        "id": journal_entry.get("id"),
        "date": journal_entry.get("date"),
        "format": journal_entry.get("format"),
        "hook_type": journal_entry.get("hook_type") or extract_hook_type(text),
        "angle": journal_entry.get("angle") or extract_angle(text),
        "cta": journal_entry.get("cta") or extract_cta(text),
        "lot_id": journal_entry.get("lot_id"),
        "lot_name": journal_entry.get("lot_name"),
        "topics": extract_topics_from_text(text)
    }


def build_history_index(client_slug: str, period_days: int = 30) -> Dict:
    """
    Построить индекс истории из журнала.

    Args:
        client_slug: slug клиента
        period_days: количество дней для индексации

    Returns:
        Полный индекс
    """
    journal = load_journal(client_slug)

    # Фильтруем по дате
    cutoff_date = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")

    entries = []
    formats_counter = Counter()
    hooks_counter = Counter()
    ctas_counter = Counter()
    angles_counter = Counter()

    for entry in journal:
        entry_date = entry.get("date", "")
        if entry_date >= cutoff_date:
            index_entry = build_index_entry(entry)
            entries.append(index_entry)

            # Собираем статистику
            if index_entry.get("format"):
                formats_counter[index_entry["format"]] += 1
            if index_entry.get("hook_type"):
                hooks_counter[index_entry["hook_type"]] += 1
            if index_entry.get("cta"):
                ctas_counter[index_entry["cta"]] += 1
            if index_entry.get("angle"):
                angles_counter[index_entry["angle"]] += 1

    index = {
        "last_updated": datetime.now().isoformat(),
        "period_days": period_days,
        "entries": entries,
        "stats": {
            "formats": dict(formats_counter),
            "hooks": dict(hooks_counter),
            "ctas": dict(ctas_counter),
            "angles": dict(angles_counter)
        }
    }

    save_history_index(client_slug, index)
    return index


def update_history_index(client_slug: str, new_entry: Dict):
    """
    Добавить новую запись в индекс и обновить статистику.

    Args:
        client_slug: slug клиента
        new_entry: новая запись журнала
    """
    index = load_history_index(client_slug)

    # Проверяем, нужно ли перестроить индекс
    if not index["entries"]:
        build_history_index(client_slug)
        return

    # Добавляем новую запись
    index_entry = build_index_entry(new_entry)
    index["entries"].append(index_entry)

    # Обновляем статистику
    if index_entry.get("format"):
        index["stats"]["formats"][index_entry["format"]] = \
            index["stats"]["formats"].get(index_entry["format"], 0) + 1
    if index_entry.get("hook_type"):
        index["stats"]["hooks"][index_entry["hook_type"]] = \
            index["stats"]["hooks"].get(index_entry["hook_type"], 0) + 1
    if index_entry.get("cta"):
        index["stats"]["ctas"][index_entry["cta"]] = \
            index["stats"]["ctas"].get(index_entry["cta"], 0) + 1
    if index_entry.get("angle"):
        index["stats"]["angles"][index_entry["angle"]] = \
            index["stats"]["angles"].get(index_entry["angle"], 0) + 1

    # Удаляем старые записи (старше period_days)
    cutoff_date = (datetime.now() - timedelta(days=index["period_days"])).strftime("%Y-%m-%d")
    index["entries"] = [e for e in index["entries"] if e.get("date", "") >= cutoff_date]

    index["last_updated"] = datetime.now().isoformat()
    save_history_index(client_slug, index)


def get_recent_entries(client_slug: str, days: int = 7) -> List[Dict]:
    """Получить записи за последние N дней"""
    index = load_history_index(client_slug)

    if not index["entries"]:
        # Перестраиваем индекс если пустой
        index = build_history_index(client_slug)

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return [e for e in index["entries"] if e.get("date", "") >= cutoff_date]


def get_stats(client_slug: str) -> Dict:
    """Получить статистику из индекса"""
    index = load_history_index(client_slug)
    return index.get("stats", {})


def find_similar_entries(client_slug: str, hook_type: str = None, angle: str = None,
                         cta: str = None, days: int = 30) -> List[Dict]:
    """
    Найти похожие записи по параметрам.

    Args:
        client_slug: slug клиента
        hook_type: тип хука для поиска
        angle: угол для поиска
        cta: CTA для поиска
        days: за сколько дней искать

    Returns:
        Список похожих записей
    """
    index = load_history_index(client_slug)

    if not index["entries"]:
        index = build_history_index(client_slug)

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    results = []

    for entry in index["entries"]:
        if entry.get("date", "") < cutoff_date:
            continue

        # Проверяем совпадения
        matches = 0
        if hook_type and entry.get("hook_type") == hook_type:
            matches += 1
        if angle and entry.get("angle") == angle:
            matches += 1
        if cta and entry.get("cta") == cta:
            matches += 1

        if matches > 0:
            entry["_match_score"] = matches
            results.append(entry)

    # Сортируем по количеству совпадений
    return sorted(results, key=lambda x: x.get("_match_score", 0), reverse=True)
