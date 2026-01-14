"""
Хранилище лотов (LOT CARD) — source of truth для "Пакет по лоту"
"""
import json
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import config


def get_lots_dir() -> str:
    """Путь к директории лотов"""
    return os.path.join(config.BASE_DIR, "data", "lots")


def get_client_lots_path(client_slug: str) -> str:
    """Путь к файлу лотов клиента"""
    return os.path.join(get_lots_dir(), client_slug, "lots.json")


def ensure_lots_dir(client_slug: str):
    """Создать директории если не существуют"""
    lots_dir = os.path.join(get_lots_dir(), client_slug)
    os.makedirs(lots_dir, exist_ok=True)


def generate_lot_id() -> str:
    """Генерирует уникальный ID лота"""
    return f"lot_{uuid.uuid4().hex[:8]}"


def get_default_lot() -> Dict[str, Any]:
    """Дефолтная структура лота"""
    return {
        "lot_id": "",
        "url": "",
        "title": "",
        "utp": [],
        "numbers": {
            "price": "",
            "payment": "",
            "deadline": "",
            "metro": ""
        },
        "features": [],
        "audience": "",
        "disclaimer": "",
        "ban_phrases": [],
        "created_at": "",
        "source": "manual"
    }


def load_lots(client_slug: str) -> List[Dict]:
    """
    Загрузить все лоты клиента.

    Returns:
        List лотов
    """
    lots_path = get_client_lots_path(client_slug)

    if not os.path.exists(lots_path):
        return []

    try:
        with open(lots_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Backward compat: если старый формат (dict), конвертим
            if isinstance(data, dict):
                return data.get("lots", [])
            return data
    except (json.JSONDecodeError, IOError):
        return []


def save_lots(client_slug: str, lots: List[Dict]):
    """Сохранить лоты клиента"""
    ensure_lots_dir(client_slug)
    lots_path = get_client_lots_path(client_slug)

    with open(lots_path, "w", encoding="utf-8") as f:
        json.dump(lots, f, ensure_ascii=False, indent=2)


def create_lot_from_facts(
    client_slug: str,
    url: str,
    facts_text: str,
    title: str = ""
) -> Dict[str, Any]:
    """
    Создать лот из текстовых фактов (manual-first подход).

    Args:
        client_slug: slug клиента
        url: URL проекта (может быть пустым)
        facts_text: текст с фактами (буллетами)
        title: название лота (опционально)

    Returns:
        Созданный лот
    """
    lot = get_default_lot()
    lot["lot_id"] = generate_lot_id()
    lot["url"] = url
    lot["created_at"] = datetime.now().isoformat()
    lot["source"] = "url" if url else "manual"

    # Парсим факты из текста
    parsed = parse_facts_from_text(facts_text)
    lot["title"] = title or parsed.get("title", "")
    lot["utp"] = parsed.get("utp", [])
    lot["numbers"] = parsed.get("numbers", lot["numbers"])
    lot["features"] = parsed.get("features", [])
    lot["audience"] = parsed.get("audience", "")

    # Сохраняем
    lots = load_lots(client_slug)
    lots.append(lot)
    save_lots(client_slug, lots)

    return lot


def parse_facts_from_text(text: str) -> Dict[str, Any]:
    """
    Парсит текстовые факты в структуру лота.

    Ожидаемый формат:
    - УТП 1
    - УТП 2
    Цена: от 25 млн
    Платеж: 150 тыс/мес
    Метро: 5 мин до Спартак
    """
    result = {
        "title": "",
        "utp": [],
        "numbers": {
            "price": "",
            "payment": "",
            "deadline": "",
            "metro": ""
        },
        "features": [],
        "audience": ""
    }

    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        line_lower = line.lower()

        # Числовые параметры
        if any(k in line_lower for k in ["цена", "от", "млн", "руб"]) and ":" in line:
            result["numbers"]["price"] = line.split(":", 1)[-1].strip()
        elif any(k in line_lower for k in ["платеж", "ежемес", "тыс/мес"]) and ":" in line:
            result["numbers"]["payment"] = line.split(":", 1)[-1].strip()
        elif any(k in line_lower for k in ["сдача", "срок", "дедлайн"]) and ":" in line:
            result["numbers"]["deadline"] = line.split(":", 1)[-1].strip()
        elif any(k in line_lower for k in ["метро", "мин", "пешком"]) and ":" in line:
            result["numbers"]["metro"] = line.split(":", 1)[-1].strip()
        elif any(k in line_lower for k in ["аудитория", "для кого"]) and ":" in line:
            result["audience"] = line.split(":", 1)[-1].strip()
        # УТП — строки с буллетами
        elif line.startswith(("-", "•", "▪", "✓", "✔", "*")):
            utp = line.lstrip("-•▪✓✔* ").strip()
            if utp:
                result["utp"].append(utp)
        # Первая строка без маркера — возможно название
        elif not result["title"] and len(line) < 100:
            result["title"] = line

    return result


def get_lot_by_id(client_slug: str, lot_id: str) -> Optional[Dict]:
    """Получить лот по ID"""
    lots = load_lots(client_slug)
    for lot in lots:
        if lot.get("lot_id") == lot_id:
            return lot
    return None


def get_recent_lots(client_slug: str, limit: int = 5) -> List[Dict]:
    """Получить последние N лотов"""
    lots = load_lots(client_slug)
    # Сортируем по дате создания (desc)
    sorted_lots = sorted(
        lots,
        key=lambda x: x.get("created_at", ""),
        reverse=True
    )
    return sorted_lots[:limit]


def delete_lot(client_slug: str, lot_id: str) -> bool:
    """Удалить лот"""
    lots = load_lots(client_slug)
    for i, lot in enumerate(lots):
        if lot.get("lot_id") == lot_id:
            lots.pop(i)
            save_lots(client_slug, lots)
            return True
    return False


def format_lot_for_prompt(lot: Dict) -> str:
    """
    Форматировать лот для включения в промпт Claude.

    Returns:
        Строка с данными лота для генерации
    """
    lines = ["ДАННЫЕ ЛОТА:"]

    if lot.get("title"):
        lines.append(f"Название: {lot['title']}")

    if lot.get("url"):
        lines.append(f"URL: {lot['url']}")

    numbers = lot.get("numbers", {})
    if numbers.get("price"):
        lines.append(f"Цена: {numbers['price']}")
    if numbers.get("payment"):
        lines.append(f"Платёж: {numbers['payment']}")
    if numbers.get("metro"):
        lines.append(f"Метро: {numbers['metro']}")
    if numbers.get("deadline"):
        lines.append(f"Сдача: {numbers['deadline']}")

    if lot.get("utp"):
        lines.append("\nУТП:")
        for utp in lot["utp"]:
            lines.append(f"• {utp}")

    if lot.get("features"):
        lines.append("\nОсобенности:")
        for feat in lot["features"]:
            lines.append(f"• {feat}")

    if lot.get("audience"):
        lines.append(f"\nАудитория: {lot['audience']}")

    if lot.get("ban_phrases"):
        lines.append(f"\nЗАПРЕЩЕНО: {', '.join(lot['ban_phrases'])}")

    return "\n".join(lines)
