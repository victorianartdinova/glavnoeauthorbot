"""
Хранение и управление контент-планами
Теперь использует SQLite вместо JSON
"""
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from utils.database import db_connection, PlansStore


# Форматы, которые защищены от удаления и требуют валидации темы
PROTECTED_FORMATS = ["ЛИДГЕН", "LIDGEN"]


def is_protected_format(format_type: str) -> bool:
    """Проверяет, является ли формат защищённым"""
    return format_type.upper() in PROTECTED_FORMATS


def save_plan(client_slug: str, days: list, period: int = 7) -> int:
    """
    Сохранить контент-план.

    Args:
        client_slug: slug клиента
        days: список дней [{day, date, weekday, format, topic, is_ads, status, raw_content}, ...]
        period: период плана в днях

    Returns:
        plan_id
    """
    with db_connection() as conn:
        store = PlansStore(conn)

        # Создаём план
        plan_id = store.create(client_slug, period)

        # Добавляем дни и посты
        for day_data in days:
            day_id = store.add_day(
                plan_id=plan_id,
                day_num=day_data.get("day", 1),
                date=day_data.get("date", ""),
                weekday=day_data.get("weekday", "")
            )

            # Если старый формат (без posts)
            if "posts" not in day_data:
                format_type = day_data.get("format", "ПОСТ")
                store.add_post_to_day(
                    plan_day_id=day_id,
                    format=format_type,
                    topic=day_data.get("topic", ""),
                    is_ads=day_data.get("is_ads", False),
                    protected=is_protected_format(format_type),
                    raw_content=day_data.get("raw_content", "")
                )
            else:
                # Новый формат с массивом posts
                for post in day_data.get("posts", []):
                    store.add_post_to_day(
                        plan_day_id=day_id,
                        format=post.get("format", "ПОСТ"),
                        topic=post.get("topic", ""),
                        is_ads=post.get("is_ads", False),
                        protected=post.get("protected", False),
                        raw_content=post.get("raw_content", "")
                    )

    return plan_id


def load_plan(client_slug: str, plan_id: Optional[int] = None) -> Optional[dict]:
    """
    Загрузить контент-план.

    Args:
        client_slug: slug клиента
        plan_id: ID плана. Если None — последний план

    Returns:
        dict с планом или None
    """
    with db_connection() as conn:
        store = PlansStore(conn)

        if plan_id:
            plan = store.get(plan_id)
        else:
            plan = store.get_latest(client_slug)

        if not plan:
            return None

        # Конвертируем в старый формат для совместимости
        return _plan_to_legacy_format(plan)


def _plan_to_legacy_format(plan: Dict) -> Dict:
    """Конвертировать план из БД в старый формат"""
    legacy = {
        "client": plan.get("client_id", ""),
        "created": plan.get("created_at", ""),
        "period": plan.get("period", 7),
        "plan_id": plan.get("id"),  # Добавляем для удобства
        "days": []
    }

    for day in plan.get("days", []):
        legacy_day = {
            "day": day.get("day_num", 1),
            "date": day.get("date", ""),
            "weekday": day.get("weekday", ""),
            "day_id": day.get("id"),  # ID дня в БД
            "posts": []
        }

        for post in day.get("posts", []):
            legacy_post = {
                "id": f"post_{post['id']}",
                "db_id": post["id"],  # ID в БД для обновлений
                "format": post.get("format", "ПОСТ"),
                "topic": post.get("topic", ""),
                "protected": bool(post.get("protected", 0)),
                "is_ads": bool(post.get("is_ads", 0)),
                "status": post.get("status", "pending"),
                "raw_content": post.get("raw_content", "")
            }
            if post.get("post_id"):
                legacy_post["linked_post_id"] = post["post_id"]
            legacy_day["posts"].append(legacy_post)

        legacy["days"].append(legacy_day)

    return legacy


def update_plan_day(client_slug: str, plan_id: int, day_index: int, updates: dict) -> bool:
    """
    Обновить день в плане (устаревший метод, для совместимости).
    Лучше использовать update_post напрямую.
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return False

    if day_index < 0 or day_index >= len(plan["days"]):
        return False

    # Обновляем первый пост дня
    day = plan["days"][day_index]
    if day["posts"]:
        post = day["posts"][0]
        return update_post(client_slug, plan_id, day["day"], post["db_id"], updates)

    return False


def get_day_display(day: dict) -> str:
    """Форматирует день для отображения"""
    first_post = day["posts"][0] if day.get("posts") else {}
    ads_mark = " 📢" if first_post.get("is_ads") else ""
    return f"День {day['day']} ({day['date']}, {day['weekday']}): {first_post.get('format', 'ПОСТ')}{ads_mark}\n{first_post.get('topic', '')}"


def get_post_by_id(plan: dict, day_num: int, post_id: str) -> Optional[dict]:
    """Получить пост по ID (строковому)"""
    for day in plan.get("days", []):
        if day["day"] == day_num:
            for post in day.get("posts", []):
                if post["id"] == post_id:
                    return post
    return None


def update_post(client_slug: str, plan_id: int, day_num: int, post_db_id: int, updates: dict) -> bool:
    """
    Обновить конкретный пост в дне.

    Args:
        client_slug: slug клиента
        plan_id: ID плана
        day_num: номер дня (1-based)
        post_db_id: ID поста в БД (plan_posts.id)
        updates: dict с обновлениями

    Returns:
        True если успешно
    """
    with db_connection() as conn:
        store = PlansStore(conn)
        return store.update_plan_post(post_db_id, **updates)


def add_post_to_day(client_slug: str, plan_id: int, day_num: int, format_type: str, topic: str, is_ads: bool = False) -> Optional[int]:
    """
    Добавить новый пост к дню.

    Args:
        client_slug: slug клиента
        plan_id: ID плана
        day_num: номер дня (1-based)
        format_type: формат поста
        topic: тема поста
        is_ads: для рекламы или нет

    Returns:
        ID нового поста или None
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return None

    # Находим day_id
    for day in plan["days"]:
        if day["day"] == day_num:
            day_id = day.get("day_id")
            if not day_id:
                return None

            with db_connection() as conn:
                store = PlansStore(conn)
                return store.add_post_to_day(
                    plan_day_id=day_id,
                    format=format_type,
                    topic=topic,
                    is_ads=is_ads,
                    protected=is_protected_format(format_type)
                )

    return None


