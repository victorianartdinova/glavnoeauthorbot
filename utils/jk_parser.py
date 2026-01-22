"""
Парсер сайтов ЖК для извлечения данных
"""
import aiohttp
from bs4 import BeautifulSoup
import re
import json
from typing import Optional, Dict, List
from urllib.parse import quote_plus


async def fetch_page(url: str, timeout: int = 10) -> Optional[str]:
    """Загрузить HTML страницы"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 200:
                    return await response.text()
                return None
    except Exception:
        return None


def find_url_in_text(text: str) -> Optional[str]:
    """Найти URL в тексте сообщения"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    match = re.search(url_pattern, text)
    return match.group(0) if match else None


def extract_prices(text: str) -> List[str]:
    """Извлечь цены из текста"""
    prices = []

    # Паттерны цен: "от 25 млн", "от 25 000 000", "25.5 млн ₽"
    patterns = [
        r'от\s*(\d+[\.,]?\d*)\s*млн',
        r'(\d+[\.,]?\d*)\s*млн\s*(?:₽|руб|рублей)',
        r'от\s*(\d{1,3}(?:\s?\d{3})+)\s*(?:₽|руб)',
        r'цена[:\s]+(\d+[\.,]?\d*)\s*млн',
        r'стоимость[:\s]+от?\s*(\d+[\.,]?\d*)\s*млн',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        for match in matches:
            clean = match.replace(' ', '').replace(',', '.')
            prices.append(f"{clean} млн ₽")

    return list(set(prices))[:3]  # Уникальные, макс 3


def extract_metro(text: str) -> List[Dict]:
    """Извлечь информацию о метро"""
    metro_info = []

    # Паттерны: "10 мин до метро Тульская", "м. Спортивная — 5 минут"
    patterns = [
        r'(\d+)\s*мин(?:ут[ыа]?)?\s*(?:до|от)?\s*(?:метро|м\.)\s*[«"]?(\w+)[»"]?',
        r'(?:метро|м\.)\s*[«"]?(\w+)[»"]?\s*[—–-]\s*(\d+)\s*мин',
        r'(?:метро|м\.)\s*[«"]?(\w+)[»"]?',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match) == 2:
                if match[0].isdigit():
                    metro_info.append({"station": match[1], "time": f"{match[0]} мин"})
                else:
                    metro_info.append({"station": match[0], "time": f"{match[1]} мин"})
            elif len(match) == 1:
                metro_info.append({"station": match[0], "time": None})

    # Убираем дубли по станции
    seen = set()
    unique = []
    for m in metro_info:
        if m["station"].lower() not in seen:
            seen.add(m["station"].lower())
            unique.append(m)

    return unique[:3]


def extract_features(text: str) -> List[str]:
    """Извлечь особенности/фишки ЖК"""
    features = []

    # Ключевые слова фишек
    feature_keywords = [
        # Финансы
        (r'рассрочк[аеуи]\s*0\s*%', 'Рассрочка 0%'),
        (r'рассрочк[аеуи]\s*без\s*%', 'Рассрочка без %'),
        (r'первый\s*взнос\s*от\s*(\d+[\.,]?\d*)\s*млн', 'ПВ от {0} млн'),
        (r'первоначальный\s*взнос\s*от\s*(\d+[\.,]?\d*)', 'ПВ от {0} млн'),
        (r'ипотек[аеуи]\s*от\s*(\d+[\.,]?\d*)\s*%', 'Ипотека от {0}%'),
        (r'траншев[аяой]+\s*ипотек', 'Траншевая ипотека'),
        (r'субсидирован\w+\s*ипотек', 'Субсидированная ипотека'),

        # Готовность
        (r'ключи\s*(?:сразу|после\s*сделки)', 'Ключи сразу'),
        (r'сдан(?:ный|а|о)?\s*дом', 'Сданный дом'),
        (r'готов[аоы]+\s*(?:к\s*)?(?:заселению|проживанию)', 'Готов к заселению'),
        (r'с\s*(?:готовой\s*)?отделк', 'С отделкой'),
        (r'с\s*ремонт', 'С ремонтом'),
        (r'без\s*отделк', 'Без отделки'),
        (r'white\s*box', 'White box'),

        # Особенности
        (r'терраc[аеуы]', 'Терраса'),
        (r'панорамн\w+\s*(?:вид|остеклен|окн)', 'Панорамные окна'),
        (r'вид\s*на\s*(?:парк|воду|реку|город|москву)', 'Видовая квартира'),
        (r'двухуровнев', 'Двухуровневая'),
        (r'пентхаус', 'Пентхаус'),
        (r'высок\w+\s*потолк', 'Высокие потолки'),
        (r'собствен\w+\s*(?:парк|двор|территор)', 'Своя территория'),
        (r'закрыт\w+\s*(?:двор|территор)', 'Закрытая территория'),
        (r'подземн\w+\s*парк', 'Подземный паркинг'),
        (r'консьерж', 'Консьерж-сервис'),

        # Класс
        (r'бизнес[\s-]*класс', 'Бизнес-класс'),
        (r'премиум[\s-]*класс', 'Премиум-класс'),
        (r'элит[\s-]*класс', 'Элит-класс'),
        (r'комфорт[\s-]*класс', 'Комфорт-класс'),

        # Инфраструктура
        (r'детск\w+\s*сад', 'Детский сад'),
        (r'школ[аеуы]', 'Школа рядом'),
        (r'фитнес', 'Фитнес'),
        (r'spa|спа', 'SPA'),
    ]

    text_lower = text.lower()

    for pattern, label in feature_keywords:
        match = re.search(pattern, text_lower)
        if match:
            if '{0}' in label and match.groups():
                features.append(label.format(match.group(1)))
            else:
                features.append(label)

    return list(dict.fromkeys(features))[:10]  # Уникальные, макс 10


def extract_location(text: str) -> Dict:
    """Извлечь информацию о локации"""
    location = {
        "district": None,
        "address": None,
        "landmarks": []
    }

    # Районы Москвы
    districts = [
        'хамовники', 'арбат', 'пресня', 'тверской', 'замоскворечье',
        'якиманка', 'басманный', 'красносельский', 'мещанский', 'таганский',
        'даниловский', 'донской', 'нагатинский', 'чертаново', 'бутово',
        'раменки', 'очаково', 'тропарёво', 'солнцево', 'ново-переделкино',
        'фили', 'кунцево', 'крылатское', 'строгино', 'хорошёво',
        'сокол', 'аэропорт', 'войковский', 'коптево', 'тимирязевский',
        'алексеевский', 'бутырский', 'марьина роща', 'останкино', 'ростокино',
        'измайлово', 'соколиная гора', 'перово', 'новогиреево',
        'кузьминки', 'люблино', 'марьино', 'печатники', 'текстильщики',
        'царицыно', 'орехово', 'братеево', 'зябликово', 'бирюлёво',
        'нагатино', 'москворечье', 'сити', 'москва-сити'
    ]

    text_lower = text.lower()

    for district in districts:
        if district in text_lower:
            location["district"] = district.title()
            break

    # Ориентиры
    landmarks_patterns = [
        (r'рядом\s+с\s+([^,\.\n]+)', 'landmarks'),
        (r'в\s+(\d+)\s*мин(?:утах?)?\s+от\s+([^,\.\n]+)', 'time_to'),
    ]

    return location


def extract_deadline(text: str) -> Optional[str]:
    """Извлечь срок сдачи"""
    patterns = [
        r'сдача[:\s]+(\d{1,2}[QК]?\s*\d{4})',
        r'срок\s*сдачи[:\s]+(\d{1,2}[QК]?\s*\d{4})',
        r'ввод[:\s]+(\d{1,2}[QК]?\s*\d{4})',
        r'([IVX1234]+\s*кварт\w*\s*\d{4})',
        r'(\d{4})\s*год',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_jk_name(text: str, url: str) -> Optional[str]:
    """Извлечь название ЖК"""
    patterns = [
        r'жк\s*[«"]([^»"]+)[»"]',
        r'жк\s+([А-Яа-яЁё\w\s-]+?)(?:\s*[-–—]|\s*$|\s*\n)',
        r'[«"]([^»"]+)[»"]\s*[-–—]\s*(?:жилой|квартир)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 50:
                return name

    # Попробуем извлечь из URL
    url_match = re.search(r'//(?:www\.)?([^/]+)', url)
    if url_match:
        domain = url_match.group(1)
        # Убираем .ru, .com и т.д.
        name = re.sub(r'\.(ru|com|moscow|msk)$', '', domain)
        name = name.replace('-', ' ').replace('_', ' ').title()
        return f"ЖК {name}"

    return None


async def parse_jk_website(url: str) -> dict:
    """
    Парсит сайт ЖК и извлекает структурированные данные.

    Returns:
        dict с ключами:
            - url: исходный URL
            - name: название ЖК
            - prices: список цен
            - metro: список станций метро с временем
            - features: список особенностей
            - location: информация о локации
            - deadline: срок сдачи
            - raw_text: сырой текст (сокращённый)
            - parse_success: успешность парсинга
            - error: сообщение об ошибке
    """
    result = {
        "url": url,
        "name": None,
        "prices": [],
        "metro": [],
        "features": [],
        "location": {},
        "deadline": None,
        "raw_text": "",
        "parse_success": False,
        "error": None
    }

    html = await fetch_page(url)

    if not html:
        result["error"] = "Не удалось загрузить страницу"
        return result

    soup = BeautifulSoup(html, "lxml")

    # Удаляем мусор
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
        tag.decompose()

    # Получаем текст
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)

    if not text or len(text) < 100:
        result["error"] = "Страница пустая или слишком короткая"
        return result

    # Извлекаем структурированные данные
    result["name"] = extract_jk_name(text, url)
    result["prices"] = extract_prices(text)
    result["metro"] = extract_metro(text)
    result["features"] = extract_features(text)
    result["location"] = extract_location(text)
    result["deadline"] = extract_deadline(text)

    # Сохраняем сокращённый текст для Claude (на случай если паттерны не нашли всё)
    result["raw_text"] = text[:5000] if len(text) > 5000 else text
    result["parse_success"] = True

    return result


def format_parsed_data(data: dict, include_name: bool = False) -> str:
    """
    Форматировать распаршенные данные для промпта Claude.

    Args:
        data: распаршенные данные
        include_name: включать ли название ЖК (по умолчанию НЕТ — для постов)
    """
    if not data["parse_success"]:
        return f"Ошибка парсинга: {data['error']}"

    lines = []

    # Название ЖК — только если явно запрошено (например, для внутренних целей)
    if include_name and data["name"]:
        lines.append(f"НАЗВАНИЕ: {data['name']}")

    if data["prices"]:
        lines.append(f"ЦЕНЫ: {', '.join(data['prices'])}")

    if data["metro"]:
        metro_str = []
        for m in data["metro"]:
            if m["time"]:
                metro_str.append(f"{m['station']} ({m['time']})")
            else:
                metro_str.append(m['station'])
        lines.append(f"МЕТРО: {', '.join(metro_str)}")

    if data["location"].get("district"):
        lines.append(f"РАЙОН: {data['location']['district']}")

    if data["deadline"]:
        lines.append(f"СРОК СДАЧИ: {data['deadline']}")

    if data["features"]:
        lines.append(f"ОСОБЕННОСТИ: {', '.join(data['features'])}")

    # Сырой текст НЕ добавляем — там может быть название ЖК
    # Все полезные данные уже извлечены парсером выше

    return "\n".join(lines)


async def search_jk_info(query: str) -> Optional[str]:
    """
    Поиск информации об объекте через Яндекс с приоритетом на Yandex XML API.
    Делает несколько запросов для максимума информации (для УТП).
    С fallback на web scraping если API недоступен.

    Returns:
        Отформатированная информация для УТП или None
    """
    if not query or len(query.strip()) < 3:
        return None

    import logging
    logger = logging.getLogger(__name__)

    # Первый приоритет: Yandex XML API через search_object_with_utp
    try:
        from utils.yandex_search import search_object_with_utp
        from utils.search_cache import get_cached_search, save_to_cache

        # Проверяем кеш
        cache_key = f"search_utp:{query.lower()}"
        cached_result = await get_cached_search(cache_key)
        if cached_result:
            logger.debug(f"Using cached search result for: {query}")
            return cached_result

        # Делаем поиск с расширенной стратегией (6 запросов)
        result = await search_object_with_utp(query, max_queries=6)
        if result:
            # Сохраняем в кеш
            await save_to_cache(cache_key, result)
            logger.info(f"Found data via search_object_with_utp for: {query}")
            return result

    except Exception as e:
        logger.debug(f"Yandex API search failed: {e}, falling back to web scraping")

    # Fallback: улучшенный web scraping с несколькими вариантами поиска
    search_variants = [
        f"{query} ЖК Москва цена метро",
        f"{query} жилой комплекс параметры",
        f"{query} Москва расположение район",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }

    all_snippets = []

    for search_query in search_variants:
        try:
            search_url = f"https://yandex.ru/search/?text={quote_plus(search_query)}"
            logger.debug(f"Trying fallback web scraping: {search_query}")

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        continue
                    html = await response.text()

            soup = BeautifulSoup(html, "lxml")

            # Парсим сниппеты Яндекса (пробуем разные селекторы)
            for snippet_elem in soup.select(".OrganicTextContentSpan, .ExtendedText-Content, .Organic-ContentWrapper, div[class*='Snippet'], div[class*='snippet']"):
                text = snippet_elem.get_text(strip=True)
                if text and len(text) > 30:
                    all_snippets.append(text[:400])
                    if len(all_snippets) >= 3:
                        break

            if len(all_snippets) >= 3:
                break

        except Exception as e:
            logger.debug(f"Fallback scraping for '{search_query}' failed: {e}")
            continue

    if all_snippets:
        result = "ИНФОРМАЦИЯ ИЗ ПОИСКА ЯНДЕКС:\n" + "\n".join(all_snippets)
        logger.info(f"Found data via fallback web scraping for: {query}")
        return result

    logger.warning(f"No search results found for: {query}")
    return None
