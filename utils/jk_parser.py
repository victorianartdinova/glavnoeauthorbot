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
    """Извлечь цены из текста.

    Более строгие критерии:
    - Явные указания на цены (ключевые слова)
    - Избегаем случайных чисел из контекста
    - Нормализуем форматы
    """
    prices = []

    # СТРОГИЕ паттерны (должны быть явно указаны как цены)
    patterns = [
        # Явные "цена", "стоимость", "от"
        (r'(?:цена|стоимость|от)\s*(?:квартир|помещ)?\s*[:\s]*(?:от\s+)?(\d+[\.,]?\d*)\s*млн', True),
        (r'от\s+(\d+[\.,]?\d*)\s+млн\s*(?:₽|руб)?', True),
        # Число с явным "млн" рядом
        (r'(\d+[\.,]?\d*)\s*млн\s*(?:₽|рублей|руб)\b', True),
        # Диапазон цен: "25-30 млн"
        (r'(\d+[\.,]?\d*)\s*-\s*(\d+[\.,]?\d*)\s*млн', True),
    ]

    for pattern, should_use in patterns:
        if not should_use:
            continue

        matches = re.finditer(pattern, text.lower())
        for match in matches:
            groups = match.groups()

            if len(groups) == 1:
                # Одно число
                price = groups[0].replace(' ', '').replace(',', '.')
                # Пропускаем очень маленькие или очень большие числа (шум)
                try:
                    price_float = float(price)
                    if 0.5 <= price_float <= 500:  # Разумные диапазоны цен
                        prices.append(f"{price} млн ₽")
                except ValueError:
                    pass
            elif len(groups) == 2:
                # Диапазон - берем оба края
                price1 = groups[0].replace(' ', '').replace(',', '.')
                price2 = groups[1].replace(' ', '').replace(',', '.')
                try:
                    p1 = float(price1)
                    p2 = float(price2)
                    if 0.5 <= p1 <= 500 and 0.5 <= p2 <= 500:
                        prices.append(f"{price1}-{price2} млн ₽")
                except ValueError:
                    pass

    # Убираем дубликаты и ограничиваем количество
    return list(dict.fromkeys(prices))[:3]


def extract_metro(text: str) -> List[Dict]:
    """Извлечь информацию о метро.

    Более строгие критерии:
    - Только четкие упоминания метро с расстоянием/временем
    - Избегаем дубликатов и неправильно распознанных данных
    """
    metro_info = []

    # СТРОГИЕ паттерны (требуют время или явное "метро")
    patterns = [
        # Наиболее надежные: "10 мин до метро Тульская", "м. Спортивная — 5 минут"
        (r'(\d+)\s*мин(?:ут[ыа]?)?\s*(?:до|от|пешком)?\s*(?:метро|м\.)\s*([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)?)', True),
        (r'(?:метро|м\.)\s*([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)?)\s*[—–-]\s*(\d+)\s*мин', True),
        # Только метро без времени (если явно упоминается)
        (r'м\.\s*([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)?)\b', False),
    ]

    for pattern, requires_time in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            groups = match.groups()

            if requires_time:
                if len(groups) == 2:
                    # Определяем что является временем
                    if groups[0].isdigit():
                        metro_info.append({
                            "station": groups[1].strip(),
                            "time": f"{groups[0]} мин"
                        })
                    else:
                        # groups[1] - время, groups[0] - станция
                        metro_info.append({
                            "station": groups[0].strip(),
                            "time": f"{groups[1]} мин"
                        })
            else:
                # Только станция без времени
                metro_info.append({
                    "station": groups[0].strip(),
                    "time": None
                })

    # Убираем дубли по станции (case-insensitive)
    seen = {}
    unique = []
    for m in metro_info:
        station_key = m["station"].lower()

        # Предпочитаем запись с временем если есть дублирование
        if station_key not in seen:
            seen[station_key] = m
            unique.append(m)
        elif m.get("time") and not seen[station_key].get("time"):
            # Заменяем на версию с временем
            idx = unique.index(seen[station_key])
            unique[idx] = m
            seen[station_key] = m

    return unique[:3]


