"""
Логика определения "подходит для рекламы" (Telegram Ads)
"""
import re
import config


def check_ad_eligibility(lot_data: dict) -> tuple[bool, list[str]]:
    """
    Проверяет, подходит ли лот для рекламы по автоматическим условиям.

    Условия (любое из):
    - ПВ ≤ 10 млн
    - Платёж ≤ 200к/мес
    - Скидка ≥ 5 млн
    - Старт продаж

    Returns:
        (is_eligible, reasons) - подходит ли и почему
    """
    rules = config.AD_ELIGIBILITY_RULES
    reasons = []

    # Проверка первого взноса
    downpayment = lot_data.get("downpayment", 0)
    if downpayment and downpayment <= rules["downpayment_max"]:
        reasons.append(f"ПВ {downpayment/1_000_000:.1f} млн")

    # Проверка платежа
    monthly = lot_data.get("monthly_payment", 0)
    if monthly and monthly <= rules["monthly_payment_max"]:
        reasons.append(f"платёж {monthly/1000:.0f}к/мес")

    # Проверка скидки
    discount = lot_data.get("discount", 0)
    if discount and discount >= rules["discount_min"]:
        reasons.append(f"скидка {discount/1_000_000:.1f} млн")

    # Проверка старта продаж
    if lot_data.get("sales_start"):
        reasons.append("старт продаж")

    return len(reasons) > 0, reasons


def parse_lot_for_ads(lot_text: str) -> tuple[bool, str, dict]:
    """
    Парсит текст лота и определяет, подходит ли для рекламы.

    Распознаёт:
    - Ручные пометки: [подходит для рекламы], [реклама], [ads], [ad], +
    - Автоматически по условиям из текста

    Returns:
        (is_for_ads, clean_text, parsed_data)
    """
    text_lower = lot_text.lower()

    # === 1. Ручные пометки ===
    manual_markers = [
        r'\[подходит для рекламы\]',
        r'\[подходит под рекламу\]',
        r'\[для рекламы\]',
        r'\[под рекламу\]',
        r'\[реклама\]',
        r'\[ads\]',
        r'\[ad\]',
        r'\breклама\b',
        r'^[\+\*]\s',  # + или * в начале строки
    ]

    manual_ad = False
    clean_text = lot_text

    for marker in manual_markers:
        if re.search(marker, text_lower):
            manual_ad = True
            # Удаляем маркер из текста
            clean_text = re.sub(marker, '', clean_text, flags=re.IGNORECASE).strip()
            break

    # === 2. Парсинг данных из текста ===
    parsed_data = {}

    # Первый взнос: "ПВ 2.5 млн", "от 2,5 млн", "взнос 3 млн"
    pv_patterns = [
        r'пв\s*[:\-]?\s*(?:от\s*)?(\d+[.,]?\d*)\s*(?:млн|м)',
        r'взнос\s*[:\-]?\s*(?:от\s*)?(\d+[.,]?\d*)\s*(?:млн|м)',
        r'первый взнос\s*[:\-]?\s*(?:от\s*)?(\d+[.,]?\d*)\s*(?:млн|м)',
        r'первоначальный\s*[:\-]?\s*(?:от\s*)?(\d+[.,]?\d*)\s*(?:млн|м)',
    ]
    for pattern in pv_patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1).replace(',', '.'))
            parsed_data["downpayment"] = int(value * 1_000_000)
            break

    # Платёж: "89к/мес", "платёж 150 тыс", "от 120 000/мес"
    payment_patterns = [
        r'платёж\s*[:\-]?\s*(?:от\s*)?(\d+)\s*(?:к|тыс)',
        r'платеж\s*[:\-]?\s*(?:от\s*)?(\d+)\s*(?:к|тыс)',
        r'(\d+)\s*(?:к|тыс)[/\\]мес',
        r'(\d+)\s*000\s*[/\\рр]?\s*мес',
        r'(\d+)\s*тыс(?:яч)?\s*[/\\в]\s*мес',
    ]
    for pattern in payment_patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = int(match.group(1))
            # Если значение < 1000, это тысячи
            if value < 1000:
                value = value * 1000
            parsed_data["monthly_payment"] = value
            break

    # Скидка: "скидка 5 млн", "-10 млн", "дисконт 7м"
    discount_patterns = [
        r'скидк[аи]\s*[:\-]?\s*(\d+[.,]?\d*)\s*(?:млн|м)',
        r'дисконт\s*[:\-]?\s*(\d+[.,]?\d*)\s*(?:млн|м)',
        r'[\-−]\s*(\d+[.,]?\d*)\s*(?:млн|м)',
    ]
    for pattern in discount_patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1).replace(',', '.'))
            parsed_data["discount"] = int(value * 1_000_000)
            break

    # Старт продаж
    start_patterns = [
        r'старт\s*продаж',
        r'начало\s*продаж',
        r'только\s*открыл',
        r'новый\s*проект',
        r'только\s*вышел',
    ]
    for pattern in start_patterns:
        if re.search(pattern, text_lower):
            parsed_data["sales_start"] = True
            break

    # === 3. Определяем итоговый статус ===
    if manual_ad:
        return True, clean_text, parsed_data

    auto_eligible, reasons = check_ad_eligibility(parsed_data)
    return auto_eligible, clean_text, parsed_data


def format_lot_with_ad_status(lot_text: str, is_for_ads: bool, reasons: list = None) -> str:
    """
    Форматирует лот с пометкой статуса рекламы.
    """
    if is_for_ads:
        reason_str = f" ({', '.join(reasons)})" if reasons else ""
        return f"📢 {lot_text} [ДЛЯ ADS]{reason_str}"
    else:
        return f"📱 {lot_text} [ТОЛЬКО КАНАЛ]"
