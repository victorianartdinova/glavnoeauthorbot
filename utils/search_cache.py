"""
Кеширование результатов поиска для сохранения лимита API Яндекса.
TTL: 24 часа.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

CACHE_FILE = Path("/root/glavnoe-bot/data/search_cache.json")
CACHE_TTL_HOURS = 24


async def get_cached_search(query: str) -> Optional[Dict]:
    """
    Проверить кеш для запроса.

    Args:
        query: поисковый запрос

    Returns:
        Закешированные результаты или None если кеш истёк/не найден
    """
    if not CACHE_FILE.exists():
        return None

    try:
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

        if query in cache:
            entry = cache[query]
            cached_time = datetime.fromisoformat(entry.get("timestamp", ""))
            age = datetime.now() - cached_time

            if age < timedelta(hours=CACHE_TTL_HOURS):
                logger.debug(f"Cache HIT for query: '{query[:50]}...' (age: {age.seconds}s)")
                return entry.get("results")
            else:
                logger.debug(f"Cache EXPIRED for query: '{query[:50]}...' (age: {age.seconds}s)")
                # Удаляем старую запись
                del cache[query]
                CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:
        logger.warning(f"Cache read error: {e}")

    return None


async def save_to_cache(query: str, results: Dict) -> bool:
    """
    Сохранить результаты поиска в кеш.

    Args:
        query: поисковый запрос
        results: результаты поиска

    Returns:
        True если успешно сохранено, False если ошибка
    """
    try:
        # Читаем существующий кеш
        cache = {}
        if CACHE_FILE.exists():
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

        # Добавляем новую запись
        cache[query] = {
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }

        # Ограничиваем размер кеша (макс 1000 запросов)
        if len(cache) > 1000:
            # Удаляем самую старую запись
            oldest_key = min(cache.keys(), key=lambda k: cache[k]["timestamp"])
            del cache[oldest_key]
            logger.debug(f"Cache size limit reached, removed oldest entry: {oldest_key[:50]}...")

        # Сохраняем
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug(f"Cache SAVE for query: '{query[:50]}...'")
        return True

    except Exception as e:
        logger.warning(f"Cache save error: {e}")
        return False


async def clear_cache():
    """Полностью очистить кеш."""
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        logger.info("Cache cleared")
        return True
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        return False


async def get_cache_stats() -> Dict:
    """
    Получить статистику кеша.

    Returns:
        {
            "total_entries": количество записей,
            "cache_file_size_kb": размер файла в KB,
            "oldest_entry_age_hours": возраст самой старой записи в часах,
        }
    """
    try:
        if not CACHE_FILE.exists():
            return {
                "total_entries": 0,
                "cache_file_size_kb": 0,
                "oldest_entry_age_hours": 0,
            }

        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

        if not cache:
            return {
                "total_entries": 0,
                "cache_file_size_kb": CACHE_FILE.stat().st_size / 1024,
                "oldest_entry_age_hours": 0,
            }

        timestamps = [
            datetime.fromisoformat(entry.get("timestamp", datetime.now().isoformat()))
            for entry in cache.values()
        ]
        oldest = min(timestamps)
        age_hours = (datetime.now() - oldest).total_seconds() / 3600

        return {
            "total_entries": len(cache),
            "cache_file_size_kb": CACHE_FILE.stat().st_size / 1024,
            "oldest_entry_age_hours": round(age_hours, 1),
        }

    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return {}
