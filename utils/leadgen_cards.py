"""
Leadgen Cards Generator v1
Генератор лидген-постов с ТЗ на карусель карточек
"""
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

from utils.claude_api import generate_content


# =============================================================================
# СХЕМА ВХОДНЫХ ДАННЫХ
# =============================================================================

@dataclass
class LeadgenProject:
    """Проект для лидген-поста"""
    name: str
    website: str = ""
    layout_url: str = ""  # Ссылка на планировку
    first_payment: str = ""  # Первый взнос
    location: str = ""  # Локация (м. Спартак, 5 мин пешком)
    project_class: str = ""  # Класс (Премиум, Бизнес)
    fin_terms: str = ""  # Финансовые условия
    usps: List[str] = field(default_factory=list)  # УТП (5-7 пунктов)
    reference_url: str = ""  # Доп. ссылка


@dataclass
class LeadgenCardsInput:
    """Входные данные для генерации лидген-поста с карточками"""
    type: str = "leadgen_cards_v1"  # v1 (gif), carousel, dual_banner
    city: str = "Москва"
    audience: str = "инвестор"  # инвестор / для жизни / семья
    cta: str = "Написать 'ПЛАНИРОВКА' в личку"
    projects: List[LeadgenProject] = field(default_factory=list)
    format_variant: str = "gif"  # gif, carousel, dual_banner


def validate_leadgen_input(data: Dict[str, Any]) -> tuple[bool, str, Optional[LeadgenCardsInput]]:
    """
    Валидация входного JSON.
    Возвращает (is_valid, error_message, parsed_input)
    """
    try:
        # Проверяем обязательные поля
        if "projects" not in data:
            return False, "Отсутствует поле 'projects'", None

        if not data["projects"]:
            return False, "Список проектов пуст", None

        if len(data["projects"]) > 5:
            return False, "Максимум 5 проектов", None

        # Парсим проекты
        projects = []
        for i, p in enumerate(data["projects"], 1):
            if not p.get("name"):
                return False, f"Проект #{i}: отсутствует название", None

            project = LeadgenProject(
                name=p.get("name", ""),
                website=p.get("website", "") or "",
                layout_url=p.get("layout_url", "") or "",
                first_payment=p.get("first_payment", "") or "",
                location=p.get("location", "") or "",
                project_class=p.get("class", "") or "",
                fin_terms=p.get("fin_terms", "") or "",
                usps=p.get("usps", []) or [],
                reference_url=p.get("reference_url", "") or ""
            )
            projects.append(project)

        result = LeadgenCardsInput(
            type=data.get("type", "leadgen_cards_v1"),
            city=data.get("city", "Москва") or "Москва",
            audience=data.get("audience", "инвестор") or "инвестор",
            cta=data.get("cta", "Написать 'ПЛАНИРОВКА' в личку") or "Написать 'ПЛАНИРОВКА' в личку",
            projects=projects,
            format_variant=data.get("format", "gif") or "gif"
        )

        return True, "", result

    except Exception as e:
        return False, f"Ошибка парсинга: {str(e)}", None


# =============================================================================
# ГЕНЕРАЦИЯ ТЕКСТА ПОСТА
# =============================================================================

