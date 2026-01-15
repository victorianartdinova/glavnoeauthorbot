"""
Модуль для работы с Claude API
"""
import anthropic
import config

from utils.memory_store import format_focus_lots_for_prompt, format_banned_phrases_for_prompt
from utils.anti_repeat import format_do_not_repeat_for_prompt


def build_memory_context(client_slug: str) -> str:
    """
    Собрать контекст памяти для включения в промпт.

    Args:
        client_slug: slug клиента

    Returns:
        Строка с контекстом памяти для system prompt
    """
    sections = []

    # Фокус недели (лоты)
    focus_lots = format_focus_lots_for_prompt(client_slug)
    if focus_lots:
        sections.append(focus_lots)

    # Антиповторы
    anti_repeat = format_do_not_repeat_for_prompt(client_slug)
    if anti_repeat:
        sections.append(anti_repeat)

    # Запрещённые фразы
    banned = format_banned_phrases_for_prompt(client_slug)
    if banned:
        sections.append(banned)

    if not sections:
        return ""

    return "\n\n".join(sections)


def generate_content_with_memory(
    client_slug: str,
    system_prompt: str,
    user_prompt: str,
    model: str = "claude-sonnet-4-20250514"
) -> str:
    """
    Генерация контента с учётом памяти клиента.

    Args:
        client_slug: slug клиента
        system_prompt: базовый системный промпт
        user_prompt: промпт пользователя
        model: модель Claude

    Returns:
        str: сгенерированный текст
    """
    # Добавляем контекст памяти к системному промпту
    memory_context = build_memory_context(client_slug)

    if memory_context:
        full_system_prompt = f"{system_prompt}\n\n---\n\n{memory_context}"
    else:
        full_system_prompt = system_prompt

    return generate_content(full_system_prompt, user_prompt, model)


def generate_content(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """
    Генерация контента через Claude API

    Args:
        system_prompt: Системный промпт с контекстом
        user_prompt: Промпт пользователя с данными
        model: Модель Claude (по умолчанию Sonnet 4.5)

    Returns:
        str: Сгенерированный текст
    """
    if not config.CLAUDE_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY не найден в окружении")

    client = anthropic.Anthropic(
        api_key=config.CLAUDE_API_KEY,
        timeout=120.0  # 2 минуты на генерацию
    )

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    return message.content[0].text


def validate_lidgen_topic(topic: str) -> tuple[bool, str]:
    """
    Валидация темы для ЛИДГЕН-поста через Claude.

    Args:
        topic: предложенная тема

    Returns:
        (is_valid, reason): True если это объект недвижимости, иначе False + причина
    """
    if not config.CLAUDE_API_KEY:
        return True, ""  # Если нет API — пропускаем валидацию

    client = anthropic.Anthropic(
        api_key=config.CLAUDE_API_KEY,
        timeout=30.0  # 30 секунд для валидации
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        system="Ты валидатор тем для контент-плана агентства недвижимости.",
        messages=[
            {"role": "user", "content": f"""Проверь, является ли эта тема объектом недвижимости (ЖК, лот, квартира, подборка объектов).

Тема: {topic}

Ответь СТРОГО в формате:
ДА — если это объект недвижимости (ЖК, лот, квартира, дом, подборка объектов, конкретный адрес)
НЕТ: [причина] — если это НЕ объект (мем, прогрев, общая тема, праздник, совет)

Примеры:
- "ЖК Легенда, от 25 млн" → ДА
- "Подборка: 3 квартиры у парка" → ДА
- "Мем про выход с праздников" → НЕТ: это мем, не объект
- "Советы покупателям" → НЕТ: это прогревочный контент"""}
        ]
    )

    response = message.content[0].text.strip()

    if response.startswith("ДА"):
        return True, ""
    else:
        # Извлекаем причину
        reason = response.replace("НЕТ:", "").replace("НЕТ", "").strip()
        if not reason:
            reason = "Это не объект недвижимости"
        return False, reason
