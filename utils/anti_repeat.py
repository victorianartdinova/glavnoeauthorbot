"""
Антиповторы — формирование списка "не повторять" для промптов
"""
from typing import List, Dict, Optional
from collections import Counter

from utils.history_index import (
    load_history_index, build_history_index, get_recent_entries, get_stats
)


def get_overused_hooks(client_slug: str, threshold: int = 3) -> List[str]:
    """
    Получить переиспользованные типы хуков (отсортированы по частоте desc).

    Args:
        client_slug: slug клиента
        threshold: порог частоты для "переиспользования"

    Returns:
        Список хуков, которых слишком много (сначала самые частые)
    """
    stats = get_stats(client_slug)
    hooks = stats.get("hooks", {})

    # Фильтруем (исключаем unknown) и сортируем по частоте (desc)
    overused = [(hook, count) for hook, count in hooks.items()
                if count >= threshold and hook != "unknown"]
    overused.sort(key=lambda x: x[1], reverse=True)
    return [hook for hook, count in overused]


def get_overused_ctas(client_slug: str, threshold: int = 2) -> List[str]:
    """
    Получить переиспользованные CTA (отсортированы по частоте desc).

    Args:
        client_slug: slug клиента
        threshold: порог частоты

    Returns:
        Список CTA, которых слишком много (сначала самые частые)
    """
    stats = get_stats(client_slug)
    ctas = stats.get("ctas", {})

    # Фильтруем и сортируем по частоте (desc)
    overused = [(cta, count) for cta, count in ctas.items() if count >= threshold]
    overused.sort(key=lambda x: x[1], reverse=True)
    return [cta for cta, count in overused]


def get_overused_angles(client_slug: str, threshold: int = 2) -> List[str]:
    """
    Получить переиспользованные углы (отсортированы по частоте desc).

    Args:
        client_slug: slug клиента
        threshold: порог частоты

    Returns:
        Список углов, которых слишком много (сначала самые частые)
    """
    stats = get_stats(client_slug)
    angles = stats.get("angles", {})

    # Фильтруем (исключаем unknown) и сортируем по частоте (desc)
    overused = [(angle, count) for angle, count in angles.items()
                if count >= threshold and angle != "unknown"]
    overused.sort(key=lambda x: x[1], reverse=True)
    return [angle for angle, count in overused]


def get_recent_topics(client_slug: str, days: int = 7) -> List[str]:
    """
    Получить темы за последние N дней.

    Args:
        client_slug: slug клиента
        days: количество дней

    Returns:
        Список всех использованных тем
    """
    entries = get_recent_entries(client_slug, days)

    topics = []
    for entry in entries:
        topics.extend(entry.get("topics", []))

    return list(set(topics))


def get_recent_lot_names(client_slug: str, days: int = 7) -> List[str]:
    """
    Получить названия лотов за последние N дней.

    Args:
        client_slug: slug клиента
        days: количество дней

    Returns:
        Список названий лотов
    """
    entries = get_recent_entries(client_slug, days)

    lot_names = []
    for entry in entries:
        if entry.get("lot_name"):
            lot_names.append(entry["lot_name"])

    return list(set(lot_names))


def build_do_not_repeat_list(client_slug: str) -> Dict:
    """
    Сформировать полный список "не повторять".

    Args:
        client_slug: slug клиента

    Returns:
        Dict с категориями того, что не повторять:
        {
            "hooks": [...],
            "ctas": [...],
            "angles": [...],
            "recent_topics": [...],
            "recent_lots": [...]
        }
    """
    return {
        "hooks": get_overused_hooks(client_slug, threshold=3),
        "ctas": get_overused_ctas(client_slug, threshold=2),
        "angles": get_overused_angles(client_slug, threshold=2),
        "recent_topics": get_recent_topics(client_slug, days=7),
        "recent_lots": get_recent_lot_names(client_slug, days=7)
    }