def generate_post_text(input_data: LeadgenCardsInput, client_context: str = "") -> str:
    """Генерация текста поста (синхронная версия для промпта)"""

    projects_text = ""
    for i, p in enumerate(input_data.projects, 1):
        usps_text = "\n".join(f"   - {usp}" for usp in p.usps[:5]) if p.usps else "   - Нет УТП"
        projects_text += f"""
Проект {i}: {p.name}
   Локация: {p.location or 'не указана'}
   Класс: {p.project_class or 'не указан'}
   Первый взнос: {p.first_payment or 'не указан'}
   Фин. условия: {p.fin_terms or 'не указаны'}
   УТП:
{usps_text}
"""

    prompt = f"""Напиши лидген-пост для Telegram-канала недвижимости.

ДАННЫЕ:
Город: {input_data.city}
Аудитория: {input_data.audience}
CTA: {input_data.cta}

ПРОЕКТЫ:
{projects_text}

{client_context}

ТРЕБОВАНИЯ К ПОСТУ:
1. Хук в первой строке (1 строка, цепляющая)
2. Краткое описание каждого ЖК (2-3 предложения):
   - Что это за проект
   - 2-3 главные причины купить
   - Ключевые цифры (первый взнос, локация)
3. CTA в конце (1-2 строки)
4. В самом конце — блок "Ссылки:" с планировками

ФОРМАТ:
- Без названий ЖК в заголовках (только в тексте)
- Используй эмодзи умеренно
- Не более 1500 символов
- Ссылки НЕ внутри текста — только в блоке "Ссылки:" в конце

СТРУКТУРА:
[Хук]

[Проект 1: описание]

[Проект 2: описание]

[Проект 3: описание] (если есть)

[CTA]

Ссылки:
• [Название] — планировка: [url]
...
"""
    return prompt


# =============================================================================
# ГЕНЕРАЦИЯ ТЗ НА КАРТОЧКИ
# =============================================================================

# Blacklist слов для рекламных баннеров
AD_BLACKLIST = [
    "собственных", "высококачественных", "уникальных",
    "эксклюзивных", "инновационных", "передовых",
    "современных", "лучших", "идеальных"
]


def clean_ad_text(text: str) -> str:
    """Убирает заезженные слова из рекламного текста"""
    import re
    for word in AD_BLACKLIST:
        # Убираем слово со всеми падежами/числами
        pattern = re.compile(rf'\b{word[:-2]}\w*\b', re.IGNORECASE)
        text = pattern.sub('', text)
    # Убираем двойные пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def generate_carousel_brief(input_data: LeadgenCardsInput) -> str:
    """
    Генерация КОРОТКОГО ТЗ для карусели (5-8 карточек)

    Формат компактный, как внутри бота.
    """
    num_projects = len(input_data.projects)

    cards = [
        "🎨 КАРУСЕЛЬ (5-8 карточек)\n",
        f"Аудитория: {input_data.audience}\n",
        f"Город: {input_data.city}\n\n",
        "СТРУКТУРА:\n",
        "[1] Хук — вопрос/цифра\n",
        "[2] Проблема\n",
        "[3] Решение\n",
        "[4] Кейс/цифры\n",
        "[5] Оффер (цена, условия)\n",
        "[6] CTA\n\n",
        "ТРЕБОВАНИЯ:\n",
        "• 1080x1920 (story)\n",
        "• Без названий ЖК\n",
        "• Заголовок: 3-6 слов, одно действие\n",
    ]

    # Blacklist правило
    cards.append(f"• Запрещено: {', '.join(AD_BLACKLIST[:5])}...\n\n")

    # Данные проектов
    if input_data.projects:
        cards.append("ДАННЫЕ:\n")
        for i, p in enumerate(input_data.projects, 1):
            cards.append(f"{i}. {p.name}\n")
            if p.location:
                cards.append(f"   📍 {p.location}\n")
            if p.first_payment:
                cards.append(f"   💰 {p.first_payment}\n")
            if p.usps:
                cards.append(f"   УТП: {', '.join(p.usps[:2])}\n")

    return "".join(cards)


