"""
Anti-spam throttle — предотвращает спам одинаковых предупреждений
"""
import time
from typing import Dict, Tuple


# Хранилище: (user_id, action) -> timestamp
_throttle_store: Dict[Tuple[int, str], float] = {}


def should_show_warning(user_id: int, action: str, cooldown_seconds: int = 60) -> bool:
    """
    Проверяет, нужно ли показывать предупреждение пользователю.

    Args:
        user_id: ID пользователя
        action: тип действия (например, "select_client")
        cooldown_seconds: время cooldown в секундах (по умолчанию 60)

    Returns:
        True если показать, False если пропустить (throttled)
    """
    key = (user_id, action)
    now = time.time()

    # Проверяем, было ли предупреждение недавно
    if key in _throttle_store:
        last_time = _throttle_store[key]
        if now - last_time < cooldown_seconds:
            # Ещё не прошло cooldown
            return False

    # Обновляем timestamp
    _throttle_store[key] = now
    return True


def clear_throttle(user_id: int, action: str = None):
    """
    Очищает throttle для пользователя.

    Args:
        user_id: ID пользователя
        action: тип действия (если None — очистить все для пользователя)
    """
    if action:
        key = (user_id, action)
        if key in _throttle_store:
            del _throttle_store[key]
    else:
        # Очистить все для пользователя
        keys_to_delete = [k for k in _throttle_store.keys() if k[0] == user_id]
        for k in keys_to_delete:
            del _throttle_store[k]


def cleanup_old_entries(max_age_seconds: int = 3600):
    """
    Очищает старые записи (старше max_age_seconds).

    Вызывать периодически для экономии памяти.
    """
    now = time.time()
    keys_to_delete = [
        k for k, timestamp in _throttle_store.items()
        if now - timestamp > max_age_seconds
    ]
    for k in keys_to_delete:
        del _throttle_store[k]
