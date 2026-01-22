"""
Интеграция Search API для поиска информации об объектах недвижимости.
Использует SerpAPI для надёжного парсинга результатов поиска.
Извлекает данные для УТП: обзоры, локацию, инфраструктуру, транспорт, особенности.
"""

import aiohttp
import logging
import re
import os
from typing import Optional, Dict, List
from urllib.parse import quote_plus
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Глобальный браузер (для переиспользования)
_browser = None
_playwright = None

# Конфиг SerpAPI
SERPAPI_URL = "https://serpapi.com/search"
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# Fallback на Яндекс web scraping если SerpAPI недоступен
YANDEX_SEARCH_URL = "https://yandex.ru/search/"

# Попытки переподключения к браузеру
MAX_BROWSER_RETRIES = 2


async def get_playwright_browser():
    """Получить или создать экземпляр браузера Playwright"""
    global _browser, _playwright

    if _browser is not None:
        try:
            # Проверяем что браузер живой
            if await _browser.is_connected():
                return _browser
        except Exception:
            _browser = None

    try:
        if _playwright is None:
            from playwright.async_api import async_playwright
            _playwright = await async_playwright().start()

        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        logger.info("Playwright browser started")
        return _browser

    except Exception as e:
        logger.error(f"Failed to start Playwright browser: {e}")
        return None


async def search_yandex_playwright(query: str, max_results: int = 5) -> List[Dict]:
    """
    Поиск через Яндекс используя Playwright (эмулирует реальный браузер).
    Обходит защиту от ботов.

    Args:
        query: поисковый запрос
        max_results: максимум результатов

    Returns:
        Список словарей с результатами
    """
    browser = await get_playwright_browser()
    if not browser:
        logger.warning("Playwright browser not available")
        return []

    context = None
    page = None

    try:
        # Создаём контекст с realistically поддельным браузером
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )

        page = await context.new_page()

        # URL поиска Яндекса
        search_url = f"{YANDEX_SEARCH_URL}?text={quote_plus(query)}&lr=213"
        logger.debug(f"Navigating to: {search_url}")

        # Загружаем страницу с ожиданием сети
        try:
            await page.goto(search_url, wait_until="networkidle", timeout=20000)
        except Exception as nav_error:
            logger.debug(f"Navigation error (continuing): {nav_error}")
            # Пробуем получить то что загрузилось
            await page.wait_for_load_state("domcontentloaded", timeout=10000)

        # Ждём загрузку элементов поиска
        try:
            await page.wait_for_selector("ol li, div[data-cid]", timeout=10000)
        except Exception:
            logger.debug("Search results selector not found, trying to extract from DOM")

        # Получаем HTML страницы
        html = await page.content()

        if not html or len(html) < 1000:
            logger.debug(f"Empty response for query: {query}")
            return []

        # Парсим результаты
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Ищем элементы результатов поиска
        search_items = soup.select("ol > li")

        if not search_items:
            search_items = soup.select("div[data-cid]")

        seen_urls = set()

        for item in search_items:
            if len(results) >= max_results:
                break

            try:
                # Ищем ссылку
                link_elem = item.select_one("a[href]")
                if not link_elem:
                    continue

                url = link_elem.get("href", "").strip()

                if not url or url.startswith("/") or url in seen_urls:
                    continue

                if not url.startswith("http"):
                    url = "https://" + url

                seen_urls.add(url)

                # Ищем заголовок
                title_elem = item.select_one("h2, h3, [class*='title']")
                title = title_elem.get_text(strip=True)[:200] if title_elem else ""

                # Ищем сниппет
                snippet = ""
                snippet_elem = item.select_one("[class*='snippet'], p, span")
                if snippet_elem:
                    snippet = snippet_elem.get_text(strip=True)[:300]

                if title and url:
                    results.append({
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                    })
                    logger.debug(f"Found result: {title[:60]}...")

            except Exception as item_error:
                logger.debug(f"Error parsing item: {item_error}")
                continue

        logger.info(f"Playwright search: '{query[:50]}' found {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Playwright search error: {e}")
        return []

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ============================================================================
# REGEX ПАТТЕРНЫ ДЛЯ ИЗВЛЕЧЕНИЯ ДАННЫХ ДЛЯ УТП
# ============================================================================

