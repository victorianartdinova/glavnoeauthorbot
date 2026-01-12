"""
Хранение и управление контент-планами
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

import config


# Форматы, которые защищены от удаления и требуют валидации темы
PROTECTED_FORMATS = ["ЛИДГЕН", "LIDGEN"]


def generate_post_id() -> str:
    """Генерирует уникальный ID поста"""
    return f"post_{uuid.uuid4().hex[:8]}"


def is_protected_format(format_type: str) -> bool:
    """Проверяет, является ли формат защищённым"""
    return format_type.upper() in PROTECTED_FORMATS


def get_plans_dir() -> str:
    """Путь к директории планов"""
    return os.path.join(config.BASE_DIR, "data", "plans")


def get_client_plan_dir(client_slug: str) -> str:
    """Путь к директории планов клиента"""
    return os.path.join(get_plans_dir(), client_slug)


def ensure_plan_dirs(client_slug: str):
    """Создать директории если не существуют"""
    client_dir = get_client_plan_dir(client_slug)
    os.makedirs(client_dir, exist_ok=True)


def save_plan(client_slug: str, days: list, period: int = 7) -> str:
    """
    Сохранить контент-план.

    Args:
        client_slug: slug клиента
        days: список дней [{day, date, format, topic, status}, ...]
        period: период плана в днях

    Returns:
        plan_id (дата создания)
    """
    ensure_plan_dirs(client_slug)

    plan_id = datetime.now().strftime("%Y-%m-%d")

    plan_data = {
        "client": client_slug,
        "created": plan_id,
        "period": period,
        "days": days
    }

    plan_path = os.path.join(get_client_plan_dir(client_slug), f"{plan_id}.json")

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)

    return plan_id


def migrate_day_to_posts(day: dict) -> dict:
    """
    Миграция старого формата дня (один пост) в новый (массив постов).

    Старый: {day, date, format, topic, status}
    Новый: {day, date, posts: [{id, format, topic, protected, status}]}
    """
    if "posts" in day:
        return day  # Уже новый формат

    format_type = day.get("format", "ПОСТ")

    new_day = {
        "day": day["day"],
        "date": day["date"],
        "weekday": day.get("weekday", ""),
        "posts": [{
            "id": generate_post_id(),
            "format": format_type,
            "topic": day.get("topic", ""),
            "protected": is_protected_format(format_type),
            "is_ads": day.get("is_ads", False),
            "status": day.get("status", "pending")
        }]
    }

    # Сохраняем сырой контент если есть
    if day.get("raw_content"):
        new_day["posts"][0]["raw_content"] = day["raw_content"]

    return new_day


def load_plan(client_slug: str, plan_id: Optional[str] = None) -> Optional[dict]:
    """
    Загрузить контент-план.

    Args:
        client_slug: slug клиента
        plan_id: ID плана (дата). Если None — последний план

    Returns:
        dict с планом или None
    """
    client_dir = get_client_plan_dir(client_slug)

    if not os.path.exists(client_dir):
        return None

    if plan_id:
        plan_path = os.path.join(client_dir, f"{plan_id}.json")
    else:
        # Берём последний план
        plans = sorted([f for f in os.listdir(client_dir) if f.endswith(".json")], reverse=True)
        if not plans:
            return None
        plan_path = os.path.join(client_dir, plans[0])

    if not os.path.exists(plan_path):
        return None

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    # Миграция старых планов
    migrated = False
    for i, day in enumerate(plan.get("days", [])):
        if "posts" not in day:
            plan["days"][i] = migrate_day_to_posts(day)
            migrated = True

    # Сохраняем мигрированный план
    if migrated:
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

    return plan


def update_plan_day(client_slug: str, plan_id: str, day_index: int, updates: dict) -> bool:
    """
    Обновить день в плане.

    Args:
        client_slug: slug клиента
        plan_id: ID плана
        day_index: индекс дня (0-based)
        updates: dict с обновлениями {topic: "...", status: "..."}

    Returns:
        True если успешно
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return False

    if day_index < 0 or day_index >= len(plan["days"]):
        return False

    plan["days"][day_index].update(updates)

    plan_path = os.path.join(get_client_plan_dir(client_slug), f"{plan_id}.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    return True


def parse_plan_from_text(plan_text: str, period: int = 7) -> list:
    """
    Парсит текстовый контент-план в структурированный формат.

    Args:
        plan_text: текст плана от Claude
        period: ожидаемое количество дней

    Returns:
        список дней [{day, date, format, topic, status}, ...]
    """
    import re

    days = []

    # Паттерн для поиска дней: "📆 13.01 (Пн)" или "📆 13.01.2026 (Пн)"
    day_pattern = r'📆\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s*\(([^)]+)\)'

    # Разбиваем текст по дням
    parts = re.split(day_pattern, plan_text)

    # parts: [до первого дня, дата1, день_недели1, контент1, дата2, день_недели2, контент2, ...]

    day_num = 1
    for i in range(1, len(parts) - 2, 3):
        date_str = parts[i].strip()
        weekday = parts[i + 1].strip()
        content = parts[i + 2].strip() if i + 2 < len(parts) else ""

        # Извлекаем формат и тему из контента
        # Паттерн: "🏢 ЛИДГЕН: тема" или "🎙 КРУЖОК: тема"
        format_match = re.search(r'([🏢🎙📚📰📸🔥💡✨])\s*([А-ЯA-Z]+)[:\s]+(.+?)(?:\n|📢|📱|$)', content)

        if format_match:
            emoji = format_match.group(1)
            format_type = format_match.group(2).strip()
            topic = format_match.group(3).strip()
        else:
            # Берём первую строку как тему
            first_line = content.split('\n')[0] if content else ""
            format_type = "ПОСТ"
            topic = first_line[:100]

        # Проверяем, для рекламы или канала
        is_ads = "📢" in content or "ADS" in content.upper()

        days.append({
            "day": day_num,
            "date": date_str,
            "weekday": weekday,
            "format": format_type,
            "topic": topic,
            "is_ads": is_ads,
            "status": "pending",
            "raw_content": content[:500]  # Сохраняем сырой контент для контекста
        })

        day_num += 1

    # Если парсинг не удался, создаём дни вручную
    if not days:
        today = datetime.now()
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        for i in range(period):
            day_date = today + timedelta(days=i + 1)
            days.append({
                "day": i + 1,
                "date": day_date.strftime("%d.%m"),
                "weekday": weekday_names[day_date.weekday()],
                "format": "ПОСТ",
                "topic": f"День {i + 1}",
                "is_ads": False,
                "status": "pending",
                "raw_content": ""
            })

    return days


def get_day_display(day: dict) -> str:
    """Форматирует день для отображения (совместимость со старым форматом)"""
    # Новый формат с posts
    if "posts" in day:
        first_post = day["posts"][0] if day["posts"] else {}
        ads_mark = " 📢" if first_post.get("is_ads") else ""
        return f"День {day['day']} ({day['date']}, {day['weekday']}): {first_post.get('format', 'ПОСТ')}{ads_mark}\n{first_post.get('topic', '')}"

    # Старый формат
    ads_mark = " 📢" if day.get("is_ads") else ""
    return f"День {day['day']} ({day['date']}, {day['weekday']}): {day['format']}{ads_mark}\n{day['topic']}"


def get_post_by_id(plan: dict, day_num: int, post_id: str) -> Optional[dict]:
    """Получить пост по ID"""
    for day in plan.get("days", []):
        if day["day"] == day_num:
            for post in day.get("posts", []):
                if post["id"] == post_id:
                    return post
    return None


def update_post(client_slug: str, plan_id: str, day_num: int, post_id: str, updates: dict) -> bool:
    """
    Обновить конкретный пост в дне.

    Args:
        client_slug: slug клиента
        plan_id: ID плана
        day_num: номер дня (1-based)
        post_id: ID поста
        updates: dict с обновлениями

    Returns:
        True если успешно
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return False

    for day in plan["days"]:
        if day["day"] == day_num:
            for post in day.get("posts", []):
                if post["id"] == post_id:
                    post.update(updates)
                    plan_path = os.path.join(get_client_plan_dir(client_slug), f"{plan_id}.json")
                    with open(plan_path, "w", encoding="utf-8") as f:
                        json.dump(plan, f, ensure_ascii=False, indent=2)
                    return True
    return False


def add_post_to_day(client_slug: str, plan_id: str, day_num: int, format_type: str, topic: str, is_ads: bool = False) -> Optional[str]:
    """
    Добавить новый пост к дню.

    Args:
        client_slug: slug клиента
        plan_id: ID плана
        day_num: номер дня (1-based)
        format_type: формат поста (ПРОГРЕВ, ЖИВОЙ, МЕМ)
        topic: тема поста
        is_ads: для рекламы или нет

    Returns:
        ID нового поста или None
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return None

    for day in plan["days"]:
        if day["day"] == day_num:
            new_post = {
                "id": generate_post_id(),
                "format": format_type,
                "topic": topic,
                "protected": is_protected_format(format_type),
                "is_ads": is_ads,
                "status": "pending"
            }
            day["posts"].append(new_post)

            plan_path = os.path.join(get_client_plan_dir(client_slug), f"{plan_id}.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)

            return new_post["id"]
    return None


def delete_post_from_day(client_slug: str, plan_id: str, day_num: int, post_id: str) -> bool:
    """
    Удалить пост из дня (только незащищённые).

    Args:
        client_slug: slug клиента
        plan_id: ID плана
        day_num: номер дня (1-based)
        post_id: ID поста

    Returns:
        True если успешно, False если пост защищён или не найден
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return False

    for day in plan["days"]:
        if day["day"] == day_num:
            for i, post in enumerate(day.get("posts", [])):
                if post["id"] == post_id:
                    # Проверяем защиту
                    if post.get("protected"):
                        return False  # Нельзя удалять защищённые посты

                    day["posts"].pop(i)

                    plan_path = os.path.join(get_client_plan_dir(client_slug), f"{plan_id}.json")
                    with open(plan_path, "w", encoding="utf-8") as f:
                        json.dump(plan, f, ensure_ascii=False, indent=2)

                    return True
    return False
