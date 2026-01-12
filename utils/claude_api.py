"""
Модуль для работы с Claude API
"""
import anthropic
import config


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

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

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

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

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