REVIEW_KEYWORDS = [
    r'(один из (?:лучших|крупнейших|известных|популярных)[^\.]{10,150})',
    r'(премия|награда|номинация[^\.]{5,100})',
    r'(рейтинг|топ-\d+[^\.]{5,100})',
    r'(признан[^\.]{5,100})',
]

LOCATION_PATTERNS = [
    r'(\d+\s*(?:мин|км)\s*(?:до|от)\s+(?:Кремл|парк|центр|площадь|набережн|реки?)[^,\.\n]+)',
    r'(рядом\s+с\s+[А-Я][а-яё\s\-]{5,50})',
    r'(в\s+сердце\s+[А-Я][^,\.\n]+)',
    r'(на\s+берегу\s+[^,\.\n]+)',
    r'(в\s+историческом\s+центре)',
]

INFRASTRUCTURE_KEYWORDS = [
    r'(кафе|рестора[нм]|бар|фуд-корт|столовая)[^,\.\n]{0,50}',
    r'(детский сад|школа|садик)[^,\.\n]{0,50}',
    r'(фитнес|спортзал|бассейн|gym|spa)[^,\.\n]{0,50}',
    r'(паркинг|парковк[аеи])[^,\.\n]{0,50}',
    r'(торговый центр|ТЦ|МЦ)[^,\.\n]{0,50}',
    r'(конференц-зал|переговорн|совещание)',
    r'(кинотеатр|кино)',
]

TRANSPORT_PATTERNS = [
    r'((?:метро|м\.)\s+[А-Я][а-яё\s]*\s+\d+\s*(?:мин|м))',
    r'(МЦК|МЦД)[^,\.\n]{0,50}',
    r'(станция|остановка)[^,\.\n]{0,50}',
    r'(из метро[^,\.\n]{0,50})',
]

UNIQUE_FEATURES = [
    r'(архитектор\s+[А-Я][^,\.\n]{5,80})',
    r'(дизайн\s+(?:от|студии|бюро)\s+[А-Я][^,\.\n]{5,80})',
    r'(панорамн\w+\s+(?:вид|окн|остеклен)[^,\.\n]{0,50})',
    r'(терраса|балкон|лоджия)[^,\.\n]{0,50}',
    r'(класс\s+[ABC]|бизнес-класс|премиум-класс|элит)',
    r'(двухуровнев|многоуровнев)',
    r'(историческое\s+здание)',
    r'(отреставрирован|реновирован)',
]


# ============================================================================
# ОСНОВНЫЕ ФУНКЦИИ
# ============================================================================

