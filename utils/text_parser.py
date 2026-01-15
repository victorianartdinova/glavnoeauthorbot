"""
Text Parser — парсинг свободного текста в структурированные данные для лидген-карусели
"""
import re
from typing import Dict, List, Optional, Any


def parse_leadgen_text(text: str) -> Dict[str, Any]:
    """
    Парсинг свободного текста в структуру для лидген-карусели.

    Поддерживаемые форматы:
    - Список проектов (буллеты, нумерация)
    - Название ЖК
    - Локация (м. Спартак, 5 мин)
    - Первый взнос (8 млн, 40%)
    - УТП (список)
    - Ссылки (URL)

    Returns:
        {
            "projects": [...],
            "city": "Москва",
            "audience": "инвестор",
            "cta": "Написать ПЛАНИРОВКА"
        }
    """

    result = {
        "projects": [],
        "city": "Москва",
        "audience": "инвестор",
        "cta": "Написать 'ПЛАНИРОВКА' в личку"
    }

    lines = text.strip().split("\n")
    current_project = None

    # Эвристики для определения контекста
    city_keywords = ["москва", "спб", "санкт-петербург", "казань", "сочи"]
    audience_keywords = {
        "инвестор": ["инвестиц", "доход", "аренд", "капитал"],
        "для жизни": ["жить", "семья", "дети", "комфорт"],
        "семья": ["семья", "дети", "школ", "детск"]
    }

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # === ГОРОД ===
        for city in city_keywords:
            if city.lower() in line_clean.lower():
                result["city"] = city.capitalize()
                break

        # === АУДИТОРИЯ ===
        for aud, keywords in audience_keywords.items():
            if any(kw in line_clean.lower() for kw in keywords):
                result["audience"] = aud
                break

        # === CTA ===
        if "написать" in line_clean.lower() or "планировка" in line_clean.lower():
            result["cta"] = line_clean
            continue

        # === ПРОЕКТ ===
        # Начало проекта: заглавная строка, название ЖК, или буллет
        if _is_project_header(line_clean):
            # Сохраняем предыдущий проект
            if current_project and current_project.get("name"):
                result["projects"].append(current_project)

            # Начинаем новый
            project_name = _extract_project_name(line_clean)
            current_project = {
                "name": project_name,
                "location": "",
                "first_payment": "",
                "usps": [],
                "layout_url": "",
                "website": ""
            }
            continue

        # Если есть активный проект — парсим его атрибуты
        if current_project:
            # Локация
            location = _extract_location(line_clean)
            if location:
                current_project["location"] = location
                continue

            # Первый взнос
            payment = _extract_payment(line_clean)
            if payment:
                current_project["first_payment"] = payment
                continue

            # URL
            url = _extract_url(line_clean)
            if url:
                if "presentationagent" in url or "планировка" in line_clean.lower():
                    current_project["layout_url"] = url
                else:
                    current_project["website"] = url
                continue

            # УТП (буллет или короткая строка)
            if _is_usp(line_clean):
                usp = _clean_usp(line_clean)
                if usp:
                    current_project["usps"].append(usp)

    # Добавляем последний проект
    if current_project and current_project.get("name"):
        result["projects"].append(current_project)

    # Если нет проектов — пытаемся создать один из всего текста
    if not result["projects"]:
        result["projects"].append(_parse_single_project(text))

    return result


def _is_project_header(line: str) -> bool:
    """Определяет, является ли строка заголовком проекта"""
    # Заглавные буквы + короткая строка (название ЖК обычно короткое)
    if len(line) < 50 and line[0].isupper() and not line.startswith(("—", "-", "•", "–")):
        return True

    # Начинается с номера или буллета
    if re.match(r"^(\d+[\.\)]|[\-\•\–])\s*[А-ЯA-Z]", line):
        return True

    return False


def _extract_project_name(line: str) -> str:
    """Извлекает название проекта из строки"""
    # Убираем буллеты и номера
    line = re.sub(r"^(\d+[\.\)]|[\-\•\–])\s*", "", line).strip()

    # Если есть двоеточие или тире — берём до него
    if ":" in line:
        line = line.split(":")[0]
    if "—" in line:
        line = line.split("—")[0]

    return line.strip()