def format_do_not_repeat_for_prompt(
    client_slug: str,
    max_hooks: int = 3,
    max_ctas: int = 5,
    max_angles: int = 5,
    max_lots: int = 3
) -> str:
    """
    Форматировать список антиповторов для включения в промпт.

    Args:
        client_slug: slug клиента
        max_hooks: максимум хуков в списке
        max_ctas: максимум CTA в списке
        max_angles: максимум углов в списке
        max_lots: максимум лотов в списке

    Returns:
        Строка для system prompt
    """
    dnr = build_do_not_repeat_list(client_slug)

    lines = []

    # Проверяем, есть ли что добавить
    has_content = any([
        dnr["hooks"],
        dnr["ctas"],
        dnr["angles"],
        dnr["recent_topics"],
        dnr["recent_lots"]
    ])

    if not has_content:
        return ""

    lines.append("АНТИПОВТОРЫ — избегай этого в новом контенте:")
    lines.append("")

    if dnr["hooks"]:
        hooks_map = {
            "financial": "финансовый (цены, рассрочка)",
            "location": "локационный (метро, близость)",
            "premium": "премиум (статус, эксклюзив)",
            "urgency": "срочность (последние, успей)",
            "emotional": "эмоциональный (мечта, комфорт)"
        }
        # Лимитер: берём топ-N по частоте (уже отсортированы в build_do_not_repeat_list)
        limited_hooks = dnr["hooks"][:max_hooks]
        readable_hooks = [hooks_map.get(h, h) for h in limited_hooks]
        lines.append(f"• Хуки (использованы часто): {', '.join(readable_hooks)}")

    if dnr["ctas"]:
        # Лимитер: топ-N CTA
        limited_ctas = dnr["ctas"][:max_ctas]
        lines.append(f"• CTA (уже были): {', '.join(limited_ctas)}")

    if dnr["angles"]:
        # Лимитер: топ-N углов
        limited_angles = dnr["angles"][:max_angles]
        lines.append(f"• Углы (повторялись): {', '.join(limited_angles)}")

    if dnr["recent_lots"]:
        # Лимитер: топ-N лотов
        limited_lots = dnr["recent_lots"][:max_lots]
        lines.append(f"• Лоты за 7 дней: {', '.join(limited_lots)}")

    lines.append("")
    lines.append("Используй ДРУГИЕ хуки, углы и CTA для разнообразия.")

    return "\n".join(lines)


def suggest_alternative_hook(client_slug: str) -> Optional[str]:
    """
    Предложить альтернативный хук на основе статистики.

    Returns:
        Тип хука, который использовался реже всего
    """
    stats = get_stats(client_slug)
    hooks = stats.get("hooks", {})

    all_hooks = ["financial", "location", "premium", "urgency", "emotional"]

    # Находим наименее использованный
    min_count = float("inf")
    best_hook = None

    for hook in all_hooks:
        count = hooks.get(hook, 0)
        if count < min_count:
            min_count = count
            best_hook = hook

    return best_hook


def suggest_alternative_cta(client_slug: str, exclude: List[str] = None) -> str:
    """
    Предложить альтернативный CTA.

    Args:
        client_slug: slug клиента
        exclude: список CTA для исключения

    Returns:
        Предложенный CTA
    """
    exclude = exclude or []
    stats = get_stats(client_slug)
    used_ctas = set(stats.get("ctas", {}).keys())
    used_ctas.update(exclude)

    # Базовые CTA
    base_ctas = [
        "ПОДРОБНЕЕ", "ХОЧУ", "УЗНАТЬ", "ПОКАЗАТЬ",
        "ИНТЕРЕСНО", "РАСЧЁТ", "КОНСУЛЬТАЦИЯ", "ПОДБОР"
    ]

    # Возвращаем первый неиспользованный
    for cta in base_ctas:
        if cta not in used_ctas:
            return cta

    # Если все использованы — вернуть самый редкий
    ctas_count = stats.get("ctas", {})
    if ctas_count:
        return min(ctas_count.keys(), key=lambda x: ctas_count[x])

    return "ПОДРОБНЕЕ"


def get_format_balance_suggestion(client_slug: str) -> Optional[str]:
    """
    Предложить формат для баланса контента.

    Returns:
        Формат, который использовался реже всего
    """
    stats = get_stats(client_slug)
    formats = stats.get("formats", {})

    all_formats = ["lidgen", "expert", "meme", "case", "live", "circle"]

    # Находим наименее использованный
    min_count = float("inf")
    best_format = None

    for fmt in all_formats:
        count = formats.get(fmt, 0)
        if count < min_count:
            min_count = count
            best_format = fmt

    return best_format
