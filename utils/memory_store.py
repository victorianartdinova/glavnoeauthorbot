"""
Хранилище памяти клиента — weekly_focus + long_term настройки
"""
import json
import os
from datetime import datetime
from typing import Optional, List, Dict
import uuid

import config


def get_memory_dir() -> str:
    """Путь к директории памяти"""
    return os.path.join(config.BASE_DIR, "data", "memory")


def get_client_memory_path(client_slug: str) -> str:
    """Путь к файлу памяти клиента"""
    return os.path.join(get_memory_dir(), client_slug, "memory.json")


def ensure_memory_dir(client_slug: str):
    """Создать директории если не существуют"""
    memory_dir = os.path.join(get_memory_dir(), client_slug)
    os.makedirs(memory_dir, exist_ok=True)


def get_default_memory() -> Dict:
    """Дефолтная структура памяти"""
    return {
        "weekly_focus": {
            "lots": [],
            "updated_at": None
        },
        "long_term": {
            "brand_voice_notes": [],
            "banned_phrases": [],
            "preferred_cta": []
        }
    }


def load_memory(client_slug: str) -> Dict:
    """
    Загрузить память клиента.

    Returns:
        Dict с weekly_focus и long_term
    """
    memory_path = get_client_memory_path(client_slug)

    if not os.path.exists(memory_path):
        return get_default_memory()

    try:
        with open(memory_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return get_default_memory()


def save_memory(client_slug: str, memory: Dict):
    """Сохранить память клиента"""
    ensure_memory_dir(client_slug)
    memory_path = get_client_memory_path(client_slug)

    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


# === WEEKLY FOCUS (ЛОТЫ) ===

def generate_lot_id() -> str:
    """Генерирует уникальный ID лота"""
    return f"lot_{uuid.uuid4().hex[:8]}"


def add_focus_lot(
    client_slug: str,
    name: str,
    price_from: Optional[int] = None,
    key_features: Optional[List[str]] = None,
    priority: int = 1
) -> str:
    """
    Добавить лот в фокус недели.

    Args:
        client_slug: slug клиента
        name: название ЖК/лота
        price_from: цена от (опционально)
        key_features: ключевые особенности
        priority: приоритет (1 = высший)

    Returns:
        ID добавленного лота
    """
    memory = load_memory(client_slug)

    lot_id = generate_lot_id()
    lot = {
        "id": lot_id,
        "name": name,
        "price_from": price_from,
        "key_features": key_features or [],
        "priority": priority,
        "added_at": datetime.now().strftime("%Y-%m-%d")
    }

    memory["weekly_focus"]["lots"].append(lot)
    memory["weekly_focus"]["updated_at"] = datetime.now().isoformat()

    save_memory(client_slug, memory)
    return lot_id


def remove_focus_lot(client_slug: str, lot_id: str) -> bool:
    """Удалить лот из фокуса"""
    memory = load_memory(client_slug)
    lots = memory["weekly_focus"]["lots"]

    for i, lot in enumerate(lots):
        if lot["id"] == lot_id:
            lots.pop(i)
            memory["weekly_focus"]["updated_at"] = datetime.now().isoformat()
            save_memory(client_slug, memory)
            return True

    return False


def clear_focus_lots(client_slug: str):
    """Очистить все лоты из фокуса"""
    memory = load_memory(client_slug)
    memory["weekly_focus"]["lots"] = []
    memory["weekly_focus"]["updated_at"] = datetime.now().isoformat()
    save_memory(client_slug, memory)


def get_focus_lots(client_slug: str) -> List[Dict]:
    """Получить лоты в фокусе (отсортированы по приоритету)"""
    memory = load_memory(client_slug)
    lots = memory["weekly_focus"]["lots"]
    return sorted(lots, key=lambda x: x.get("priority", 99))


def set_focus_lots(client_slug: str, lots: List[Dict]):
    """
    Установить лоты в фокус (замена всех).

    Args:
        client_slug: slug клиента
        lots: список лотов [{name, price_from, key_features, priority}]
    """
    memory = load_memory(client_slug)

    # Генерируем ID для лотов без них
    for lot in lots:
        if "id" not in lot:
            lot["id"] = generate_lot_id()
        if "added_at" not in lot:
            lot["added_at"] = datetime.now().strftime("%Y-%m-%d")

    memory["weekly_focus"]["lots"] = lots
    memory["weekly_focus"]["updated_at"] = datetime.now().isoformat()

    save_memory(client_slug, memory)


# === LONG TERM ===

def add_banned_phrase(client_slug: str, phrase: str):
    """Добавить запрещённую фразу"""
    memory = load_memory(client_slug)
    if phrase not in memory["long_term"]["banned_phrases"]:
        memory["long_term"]["banned_phrases"].append(phrase)
        save_memory(client_slug, memory)


def remove_banned_phrase(client_slug: str, phrase: str):
    """Удалить запрещённую фразу"""
    memory = load_memory(client_slug)
    if phrase in memory["long_term"]["banned_phrases"]:
        memory["long_term"]["banned_phrases"].remove(phrase)
        save_memory(client_slug, memory)


def get_banned_phrases(client_slug: str) -> List[str]:
    """Получить список запрещённых фраз"""
    memory = load_memory(client_slug)
    return memory["long_term"]["banned_phrases"]


def add_preferred_cta(client_slug: str, cta: str):
    """Добавить предпочитаемый CTA"""
    memory = load_memory(client_slug)
    if cta not in memory["long_term"]["preferred_cta"]:
        memory["long_term"]["preferred_cta"].append(cta)
        save_memory(client_slug, memory)


def get_preferred_cta(client_slug: str) -> List[str]:
    """Получить предпочитаемые CTA"""
    memory = load_memory(client_slug)
    return memory["long_term"]["preferred_cta"]


# === ФОРМАТИРОВАНИЕ ДЛЯ ПРОМПТА ===

def format_focus_lots_for_prompt(client_slug: str, max_lots: int = 3) -> str:
    """
    Форматировать лоты фокуса для включения в промпт.

    Args:
        client_slug: slug клиента
        max_lots: максимум лотов в промпте (лимитер)

    Returns:
        Строка для system prompt
    """
    lots = get_focus_lots(client_slug)

    if not lots:
        return ""

    # Лимитер: берём только top-N по приоритету
    lots = lots[:max_lots]

    lines = ["ФОКУС НЕДЕЛИ — приоритетные лоты для продвижения:"]

    for i, lot in enumerate(lots, 1):
        line = f"{i}. {lot['name']}"
        if lot.get("price_from"):
            line += f" (от {lot['price_from']:,} ₽)".replace(",", " ")
        if lot.get("key_features"):
            line += f" — {', '.join(lot['key_features'])}"
        lines.append(line)

    lines.append("")
    lines.append("Отдавай приоритет этим лотам при генерации контента.")

    return "\n".join(lines)


def format_banned_phrases_for_prompt(client_slug: str) -> str:
    """
    Форматировать запрещённые фразы для промпта.

    Returns:
        Строка для system prompt
    """
    phrases = get_banned_phrases(client_slug)

    if not phrases:
        return ""

    return f"ЗАПРЕЩЁННЫЕ ФРАЗЫ (НЕ использовать): {', '.join(phrases)}"