def _extract_location(line: str) -> Optional[str]:
    """Извлекает локацию (м. Спартак, 5 мин)"""
    # Паттерны метро
    metro_patterns = [
        r"м\.\s*([А-Яа-я\s]+)(?:,\s*(\d+)\s*мин)?",
        r"метро\s+([А-Яа-я\s]+)(?:,\s*(\d+)\s*мин)?",
        r"(\d+)\s*мин[а-я]*\s*(?:до|от|—)\s*(?:м\.)?\s*([А-Яа-я\s]+)"
    ]

    for pattern in metro_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            if "мин" in line:
                # Формат с минутами
                station = match.group(1) if match.group(1) else match.group(2)
                minutes = match.group(2) if match.group(2) else match.group(1)
                return f"{minutes} мин до м. {station.strip()}"
            else:
                # Только станция
                return f"м. {match.group(1).strip()}"

    # Просто адрес/район
    if any(kw in line.lower() for kw in ["район", "ул.", "наб.", "проспект", "шоссе"]):
        return line.strip()

    return None


def _extract_payment(line: str) -> Optional[str]:
    """Извлекает первый взнос"""
    # Паттерны первого взноса
    payment_patterns = [
        r"(?:первый\s+взнос|пв|взнос)[:\s]*(?:от\s+)?(\d+(?:\.\d+)?)\s*(млн|тыс|%)",
        r"(\d+)%\s*=\s*(\d+(?:\.\d+)?)\s*млн",
        r"(?:от|стоимость)[:\s]*(\d+(?:\.\d+)?)\s*млн"
    ]

    for pattern in payment_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            if "%" in line and "=" in line:
                # Формат: 40% = 8 млн
                percent = match.group(1)
                amount = match.group(2)
                return f"{percent}% = {amount} млн"
            else:
                # Простой формат
                amount = match.group(1)
                unit = match.group(2).lower()
                return f"{amount} {unit}"

    return None


def _extract_url(line: str) -> Optional[str]:
    """Извлекает URL"""
    url_pattern = r"https?://[^\s]+"
    match = re.search(url_pattern, line)
    return match.group(0) if match else None


def _is_usp(line: str) -> bool:
    """Определяет, является ли строка УТП"""
    # Короткая строка с буллетом или тире
    if len(line) < 200 and re.match(r"^[\-\•\–\*]\s*", line):
        return True

    # Ключевые слова УТП
    usp_keywords = [
        "район", "школ", "сад", "парк", "набережная", "благоустройство",
        "сдача", "ремонт", "класс", "вид", "инфраструктура", "транспорт",
        "ипотека", "рассрочка", "скидка", "акция"
    ]

    if any(kw in line.lower() for kw in usp_keywords):
        return True

    return False


def _clean_usp(line: str) -> str:
    """Очищает УТП от лишних символов"""
    # Убираем буллеты и начальные символы
    line = re.sub(r"^[\-\•\–\*]\s*", "", line).strip()
    return line


def _parse_single_project(text: str) -> Dict[str, Any]:
    """Парсит весь текст как один проект"""
    project = {
        "name": "Проект",
        "location": "",
        "first_payment": "",
        "usps": [],
        "layout_url": "",
        "website": ""
    }

    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Пытаемся извлечь атрибуты
        location = _extract_location(line)
        if location:
            project["location"] = location

        payment = _extract_payment(line)
        if payment:
            project["first_payment"] = payment

        url = _extract_url(line)
        if url:
            if "presentationagent" in url:
                project["layout_url"] = url
            else:
                project["website"] = url

        if _is_usp(line):
            usp = _clean_usp(line)
            if usp:
                project["usps"].append(usp)

    # Название — первая строка или из текста
    if lines:
        first_line = lines[0].strip()
        if len(first_line) < 100 and not _extract_url(first_line):
            project["name"] = _extract_project_name(first_line)

    return project


def ask_missing_fields(parsed: Dict[str, Any]) -> List[str]:
    """
    Определяет, каких полей не хватает для полноценной генерации.
    Возвращает список вопросов для пользователя.
    """
    questions = []

    for i, proj in enumerate(parsed.get("projects", []), 1):
        prefix = f"Проект {i} ({proj.get('name', 'без названия')})"

        if not proj.get("location"):
            questions.append(f"{prefix}: Где находится? (м. Станция, мин)")

        if not proj.get("first_payment"):
            questions.append(f"{prefix}: Первый взнос? (млн или %)")

        if not proj.get("usps") or len(proj["usps"]) < 2:
            questions.append(f"{prefix}: Главные преимущества? (2-3)")

    return questions
