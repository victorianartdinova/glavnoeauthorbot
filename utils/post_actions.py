"""
Утилита для действий с постами — кнопки дизайна и сценария
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional


def get_post_actions_keyboard(
    post_id: Optional[str] = None,
    include_design: bool = True,
    include_script: bool = True,
    include_approve: bool = False
) -> InlineKeyboardMarkup:
    """
    Клавиатура действий для поста

    Args:
        post_id: ID поста для callback данных
        include_design: Показывать кнопку дизайна
        include_script: Показывать кнопку сценария
        include_approve: Показывать кнопку согласования

    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    buttons = []

    # Первый ряд — основные действия
    row1 = []

    if include_design:
        callback_data = f"design_{post_id}" if post_id else "design_post"
        row1.append(InlineKeyboardButton(text="🎨 Дизайн", callback_data=callback_data))

    if include_script:
        callback_data = f"script_{post_id}" if post_id else "script_post"
        row1.append(InlineKeyboardButton(text="🎙 Сценарий", callback_data=callback_data))

    if row1:
        buttons.append(row1)

    # Второй ряд — согласование
    if include_approve:
        row2 = []
        approve_callback = f"approve_{post_id}" if post_id else "approve_post"
        edit_callback = f"edit_{post_id}" if post_id else "edit_post"

        row2.append(InlineKeyboardButton(text="✅ Согласовать", callback_data=approve_callback))
        row2.append(InlineKeyboardButton(text="✏️ Редактировать", callback_data=edit_callback))
        buttons.append(row2)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_design_type_keyboard(post_id: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора типа дизайна

    Returns:
        InlineKeyboardMarkup с кнопками выбора формата
    """
    prefix = f"{post_id}_" if post_id else ""

    buttons = [
        [
            InlineKeyboardButton(text="📱 Баннер", callback_data=f"{prefix}design_banner"),
            InlineKeyboardButton(text="🎬 ГИФ-слайдер", callback_data=f"{prefix}design_slider")
        ],
        [
            InlineKeyboardButton(text="📑 Галерея 4-5", callback_data=f"{prefix}design_gallery"),
            InlineKeyboardButton(text="🎠 Карусель 5-8", callback_data=f"{prefix}design_carousel")
        ],
        [
            InlineKeyboardButton(text="💡 Компактное ТЗ", callback_data=f"{prefix}design_compact"),
            InlineKeyboardButton(text="📋 Подробное ТЗ", callback_data=f"{prefix}design_detailed")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}design_cancel")]
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_script_type_keyboard(post_id: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора типа сценария

    Returns:
        InlineKeyboardMarkup с кнопками выбора длительности
    """
    prefix = f"{post_id}_" if post_id else ""

    buttons = [
        [InlineKeyboardButton(text="🎙 Голосовое (45-60 сек)", callback_data=f"{prefix}script_voice_short")],
        [InlineKeyboardButton(text="🎙 Голосовое (60-90 сек)", callback_data=f"{prefix}script_voice_medium")],
        [InlineKeyboardButton(text="🎙 Голосовое (90-120 сек)", callback_data=f"{prefix}script_voice_long")],
        [InlineKeyboardButton(text="⭕ Кружок (20-30 сек)", callback_data=f"{prefix}script_circle_short")],
        [InlineKeyboardButton(text="⭕ Кружок (30-40 сек)", callback_data=f"{prefix}script_circle_medium")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}script_cancel")]
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def generate_design_for_post(
    post_text: str,
    design_type: str = "banner",
    brief_mode: str = "compact",
    client_context: str = ""
) -> str:
    """
    Генерация ТЗ дизайнеру для поста

    Args:
        post_text: текст поста
        design_type: banner, slider, gallery, carousel
        brief_mode: compact или detailed
        client_context: контекст клиента

    Returns:
        Текст ТЗ
    """
    from utils.design_brief import generate_compact_brief, generate_detailed_brief

    if brief_mode == "compact":
        return generate_compact_brief(post_text, design_type, client_context)
    else:
        return generate_detailed_brief(post_text, design_type, client_context)


async def generate_script_for_post(
    post_text: str,
    script_type: str = "voice",
    duration: str = "medium",
    client_context: str = ""
) -> str:
    """
    Генерация сценария для поста

    Args:
        post_text: текст поста
        script_type: voice или circle
        duration: short, medium, long
        client_context: контекст клиента

    Returns:
        Текст сценария
    """
    from utils.script_generator import generate_voice_script, generate_circle_script

    if script_type == "voice":
        return generate_voice_script(post_text, duration, client_context)
    else:
        return generate_circle_script(post_text, duration, client_context)