async def search_serpapi(query: str, max_results: int = 5) -> List[Dict]:
    """
    Поиск через SerpAPI (парсит Яндекс и Google через облако).

    Docs: https://serpapi.com/docs/search-api/overview

    Args:
        query: поисковый запрос
        max_results: максимум результатов вернуть

    Returns:
        Список словарей с результатами:
        [
            {
                "url": "https://example.ru/...",
                "title": "Название объекта",
                "snippet": "Фрагмент текста ...",
            },
            ...
        ]
    """
    if not SERPAPI_KEY:
        logger.debug("SerpAPI key not configured. Set SERPAPI_KEY environment variable")
        return []

    try:
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "engine": "yandex",  # Используем Яндекс
            "hl": "ru",
            "tbm": "lcl",  # Local search (может быть полезно для объектов)
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                SERPAPI_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False,
            ) as response:
                if response.status != 200:
                    logger.warning(f"SerpAPI returned status {response.status}")
                    return []

                data = await response.json()

        results = []

        # Парсим органические результаты
        organic_results = data.get("organic_results", [])
        for result in organic_results[:max_results]:
            results.append({
                "url": result.get("link", ""),
                "title": result.get("title", ""),
                "snippet": result.get("snippet", ""),
            })

        logger.info(f"SerpAPI: query='{query[:50]}...' found {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"SerpAPI error: {e}")
        return []


async def search_yandex_web_scraping(query: str, max_results: int = 5) -> List[Dict]:
    """
    Парсит Яндекс через web scraping с правильным эмулированием браузера.
    Использует реалистичные User-Agent и headers.

    Args:
        query: поисковый запрос
        max_results: максимум результатов вернуть

    Returns:
        Список словарей с результатами
    """
    from bs4 import BeautifulSoup
    import asyncio

    try:
        # Формируем URL поиска (добавляем Москву для недвижимости)
        search_url = f"{YANDEX_SEARCH_URL}?text={quote_plus(query)}&lr=213"

        # Реалистичные headers как у обычного браузера
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        # Задержка перед запросом
        await asyncio.sleep(0.3)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
                ssl=False,
            ) as response:
                if response.status != 200:
                    logger.debug(f"Yandex returned {response.status} for query: {query[:50]}")
                    return []

                html = await response.text()

        if not html or len(html) < 1000:
            logger.debug(f"Yandex response too short for query: {query[:50]}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Попытка 1: поиск через основной селектор Яндекса (ol > li)
        search_items = soup.select("ol > li")

        if not search_items:
            # Попытка 2: через div с атрибутом data
            search_items = soup.select("div[data-cid]")

        if not search_items:
            # Попытка 3: через article элементы
            search_items = soup.select("article")

        seen_urls = set()

        for item in search_items:
            if len(results) >= max_results:
                break

            try:
                # Ищем ссылку
                link_elem = item.select_one("a[href]")
                if not link_elem:
                    continue

                url = link_elem.get("href", "").strip()

                # Пропускаем редиректы и невалидные URL
                if not url or url.startswith("/") or url in seen_urls:
                    continue

                if not url.startswith("http"):
                    url = "https://" + url

                seen_urls.add(url)

                # Ищем заголовок
                title_elem = item.select_one("h2, h3, span, a")
                title = ""
                if title_elem:
                    title = title_elem.get_text(strip=True)[:200]

                # Ищем сниппет (описание)
                # Ищем сниппет в разных местах
                snippet = ""
                for selector in ["span", "p", "div"]:
                    snippet_elem = item.select_one(selector)
                    if snippet_elem:
                        text = snippet_elem.get_text(strip=True)
                        if len(text) > 30 and len(text) < 500:
                            snippet = text[:300]
                            break

                if title and url:
                    results.append({
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                    })
                    logger.debug(f"Found: {title[:50]}...")

            except Exception as item_error:
                logger.debug(f"Error parsing search item: {item_error}")
                continue

        logger.info(f"Yandex search: query='{query[:50]}' found {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Yandex web scraping error: {e}")
        return []


async def extract_info_for_utp(results: List[Dict]) -> Dict:
    """
    Извлекает структурированную информацию для УТП из результатов поиска.

    Args:
        results: список результатов от search_yandex_api()

    Returns:
        {
            "reviews": ["...", "..."],
            "location_features": ["...", "..."],
            "infrastructure": ["...", "..."],
            "transport": ["...", "..."],
            "unique_features": ["...", "..."],
            "raw_snippets": ["...", "..."]
        }
    """
    combined_text = " ".join([
        r.get("title", "") + " " + r.get("snippet", "")
        for r in results
    ]).lower()

    extracted = {
        "reviews": [],
        "location_features": [],
        "infrastructure": [],
        "transport": [],
        "unique_features": [],
        "raw_snippets": [r.get("snippet", "")[:200] for r in results if r.get("snippet", "")],
    }

    # Извлекаем обзоры/отзывы
    for pattern in REVIEW_KEYWORDS:
        matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            text = match.strip().capitalize()
            if len(text) > 15 and text not in extracted["reviews"]:
                extracted["reviews"].append(text[:150])

    # Извлекаем локацию до ключевых точек
    for pattern in LOCATION_PATTERNS:
        matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            text = match.strip().capitalize()
            if len(text) > 10 and text not in extracted["location_features"]:
                extracted["location_features"].append(text[:150])

    # Извлекаем инфраструктуру
    for pattern in INFRASTRUCTURE_KEYWORDS:
        matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            text = match.strip().capitalize()
            if len(text) > 5 and text not in extracted["infrastructure"]:
                extracted["infrastructure"].append(text[:150])

    # Извлекаем транспорт
    for pattern in TRANSPORT_PATTERNS:
        matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            text = match.strip().capitalize()
            if len(text) > 8 and text not in extracted["transport"]:
                extracted["transport"].append(text[:150])

    # Извлекаем уникальные фишки
    for pattern in UNIQUE_FEATURES:
        matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            text = match.strip().capitalize()
            if len(text) > 8 and text not in extracted["unique_features"]:
                extracted["unique_features"].append(text[:150])

    # Ограничиваем количество элементов
    for key in extracted:
        if key != "raw_snippets":
            extracted[key] = extracted[key][:5]  # Макс 5 элементов на категорию

    return extracted


def format_utp_results(utp_data: Dict) -> str:
    """
    Форматирует извлечённые данные для УТП в текст для Claude.

    Args:
        utp_data: результат extract_info_for_utp()

    Returns:
        Отформатированный текст для промпта Claude
    """
    lines = []

    if utp_data.get("reviews"):
        lines.append("ОБЗОРЫ И РЕПУТАЦИЯ:")
        for review in utp_data["reviews"]:
            lines.append(f"• {review}")

    if utp_data.get("location_features"):
        lines.append("\nЛОКАЦИЯ И КЛЮЧЕВЫЕ ТОЧКИ:")
        for feature in utp_data["location_features"]:
            lines.append(f"• {feature}")

    if utp_data.get("infrastructure"):
        lines.append("\nИНФРАСТРУКТУРА РЯДОМ:")
        for item in utp_data["infrastructure"]:
            lines.append(f"• {item}")

    if utp_data.get("transport"):
        lines.append("\nТРАНСПОРТНАЯ ДОСТУПНОСТЬ:")
        for transport in utp_data["transport"]:
            lines.append(f"• {transport}")

    if utp_data.get("unique_features"):
        lines.append("\nУНИКАЛЬНЫЕ ОСОБЕННОСТИ:")
        for feature in utp_data["unique_features"]:
            lines.append(f"• {feature}")

    # Если ничего не нашлось, добавляем сырые сниппеты
    if not any([
        utp_data.get("reviews"),
        utp_data.get("location_features"),
        utp_data.get("infrastructure"),
        utp_data.get("transport"),
        utp_data.get("unique_features"),
    ]):
        if utp_data.get("raw_snippets"):
            lines.append("ИНФОРМАЦИЯ ИЗ ПОИСКА:")
            for snippet in utp_data["raw_snippets"][:3]:
                if snippet:
                    lines.append(f"• {snippet}")

    return "\n".join(lines) if lines else None


async def search_object_with_utp(object_name: str, max_queries: int = 4) -> Optional[str]:
    """
    Полный поиск информации об объекте для УТП.
    Делает несколько запросов для максимума информации.

    Приоритет: SerpAPI → Playwright → web scraping

    Args:
        object_name: название объекта (БЦ, ЖК, офис и т.д.)
        max_queries: количество разных запросов

    Returns:
        Отформатированная информация для УТП или None
    """
    if not object_name or len(object_name.strip()) < 3:
        return None

    # Стратегия множественных запросов
    queries = [
        f"{object_name}",
        f"{object_name} офис недвижимость",
        f"{object_name} Москва",
        f"{object_name} информация особенности",
    ][:max_queries]

    all_results = []
    logger.info(f"Starting search for: {object_name}")

    for q in queries:
        logger.debug(f"Searching: {q}")
        results = []

        # Приоритет 1: SerpAPI (если доступен)
        if SERPAPI_KEY:
            results = await search_serpapi(q, max_results=5)

        # Приоритет 2: Playwright (эмулирует реальный браузер)
        if not results:
            logger.debug(f"  Trying Playwright...")
            results = await search_yandex_playwright(q, max_results=5)

        # Приоритет 3: web scraping fallback (базовый парсинг)
        if not results:
            logger.debug(f"  Trying web scraping fallback...")
            results = await search_yandex_web_scraping(q, max_results=5)

        if results:
            all_results.extend(results)
            logger.debug(f"  Found {len(results)} results")

    if not all_results:
        logger.warning(f"No search results for: {object_name}")
        return None

    # Извлекаем и форматируем данные для УТП
    utp_data = await extract_info_for_utp(all_results)
    formatted = format_utp_results(utp_data)

    if formatted:
        logger.info(f"Successfully extracted UTP data for: {object_name}")
        return formatted

    return None
