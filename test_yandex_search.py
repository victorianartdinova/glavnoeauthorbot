#!/usr/bin/env python3
"""
Тестовый скрипт для проверки интеграции Yandex Search API
"""

import asyncio
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

async def test_search():
    """Тестирует функцию поиска через Yandex API"""

    print("=" * 70)
    print("TEST: Search Integration (SerpAPI + Web Scraping)")
    print("=" * 70)

    # Проверяем конфиг
    from config.settings import SERPAPI_KEY

    if SERPAPI_KEY:
        print("✅ SerpAPI credentials found:")
        print(f"   API Key: {SERPAPI_KEY[:20]}...\n")
    else:
        print("⚠️  SerpAPI credentials NOT configured")
        print("   Will use web scraping fallback (slower)\n")

    # Импортируем функцию поиска
    from utils.jk_parser import search_jk_info

    # Тестовые запросы
    test_queries = [
        "БЦ Белая площадь",
        "ЖК Садовые кварталы",
        "Офис на Маяковской",
    ]

    for query in test_queries:
        print(f"🔍 Searching for: '{query}'")
        print("-" * 70)

        result = await search_jk_info(query)

        if result:
            print(f"✅ Found information:\n")
            print(result[:500])  # Первые 500 символов
            if len(result) > 500:
                print(f"\n... (truncated, total {len(result)} chars)")
        else:
            print("❌ No information found")

        print("\n")

    print("=" * 70)
    print("TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_search())
