"""
Утилита для хранения состояния контента
- Чередование форматов (ГИФ/статика)
- Автоматический расчёт даты публикации
"""
import json
import os
from datetime import datetime, timedelta
from typing import Literal

STATE_FILE = "data/content_state.json"

# Форматы лидген-постов (чередуются)
LEADGEN_FORMATS = [
    "GIF_SINGLE",      # ГИФ с 1 УТП
    "GIF_SLIDER",      # ГИФ со слайдерами
    "STATIC"           # Статика
]

DEFAULT_STATE = {
    "last_format_index": -1,  # Начнём с 0 (GIF_SINGLE)
    "last_publish_date": None,
    "briefs_queue": []  # Очередь брифов для контент-плана
}


def _ensure_data_dir():
    """Создать папку data если её нет"""
    os.makedirs("data", exist_ok=True)


def _load_state() -> dict:
    """Загрузить состояние из файла"""
    _ensure_data_dir()
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_STATE.copy()


def _save_state(state: dict):
    """Сохранить состояние в файл"""
    _ensure_data_dir()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_next_format() -> str:
    """
    Получить следующий формат для лидген-поста (чередование)

    Returns:
        "GIF_SINGLE", "GIF_SLIDER" или "STATIC"
    """
    state = _load_state()
    next_index = (state["last_format_index"] + 1) % len(LEADGEN_FORMATS)
    state["last_format_index"] = next_index
    _save_state(state)
    return LEADGEN_FORMATS[next_index]


def get_format_display(format_code: str) -> str:
    """
    Получить отображаемое название формата

    Args:
        format_code: "GIF_SINGLE", "GIF_SLIDER", "STATIC"

    Returns:
        Человекочитаемое название
    """
    display_names = {
        "GIF_SINGLE": "ГИФ (1 УТП)",
        "GIF_SLIDER": "ГИФ (слайдеры)",
        "STATIC": "Статика"
    }
    return display_names.get(format_code, format_code)


def get_next_publish_date(days_ahead: int = 0) -> tuple[str, str]:
    """
    Получить следующую дату публикации (только будни)

    Args:
        days_ahead: сколько дней добавить к текущей дате

    Returns:
        tuple (дата в формате "13.01", день недели "Пн")
    """
    state = _load_state()

    # Начинаем с завтра
    if state["last_publish_date"]:
        last_date = datetime.strptime(state["last_publish_date"], "%Y-%m-%d")
        next_date = last_date + timedelta(days=1)
    else:
        next_date = datetime.now() + timedelta(days=1)

    next_date += timedelta(days=days_ahead)

    # Пропускаем выходные (5=Сб, 6=Вс)
    while next_date.weekday() >= 5:
        next_date += timedelta(days=1)

    # Сохраняем
    state["last_publish_date"] = next_date.strftime("%Y-%m-%d")
    _save_state(state)

    weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    date_str = next_date.strftime("%d.%m")
    weekday_str = weekday_names[next_date.weekday()]

    return date_str, weekday_str


def reset_publish_dates():
    """Сбросить счётчик дат (начать с завтра)"""
    state = _load_state()
    state["last_publish_date"] = None
    _save_state(state)


def add_brief_to_queue(brief_data: dict):
    """
    Добавить бриф в очередь для контент-плана

    Args:
        brief_data: словарь с данными брифа
    """
    state = _load_state()
    state["briefs_queue"].append({
        **brief_data,
        "added_at": datetime.now().isoformat()
    })
    _save_state(state)


def get_briefs_queue() -> list:
    """Получить очередь брифов"""
    state = _load_state()
    return state.get("briefs_queue", [])


def clear_briefs_queue():
    """Очистить очередь брифов"""
    state = _load_state()
    state["briefs_queue"] = []
    _save_state(state)


def peek_next_format() -> str:
    """
    Посмотреть следующий формат БЕЗ его использования
    (для предпросмотра)
    """
    state = _load_state()
    next_index = (state["last_format_index"] + 1) % len(LEADGEN_FORMATS)
    return LEADGEN_FORMATS[next_index]
