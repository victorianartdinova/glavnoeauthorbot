"""
Редакторский второй проход — сжатие, ритм, CTA
"""
import anthropic
import config


def editor_pass(text: str, direction: str = "harder") -> str:
    """
    Редакторский проход по тексту.

    Args:
        text: исходный текст поста
        direction: "harder" (жёстче, сжатие) или "softer" (мягче, развёрнутее)

    Returns:
        Отредактированный текст
    """
    if not config.CLAUDE_API_KEY:
        return text

    client = anthropic.Anthropic(
        api_key=config.CLAUDE_API_KEY,
        timeout=60.0
    )

    if direction == "harder":
        system_prompt = """Ты — редактор премиум-контента для недвижимости.

ЗАДАЧА: Сделать текст ЖЁСТЧЕ и КОРОЧЕ.

ПРАВИЛА:
1. Убери ВСЮ воду и абстракции
2. Оставь только конкретику: цифры, факты, выгоды
3. Короткие предложения (макс 10 слов)
4. Ритм: короткое → среднее → короткое
5. CTA должен быть чётким и конкретным
6. Убери вводные слова и "мягкие" конструкции

НЕ МЕНЯЙ:
- Факты и цифры
- Структуру (эмодзи, блоки)
- CTA-слово

Верни ТОЛЬКО отредактированный текст, без комментариев."""

        user_prompt = f"""Сделай этот пост жёстче и короче:

{text}"""

    else:  # softer
        system_prompt = """Ты — редактор премиум-контента для недвижимости.

ЗАДАЧА: Сделать текст МЯГЧЕ и ТЕПЛЕЕ.

ПРАВИЛА:
1. Добавь эмоциональные образы (но без "воды")
2. Сделай переходы плавнее
3. Добавь "человеческие" детали
4. Сохрани все факты и цифры
5. CTA должен звучать как приглашение, не как приказ

НЕ МЕНЯЙ:
- Факты и цифры
- Структуру (эмодзи, блоки)
- CTA-слово

Верни ТОЛЬКО отредактированный текст, без комментариев."""

        user_prompt = f"""Сделай этот пост мягче и теплее:

{text}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    return message.content[0].text


def quick_polish(text: str) -> str:
    """
    Быстрая полировка текста — убрать очевидные проблемы.

    Args:
        text: исходный текст

    Returns:
        Отполированный текст
    """
    if not config.CLAUDE_API_KEY:
        return text

    client = anthropic.Anthropic(
        api_key=config.CLAUDE_API_KEY,
        timeout=30.0
    )

    system_prompt = """Ты — редактор. Быстро исправь очевидные проблемы:
- Опечатки
- Лишние пробелы
- Дублирование слов
- Некорректные знаки препинания

НЕ МЕНЯЙ смысл и структуру. Верни ТОЛЬКО исправленный текст."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {"role": "user", "content": text}
        ]
    )

    return message.content[0].text


def extract_metadata_from_post(text: str) -> dict:
    """
    Извлечь метаданные из сгенерированного поста для сохранения в журнал.

    Args:
        text: текст поста

    Returns:
        Dict с hook_type, angle, cta
    """
    if not config.CLAUDE_API_KEY:
        return {}

    client = anthropic.Anthropic(
        api_key=config.CLAUDE_API_KEY,
        timeout=30.0
    )

    system_prompt = """Проанализируй пост и извлеки метаданные.

Ответь СТРОГО в формате JSON:
{
    "hook_type": "financial|location|premium|urgency|emotional",
    "angle": "краткое описание угла/подхода (2-3 слова)",
    "cta": "СЛОВО из CTA (то что в кавычках после 'Напишите')"
}

Только JSON, без комментариев."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system=system_prompt,
            messages=[
                {"role": "user", "content": text}
            ]
        )

        import json
        response = message.content[0].text.strip()
        # Убираем возможные markdown-обёртки
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
            response = response.rsplit("```", 1)[0]
        return json.loads(response)
    except Exception:
        return {}