def delete_post_from_day(client_slug: str, plan_id: int, day_num: int, post_db_id: int) -> bool:
    """
    Удалить пост из дня (только незащищённые).
    """
    plan = load_plan(client_slug, plan_id)
    if not plan:
        return False

    for day in plan["days"]:
        if day["day"] == day_num:
            for post in day.get("posts", []):
                if post["db_id"] == post_db_id:
                    if post.get("protected"):
                        return False  # Нельзя удалять защищённые

                    with db_connection() as conn:
                        conn.execute("DELETE FROM plan_posts WHERE id = ?", (post_db_id,))
                        conn.commit()
                    return True
    return False


def delete_plan(client_slug: str, plan_id: Optional[int] = None) -> bool:
    """
    Удалить контент-план.
    """
    if plan_id is None:
        plan = load_plan(client_slug)
        if not plan:
            return False
        plan_id = plan.get("plan_id")

    if not plan_id:
        return False

    with db_connection() as conn:
        store = PlansStore(conn)
        return store.delete(plan_id)


def list_plans(client_slug: str) -> List[Dict]:
    """
    Получить список планов клиента (от новых к старым).
    """
    with db_connection() as conn:
        store = PlansStore(conn)
        return store.list_plans(client_slug)


def parse_plan_from_text(plan_text: str, period: int = 7) -> list:
    """
    Парсит текстовый контент-план в структурированный формат.

    Args:
        plan_text: текст плана от Claude
        period: ожидаемое количество дней

    Returns:
        список дней [{day, date, format, topic, status}, ...]
    """
    days = []

    # Паттерн для поиска дней: "📆 13.01 (Пн)" или "📆 13.01.2026 (Пн)"
    day_pattern = r'📆\s*(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s*\(([^)]+)\)'

    # Разбиваем текст по дням
    parts = re.split(day_pattern, plan_text)

    day_num = 1
    for i in range(1, len(parts) - 2, 3):
        date_str = parts[i].strip()
        weekday = parts[i + 1].strip()
        content = parts[i + 2].strip() if i + 2 < len(parts) else ""

        # Извлекаем формат и тему из контента
        format_match = re.search(r'([🏢🎙📚📰📸🔥💡✨])\s*([А-ЯA-Z]+)[:\s]+(.+?)(?:\n|📢|📱|$)', content)

        if format_match:
            format_type = format_match.group(2).strip()
            topic = format_match.group(3).strip()
        else:
            first_line = content.split('\n')[0] if content else ""
            format_type = "ПОСТ"
            topic = first_line[:100]

        is_ads = "📢" in content or "ADS" in content.upper()

        days.append({
            "day": day_num,
            "date": date_str,
            "weekday": weekday,
            "format": format_type,
            "topic": topic,
            "is_ads": is_ads,
            "status": "pending",
            "raw_content": content[:500]
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


# ============
# Функция миграции JSON -> SQLite
# ============

def migrate_plans_to_sqlite():
    """
    Миграция планов из старых JSON файлов в SQLite.
    """
    import json
    import os
    import config

    json_dir = os.path.join(config.BASE_DIR, "data", "plans")

    if not os.path.exists(json_dir):
        print("Нет планов для миграции")
        return

    migrated = 0
    for client_slug in os.listdir(json_dir):
        client_dir = os.path.join(json_dir, client_slug)
        if not os.path.isdir(client_dir):
            continue

        for plan_file in os.listdir(client_dir):
            if not plan_file.endswith(".json"):
                continue

            plan_path = os.path.join(client_dir, plan_file)
            print(f"Мигрирую {client_slug}/{plan_file}...")

            with open(plan_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)

            # Сохраняем план в SQLite
            save_plan(
                client_slug=client_slug,
                days=plan_data.get("days", []),
                period=plan_data.get("period", 7)
            )

            # Переименовываем
            backup_path = plan_path + ".migrated"
            os.rename(plan_path, backup_path)
            migrated += 1

    print(f"\nМигрировано планов: {migrated}")


# Для запуска: python -c "from utils.plan_storage import migrate_plans_to_sqlite; migrate_plans_to_sqlite()"