def generate_dual_banner_brief(input_data: LeadgenCardsInput) -> str:
    """
    Генерация ТЗ для A/B баннеров (2 варианта одного оффера)

    Вариант A: Рациональный (цифры, факты)
    Вариант B: Эмоциональный (lifestyle, мечта)
    """
    project = input_data.projects[0] if input_data.projects else None

    if not project:
        return "❌ Нет данных проекта"

    cards = []
    cards.append(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎨 ТЗ ДИЗАЙНЕРУ: A/B БАННЕРЫ (2 ВАРИАНТА)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ПРОЕКТ: {project.name}
ЛОКАЦИЯ: {project.location or "—"}
АУДИТОРИЯ: {input_data.audience}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ВАРИАНТ A: РАЦИОНАЛЬНЫЙ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Фокус: Цифры, выгода, конкретика

[ПЛАШКА 1]: {project.location or "ЛОКАЦИЯ"}
[ПЛАШКА 2]: {project.first_payment or "ПЕРВЫЙ ВЗНОС ОТ..."}
[ЗАГОЛОВОК]: Платёж от X₽/мес — квартира в {project.project_class or "премиум"}

[ВИЗУАЛ]:
• Фото фасада или планировки
• Таблица с условиями
• Акцент на цифрах (крупный шрифт)

[CTA]:
📞 "Узнать условия" / "Получить расчёт"

[НАСТРОЕНИЕ]:
• Сдержанно-деловое
• Цвета: нейтральные, акцент на синем/зелёном
• Шрифт: строгий, без засечек

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ВАРИАНТ B: ЭМОЦИОНАЛЬНЫЙ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Фокус: Lifestyle, мечта, эмоции

[ПЛАШКА 1]: ДОМ ВАШЕЙ МЕЧТЫ
[ПЛАШКА 2]: {project.location or "У ПАРКА"}
[ЗАГОЛОВОК]: Просыпайтесь с видом на {project.location or "зелень"} — это реальность

[ВИЗУАЛ]:
• Фото панорамного вида/интерьера
• Счастливая семья или уютная атмосфера
• Мягкий свет, теплые тона

[CTA]:
💬 "Хочу так жить" / "Покажите варианты"

[НАСТРОЕНИЕ]:
• Тёплое, вдохновляющее
• Цвета: тёплая палитра (бежевый, золотой)
• Шрифт: мягкий, с лёгкими засечками

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Формат: 1200x628 (Telegram Ads)
• Оба баннера одинаковые по размеру
• Тестируются параллельно (A/B тест)
• Нельзя: указывать название ЖК
• Обязательно: контраст для CTA-кнопки
""")

    return "".join(cards)


def generate_cards_brief(input_data: LeadgenCardsInput) -> str:
    """Генерация ТЗ на карусель карточек"""

    num_projects = len(input_data.projects)

    # Card 1: Обложка
    cards = [f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CARD 1 — ОБЛОЖКА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ЗАГОЛОВОК: [Цифра] + [Выгода для {input_data.audience}]
ПОДЗАГОЛОВОК: {input_data.city} | От [мин. первый взнос]
ТРИГГЕР: 1 строка — почему листать дальше

ДИЗАЙН-НОТЫ:
• Акцент: цифра (количество ЖК или % выгоды)
• Визуал: силуэты зданий или skyline города
• Шрифт: крупный заголовок, контраст
"""]

    # Cards 2-4: Проекты
    for i, project in enumerate(input_data.projects, 2):
        has_layout = bool(project.layout_url)
        layout_note = f"✅ Ссылка: {project.layout_url}" if has_layout else "⚠️ НЕТ ССЫЛКИ — запросить у менеджера"

        usps_text = ""
        for j, usp in enumerate(project.usps[:5], 1):
            usps_text += f"   {j}. {usp}\n"
        if not usps_text:
            usps_text = "   — УТП не указаны\n"

        card = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CARD {i} — {project.name.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
НАЗВАНИЕ: {project.name}
КЛАСС: {project.project_class or '—'}
ЛОКАЦИЯ: {project.location or '—'}

УТП (буллеты):
{usps_text}
ФИН. УСЛОВИЯ: {project.fin_terms or project.first_payment or '—'}
ПЕРВЫЙ ВЗНОС: {project.first_payment or '—'}

ССЫЛКА НА ПЛАНИРОВКУ:
{layout_note}

ДИЗАЙН-НОТЫ:
• Акцент: {"локация (метро)" if project.location else "первый взнос" if project.first_payment else "УТП"}
• Визуал: рендер здания / вид из окна / район
• Цвет: фирменный цвет проекта (если есть)
"""
        cards.append(card)

    # Card N+1: Сравнение
    comparison_card_num = num_projects + 2
    comparison_rows = ""
    for p in input_data.projects:
        audience_fit = "✓" if input_data.audience.lower() in ["инвестор", "для жизни"] else "?"
        comparison_rows += f"• {p.name}: {p.first_payment or '—'} | {p.location or '—'}\n"

    cards.append(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CARD {comparison_card_num} — СРАВНЕНИЕ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ЗАГОЛОВОК: Кому какой подходит?

МИНИ-ТАБЛИЦА:
{comparison_rows}
АУДИТОРИЯ: {input_data.audience}

ДЛЯ ИНВЕСТОРА: [Главный аргумент по доходности/росту]
ДЛЯ ЖИЗНИ: [Главный аргумент по комфорту/локации]
ДЛЯ СЕМЬИ: [Главный аргумент по инфраструктуре]

ДИЗАЙН-НОТЫ:
• Формат: таблица или сетка 3 колонки
• Акцент: иконки ЦА (💼 инвестор, 🏠 жизнь, 👨‍👩‍👧 семья)
• Минимализм: только ключевые цифры
""")

    # Card N+2: CTA
    cta_card_num = num_projects + 3
    cards.append(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 CARD {cta_card_num} — CTA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ОФФЕР: {input_data.cta}

ШАГИ:
1. Что написать: "ПЛАНИРОВКА" / "ХОЧУ" / название ЖК
2. Куда написать: в личные сообщения
3. Что получите: презентацию + расчёт

ДИЗАЙН-НОТЫ:
• Акцент: кнопка/стрелка → действие
• Цвет: контрастный CTA-цвет
• Дисклеймер: мелким шрифтом (условия ипотеки могут измениться)
""")

    # Финальный блок со ссылками
    links_block = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📎 ВСЕ ССЫЛКИ\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for p in input_data.projects:
        links_block += f"\n{p.name}:\n"
        if p.website:
            links_block += f"  • Сайт: {p.website}\n"
        if p.layout_url:
            links_block += f"  • Планировка: {p.layout_url}\n"
        if p.reference_url:
            links_block += f"  • Доп. материал: {p.reference_url}\n"
        if not (p.website or p.layout_url or p.reference_url):
            links_block += f"  • Ссылок нет — запросить у менеджера\n"

    return "".join(cards) + links_block


# =============================================================================
# ГЛАВНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ
# =============================================================================

async def generate_leadgen_cards(
    input_json: Dict[str, Any],
    client_context: str = "",
    client_slug: str = ""
) -> Dict[str, Any]:
    """
    Генерация лидген-поста + ТЗ на карточки.

    Возвращает:
    {
        "success": bool,
        "error": str | None,
        "post_text": str,  # Готовый текст поста
        "cards_brief": str,  # ТЗ на карточки
        "links_summary": str,  # Блок ссылок
        "input_data": dict  # Распарсенные входные данные
    }
    """
    # Валидация
    is_valid, error, input_data = validate_leadgen_input(input_json)
    if not is_valid:
        return {
            "success": False,
            "error": error,
            "post_text": "",
            "cards_brief": "",
            "links_summary": "",
            "input_data": {}
        }

    # Генерируем промпт для Claude
    post_prompt = generate_post_text(input_data, client_context)

    # Генерируем текст поста через Claude API
    system_prompt = """Ты — копирайтер премиальной недвижимости.
Пишешь лидген-посты для Telegram.
Стиль: лаконичный, конкретный, без воды.
Всегда выносишь ссылки в отдельный блок в конце."""

    try:
        post_text = await generate_content(
            system_prompt=system_prompt,
            user_prompt=post_prompt,
            max_tokens=2000
        )
    except Exception as e:
        # Fallback — генерируем простой текст без Claude
        post_text = _generate_fallback_post(input_data)

    # Генерируем ТЗ на карточки (не требует Claude)
    format_variant = input_data.format_variant.lower()

    if format_variant == "carousel":
        cards_brief = generate_carousel_brief(input_data)
    elif format_variant == "dual_banner":
        cards_brief = generate_dual_banner_brief(input_data)
    else:
        # По умолчанию — GIF карточки
        cards_brief = generate_cards_brief(input_data)

    # Собираем блок ссылок
    links_summary = _generate_links_summary(input_data)

    return {
        "success": True,
        "error": None,
        "post_text": post_text,
        "cards_brief": cards_brief,
        "links_summary": links_summary,
        "input_data": {
            "type": input_data.type,
            "city": input_data.city,
            "audience": input_data.audience,
            "cta": input_data.cta,
            "projects": [asdict(p) for p in input_data.projects]
        }
    }


def _generate_fallback_post(input_data: LeadgenCardsInput) -> str:
    """Fallback генерация поста без Claude"""
    lines = []

    # Хук
    if input_data.audience == "инвестор":
        lines.append(f"📈 {len(input_data.projects)} проекта для инвестиций в {input_data.city}")
    else:
        lines.append(f"🏢 {len(input_data.projects)} варианта для жизни в {input_data.city}")

    lines.append("")

    # Проекты
    for p in input_data.projects:
        lines.append(f"▪️ {p.name}")
        if p.location:
            lines.append(f"   📍 {p.location}")
        if p.first_payment:
            lines.append(f"   💰 Первый взнос: {p.first_payment}")
        if p.usps:
            lines.append(f"   ✓ {p.usps[0]}")
        lines.append("")

    # CTA
    lines.append(f"👉 {input_data.cta}")
    lines.append("")

    # Ссылки
    lines.append("Ссылки:")
    for p in input_data.projects:
        if p.layout_url:
            lines.append(f"• {p.name} — планировка: {p.layout_url}")
        elif p.website:
            lines.append(f"• {p.name} — сайт: {p.website}")

    return "\n".join(lines)


def _generate_links_summary(input_data: LeadgenCardsInput) -> str:
    """Генерация блока ссылок"""
    lines = ["📎 Ссылки:", ""]

    for p in input_data.projects:
        lines.append(f"{p.name}:")
        if p.website:
            lines.append(f"  • Сайт: {p.website}")
        if p.layout_url:
            lines.append(f"  • Планировка: {p.layout_url}")
        if not p.website and not p.layout_url:
            lines.append(f"  • Ссылок нет")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# ПРИМЕР ВХОДНЫХ ДАННЫХ
# =============================================================================

EXAMPLE_INPUT = {
    "type": "leadgen_cards_v1",
    "city": "Москва",
    "audience": "инвестор",
    "cta": "Написать 'ПЛАНИРОВКА' в личку",
    "projects": [
        {
            "name": "ALIA",
            "website": "https://alia.moscow/",
            "layout_url": "https://presentationagent.com/view/au9hw.1768063472512/696281f00e41dcc05beb40b9",
            "first_payment": "40% = 8 млн ₽",
            "location": "м. Спартак, 5–7 мин пешком",
            "class": "",
            "fin_terms": "",
            "usps": [
                "Сформированный район: БЦ Ростеха, школы/сады, спорт",
                "Набережная Москвы-реки, благоустройство уже идёт",
                "Дефицит аренды в локации",
                "Сдача в whitebox → быстрее ремонт/сдача",
                "30 га благоустройства"
            ]
        },
        {
            "name": "Upside Towers",
            "website": "",
            "layout_url": "https://presentationagent.com/view/wfz7f.1768063760611/6962831012d1b1f5c5f7dde6",
            "first_payment": "",
            "location": "5 мин до м. Бутырская",
            "class": "Премиум-класс",
            "fin_terms": "Семейная ипотека от 3,5%",
            "usps": [
                "Виды на Останкинскую башню",
                "Сдача: whitebox или с отделкой",
                "Формат: 2Е"
            ]
        },
        {
            "name": "ЖК Rise",
            "website": "",
            "layout_url": "",
            "first_payment": "ПВ от 20%",
            "location": "3 мин — м. Римская (1 станция до кольца)",
            "class": "",
            "fin_terms": "Ежемесячный платёж от 170 тыс",
            "usps": [
                "Рядом строится БЦ STONE Римская"
            ]
        }
    ]
}
