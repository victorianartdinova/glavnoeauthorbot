"""
Отправка сообщений в рабочий чат команды
"""
from aiogram import Bot

import config
from utils.client_context import get_client_designer


async def send_to_team_chat(
    bot: Bot,
    client_slug: str,
    message: str,
    mention_designer: bool = False,
    mention_operator: bool = False
) -> bool:
    """
    Отправить сообщение в рабочий чат (в ветку клиента).

    Args:
        bot: экземпляр бота
        client_slug: slug клиента (для определения ветки)
        message: текст сообщения
        mention_designer: отметить дизайнера
        mention_operator: отметить оператора

    Returns:
        True если успешно
    """
    if not config.TEAM_CHAT_ID:
        return False

    # Получаем thread_id для клиента
    thread_id = config.CLIENT_THREADS.get(client_slug)

    # Формируем теги
    tags = []
    if mention_designer:
        designer = get_client_designer(client_slug)
        if designer:
            tags.append(f"👨‍🎨 {designer}")

    if mention_operator:
        if config.OPERATOR_USERNAME:
            tags.append(f"📤 @{config.OPERATOR_USERNAME}")

    # Собираем сообщение
    if tags:
        full_message = "\n".join(tags) + "\n\n" + message
    else:
        full_message = message

    try:
        # Разбиваем длинные сообщения
        max_length = 4000

        if len(full_message) > max_length:
            # Отправляем теги отдельно
            if tags:
                await bot.send_message(
                    config.TEAM_CHAT_ID,
                    "\n".join(tags),
                    message_thread_id=thread_id
                )

            # Разбиваем основное сообщение
            parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
            for part in parts:
                await bot.send_message(
                    config.TEAM_CHAT_ID,
                    part,
                    message_thread_id=thread_id
                )
        else:
            await bot.send_message(
                config.TEAM_CHAT_ID,
                full_message,
                message_thread_id=thread_id
            )

        return True

    except Exception as e:
        print(f"Ошибка отправки в чат: {e}")
        return False


async def send_brief_to_designer(bot: Bot, client_slug: str, brief: str) -> bool:
    """
    Отправить ТЗ дизайнеру в ветку клиента.

    Args:
        bot: экземпляр бота
        client_slug: slug клиента
        brief: текст ТЗ

    Returns:
        True если успешно
    """
    header = "📋 ТЗ ДЛЯ ДИЗАЙНЕРА\n"
    full_brief = header + brief

    return await send_to_team_chat(
        bot=bot,
        client_slug=client_slug,
        message=full_brief,
        mention_designer=True,
        mention_operator=False
    )


async def send_post_to_operator(bot: Bot, client_slug: str, post: str) -> bool:
    """
    Отправить готовый пост оператору в ветку клиента.

    Args:
        bot: экземпляр бота
        client_slug: slug клиента
        post: текст поста

    Returns:
        True если успешно
    """
    header = "📝 ПОСТ НА ПУБЛИКАЦИЮ\n"
    full_post = header + post

    return await send_to_team_chat(
        bot=bot,
        client_slug=client_slug,
        message=full_post,
        mention_designer=False,
        mention_operator=True
    )
