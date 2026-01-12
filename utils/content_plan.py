"""
Утилита для работы с контент-планом
- Накопление брифов
- Генерация недельного плана
- Отправка в рабочую группу
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

PLAN_FILE = "data/content_plan.json"


def _ensure_data_dir():
    """Создать папку data если её нет"""
    os.makedirs("data", exist_ok=True)


def _load_plan() -> dict:
    """Загрузить план из файла"""
    _ensure_data_dir()
    if os.path.exists(PLAN_FILE):
        with open(PLAN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "briefs": [],
        "week_start": None,
        "status": "draft"  # draft, pending_approval, approved
    }


def _save_plan(plan: dict):
    """Сохранить план в файл"""
    _ensure_data_dir()
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def add_brief(brief_data: dict) -> int:
    """
    Добавить бриф в план

    Args:
        brief_data: данные брифа (date, format, ad_type, summary)

    Returns:
        Количество брифов в плане
    """
    plan = _load_plan()
    brief_data["added_at"] = datetime.now().isoformat()
    plan["briefs"].append(brief_data)

    if not plan["week_start"]:
        plan["week_start"] = datetime.now().strftime("%Y-%m-%d")

    _save_plan(plan)
    return len(plan["briefs"])


def get_briefs() -> list:
    """Получить все брифы в плане"""
    plan = _load_plan()
    return plan.get("briefs", [])


def clear_plan():
    """Очистить план"""
    _save_plan({
        "briefs": [],
        "week_start": None,
        "status": "draft"
    })


def format_plan_for_group() -> str:
    """
    Сформировать текст контент-плана для отправки в рабочую группу

    Returns:
        Форматированный текст плана
    """
    plan = _load_plan()
    briefs = plan.get("briefs", [])

    if not briefs:
        return "📋 Контент-план пуст"

    # Группируем по датам
    by_date = {}
    for brief in briefs:
        date = brief.get("date", "Без даты")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(brief)

    # Формируем текст
    lines = ["📋 КОНТЕНТ-ПЛАН НА НЕДЕЛЮ", ""]

    for date, items in sorted(by_date.items()):
        weekday = items[0].get("weekday", "")
        lines.append(f"📅 {date} ({weekday})")

        for item in items:
            format_type = item.get("format", "")
            ad_type = item.get("ad_type", "")
            summary = item.get("summary", item.get("designer_brief", ""))[:100]

            lines.append(f"  🎬 {format_type} | {ad_type}")
            if summary:
                lines.append(f"  📝 {summary}...")

        lines.append("")

    lines.append(f"Всего постов: {len(briefs)}")

    return "\n".join(lines)


def set_plan_status(status: str):
    """
    Установить статус плана

    Args:
        status: draft, pending_approval, approved
    """
    plan = _load_plan()
    plan["status"] = status
    _save_plan(plan)


def get_plan_status() -> str:
    """Получить статус плана"""
    plan = _load_plan()
    return plan.get("status", "draft")


def generate_week_dates(start_from: datetime = None) -> list:
    """
    Сгенерировать даты на неделю (только будни)

    Args:
        start_from: начальная дата (по умолчанию завтра)

    Returns:
        Список кортежей (дата, день_недели)
    """
    if start_from is None:
        start_from = datetime.now() + timedelta(days=1)

    dates = []
    current = start_from
    weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    while len(dates) < 5:  # 5 будних дней
        if current.weekday() < 5:  # Пн-Пт
            dates.append((
                current.strftime("%d.%m"),
                weekday_names[current.weekday()]
            ))
        current += timedelta(days=1)

    return dates