def extract_features(text: str) -> List[str]:
    """Извлечь особенности/фишки ЖК.

    Более строгие критерии для избежания 'воды':
    - Нужны конкретные, проверяемые преимущества
    - Избегаем общих слов и предположений
    - Максимум 5-6 фичей (только самые важные)
    """
    features = []

    # ТОЛЬКО конкретные фишки (без воды)
    feature_keywords = [
        # Финансовые условия (только конкретные)
        (r'рассрочк[аеуи]\s*0\s*%', 'Рассрочка 0%'),
        (r'первый\s*взнос\s*от\s*(\d+[\.,]?\d*)\s*млн', 'ПВ от {0} млн'),
        (r'ипотек[аеуи]\s*от\s*(\d+[\.,]?\d*)\s*%', 'Ипотека от {0}%'),

        # Готовность (только факты)
        (r'ключи\s*(?:сразу|после\s*сделки)', 'Ключи сразу'),
        (r'сдан(?:ный|а|о)?\s*дом', 'Сданный дом'),

        # Особенности квартир (только проверяемые)
        (r'панорамн\w+\s*(?:вид|окн)', 'Панорамные окна'),
        (r'пентхаус', 'Пентхаус'),
        (r'террас[аеуы]', 'Терраса'),
        (r'подземн\w+\s*парк', 'Подземный паркинг'),

        # Сегмент (с осторожностью)
        (r'премиум[\s-]*класс', 'Премиум-класс'),
        (r'бизнес[\s-]*класс', 'Бизнес-класс'),
    ]

    text_lower = text.lower()

    for pattern, label in feature_keywords:
        # Проверяем что совпадение находится в контексте (не в случайном месте)
        match = re.search(pattern, text_lower)
        if match:
            # Проверяем что это не просто упоминание в сноске или комментарии
            match_start = match.start()
            # Ищем контекстные слова перед совпадением
            context_before = text_lower[max(0, match_start - 50):match_start]

            # Исключаем если это звучит как отрицание или сравнение
            if re.search(r'(без|не|но|только|если|как|например)', context_before):
                continue

            if '{0}' in label and match.groups():
                features.append(label.format(match.group(1)))
            else:
                features.append(label)

    # Возвращаем только самые релевантные (макс 6, не 10)
    return list(dict.fromkeys(features))[:6]


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

    Чистый и конкретный формат без 'воды'.

    Args:
        data: распаршенные данные
        include_name: включать ли название ЖК (по умолчанию НЕТ — для постов)

    Returns:
        Отформатированная строка с только релевантной информацией
    """
    if not data["parse_success"]:
        return f"Ошибка парсинга: {data['error']}"

    lines = []

    # Название ЖК — только если явно запрошено (например, для внутренних целей)
    if include_name and data["name"]:
        lines.append(f"НАЗВАНИЕ: {data['name']}")

    # Добавляем только НЕ пустые секции
    if data.get("prices"):
        lines.append(f"ЦЕНЫ: {', '.join(data['prices'])}")

    if data.get("metro"):
        metro_str = []
        for m in data["metro"]:
            if m.get("time"):
                metro_str.append(f"{m['station']} ({m['time']})")
            else:
                metro_str.append(m['station'])
        if metro_str:
            lines.append(f"МЕТРО: {', '.join(metro_str)}")

    if data.get("location", {}).get("district"):
        lines.append(f"РАЙОН: {data['location']['district']}")

    if data.get("deadline"):
        lines.append(f"СРОК СДАЧИ: {data['deadline']}")

    if data.get("features"):
        # Фильтруем пустые фичи
        features = [f for f in data["features"] if f and f.strip()]
        if features:
            lines.append(f"ОСОБЕННОСТИ: {', '.join(features)}")

    # НИКОГДА не добавляем raw_text — это 'вода'
    # Все полезные данные уже структурированы выше

    return "\n".join(lines) if lines else "Данные не найдены"


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
