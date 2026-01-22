"""
Обработчик создания контента
"""
from aiogram import types, Dispatcher, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import json
import os
import re
from datetime import datetime

import config
from utils.client_context import load_client_context, get_client_prompt, get_client_lots, add_client_channel, list_clients, get_client_designer, get_client_emojis, get_emoji_prompt_section
from utils.plan_storage import save_plan, parse_plan_from_text, load_plan
from handlers.plan_handler import get_plan_days_keyboard
from utils.content_state import get_next_format, get_format_display, get_next_publish_date, add_brief_to_queue, peek_next_format
from utils.claude_api import generate_content, generate_content_with_memory
from utils.editor_pass import editor_pass, extract_metadata_from_post
from utils.jk_parser import find_url_in_text, parse_jk_website, format_parsed_data, search_jk_info
from utils.ad_eligibility import check_ad_eligibility, parse_lot_for_ads
from utils.content_journal import add_entry as add_journal_entry
from utils.meme_sources import get_top_references, format_reference_preview, get_reference_by_index
from utils.team_chat import send_brief_to_designer
from utils.prompt_variations import (
    get_random_leadgen_structure, get_random_leadgen_hook,
    get_random_instagram_structure, get_random_instagram_opener,
    get_random_circle_structure, get_random_circle_opener,
    get_random_voice_structure, get_random_expert_structure,
    get_random_expert_opener, get_random_style_instruction,
    detect_investment_lot
)
from utils.client_style import (
    get_style_prompt_section, validate_post, fix_post_issues,
    get_post_length_requirements
)
from utils.post_actions import (
    get_post_actions_keyboard, get_design_type_keyboard, get_script_type_keyboard,
    generate_design_for_post, generate_script_for_post
)


def escape_markdown_v2(text: str) -> str:
    """Экранирование спецсимволов для MarkdownV2"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


def safe_markdown(text: str) -> str:
    """Безопасная отправка текста без парсинга markdown"""
    return text


class ContentStates(StatesGroup):
    """Состояния для FSM"""
    waiting_for_brief_data = State()
    waiting_for_brief_ad_type = State()  # НОВОЕ: под рекламу или нет
    waiting_for_brief_mode = State()  # SHORT / NORMAL / PRO (при ENABLE_BRIEF_SHORT)
    waiting_for_live_link = State()
    waiting_for_voice_topic = State()
    waiting_for_plan_client = State()
    waiting_for_channel = State()
    # Новые состояния для /post
    waiting_for_post_format = State()
    waiting_for_post_date = State()  # Выбор даты публикации
    waiting_for_post_lot = State()
    waiting_for_post_digest_topic = State()
    waiting_for_circle_topic = State()
    # Состояния для контент-плана
    waiting_for_plan_info = State()  # НОВОЕ: сбор базовой информации
    waiting_for_plan_lots = State()
    waiting_for_plan_manual_themes = State()  # Ручной ввод тем вместо лотов
    waiting_for_plan_live = State()
    waiting_for_plan_requests = State()
    # Состояния для ТЗ из контент-плана
    waiting_for_brief_edit = State()  # Редактирование ТЗ перед отправкой
    # Редактирование сгенерированного поста
    waiting_for_post_edit = State()  # Ожидание инструкции по изменению
    # ТЗ из поста
    waiting_for_post_brief_edit = State()  # Редактирование ТЗ из поста


def get_post_edit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для редактирования сгенерированного поста"""
    # Используем get_post_actions_keyboard из utils
    base_keyboard = get_post_actions_keyboard(
        post_id=None,
        include_design=True,
        include_script=True,
        include_approve=False
    )

    # Добавляем кнопки редактирования и действий
    edit_buttons = [
        [
            InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post_regen"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="post_edit_request")
        ],
        [
            InlineKeyboardButton(text="💪 Жёстче", callback_data="post_harder"),
            InlineKeyboardButton(text="🌸 Мягче", callback_data="post_softer")
        ]
    ]

    # Кнопки дизайна и сценария из base_keyboard
    action_buttons = base_keyboard.inline_keyboard

    # Финальные кнопки
    final_buttons = [
        [
            InlineKeyboardButton(text="📋 Скопировать", callback_data="post_copy"),
            InlineKeyboardButton(text="✅ Готово", callback_data="post_done")
        ]
    ]

    return InlineKeyboardMarkup(inline_keyboard=edit_buttons + action_buttons + final_buttons)


def get_plan_skip_keyboard(show_clear: bool = False, show_manual: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для пропуска шага"""
    buttons = [
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="plan_skip")],
        [InlineKeyboardButton(text="✅ Готово, генерировать К-П", callback_data="plan_generate")],
    ]
    if show_clear:
        buttons.append([InlineKeyboardButton(text="🗑 Очистить лоты", callback_data="plan_clear_lots")])
    if show_manual:
        buttons.append([InlineKeyboardButton(text="📝 Я сам напишу темы", callback_data="plan_manual_themes")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_plan_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора периода контент-плана"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="7 дней", callback_data="plan_period_7"),
            InlineKeyboardButton(text="14 дней", callback_data="plan_period_14")
        ],
        [
            InlineKeyboardButton(text="30 дней", callback_data="plan_period_30")
        ]
    ])


def get_plan_posts_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества постов в день"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 в день", callback_data="plan_posts_1"),
            InlineKeyboardButton(text="2 в день", callback_data="plan_posts_2")
        ],
        [
            InlineKeyboardButton(text="3 в день", callback_data="plan_posts_3")
        ]
    ])


def get_plan_events_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для событий/дат"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Нет особых дат", callback_data="plan_events_skip")],
    ])


def get_post_date_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора даты публикации поста"""
    from datetime import timedelta
    today = datetime.now()
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    buttons = []
    # Сегодня
    buttons.append([
        InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data="post_date_today"
        )
    ])

    # Следующие 5 рабочих дней
    row = []
    days_added = 0
    day_offset = 1
    while days_added < 5:
        next_day = today + timedelta(days=day_offset)
        # Пропускаем выходные
        if next_day.weekday() < 5:  # Пн-Пт
            weekday = weekdays_ru[next_day.weekday()]
            row.append(InlineKeyboardButton(
                text=f"{weekday} {next_day.strftime('%d.%m')}",
                callback_data=f"post_date_{next_day.strftime('%Y-%m-%d')}"
            ))
            days_added += 1
            if len(row) == 3:
                buttons.append(row)
                row = []
        day_offset += 1

    if row:
        buttons.append(row)

    # Ввести вручную
    buttons.append([
        InlineKeyboardButton(text="✏️ Другая дата", callback_data="post_date_custom")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def cmd_plan(message: types.Message, state: FSMContext):
    """Команда контент-план — начинаем с базовых вопросов"""
    # Получаем текущего клиента из state
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    # Инициализируем данные для плана
    await state.update_data(
        plan_client=client,
        plan_lots=[],
        plan_live=[],
        plan_requests=[],
        plan_period=7,
        plan_posts_per_day=1,
        plan_events=""
    )

    await message.answer(
        f"📅 *Контент-план для {client}*\n\n"
        "Сначала несколько вопросов:\n\n"
        "❓ *На какой период план?*",
        parse_mode="Markdown",
        reply_markup=get_plan_period_keyboard()
    )
    await state.set_state(ContentStates.waiting_for_plan_info)


async def callback_plan_period(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора периода"""
    period = int(callback.data.replace("plan_period_", ""))
    await state.update_data(plan_period=period)
    await callback.answer()

    await callback.message.edit_text(
        f"✅ Период: {period} дней\n\n"
        "❓ *Сколько постов в день?*",
        parse_mode="Markdown",
        reply_markup=get_plan_posts_keyboard()
    )


async def callback_plan_posts(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора количества постов"""
    posts = int(callback.data.replace("plan_posts_", ""))
    await state.update_data(plan_posts_per_day=posts)
    await callback.answer()

    data = await state.get_data()
    period = data.get("plan_period", 7)

    await callback.message.edit_text(
        f"✅ Период: {period} дней\n"
        f"✅ Постов в день: {posts}\n\n"
        "❓ *Есть важные даты/события?*\n"
        "(праздники, акции, старт продаж)\n\n"
        "Напиши или нажми кнопку:",
        parse_mode="Markdown",
        reply_markup=get_plan_events_keyboard()
    )


async def process_plan_events_text(message: types.Message, state: FSMContext):
    """Обработка текстового ввода событий"""
    await state.update_data(plan_events=message.text)
    await proceed_to_lots(message, state)


async def callback_plan_events_skip(callback: CallbackQuery, state: FSMContext):
    """Пропуск событий"""
    await callback.answer()
    await proceed_to_lots(callback.message, state, is_callback=True)


async def proceed_to_lots(message: types.Message, state: FSMContext, is_callback: bool = False):
    """Переход к сбору лотов"""
    data = await state.get_data()
    period = data.get("plan_period", 7)
    posts = data.get("plan_posts_per_day", 1)
    events = data.get("plan_events", "")

    summary = f"✅ Период: {period} дней\n✅ Постов в день: {posts}"
    if events:
        summary += f"\n✅ События: {events}"

    text = (
        f"{summary}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Шаг 1/3: *ЛОТЫ*\n\n"
        "Отправь лоты для продвижения:\n"
        "• Название ЖК\n"
        "• Ссылка на сайт\n"
        "• Цена/платёж\n"
        "• Особенности\n\n"
        "Можно несколько сообщений подряд.\n"
        "Когда закончишь — нажми кнопку."
    )

    if is_callback:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=get_plan_skip_keyboard())
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=get_plan_skip_keyboard())

    await state.set_state(ContentStates.waiting_for_plan_lots)


def split_lots_from_message(text: str) -> list[str]:
    """Разбивает сообщение на отдельные лоты.

    Поддерживает форматы:
    - Нумерация: 1. 2. 3. или 1) 2) 3)
    - Один лот без номера
    """
    import re

    # Паттерн для нумерованных лотов: 1. или 1) в начале строки
    numbered_pattern = r'(?:^|\n)(?=\d+[.\)]\s)'

    # Проверяем, есть ли нумерация
    if re.search(r'(?:^|\n)\d+[.\)]\s', text):
        # Разбиваем по номерам
        parts = re.split(numbered_pattern, text)
        # Убираем пустые части и очищаем номера
        lot_texts = []
        for part in parts:
            part = part.strip()
            if part:
                # Убираем номер в начале (1. или 1))
                clean_part = re.sub(r'^\d+[.\)]\s*', '', part).strip()
                if clean_part:
                    lot_texts.append(clean_part)
        return lot_texts if lot_texts else [text]
    else:
        # Один лот
        return [text]


async def process_plan_lots(message: types.Message, state: FSMContext):
    """Сбор лотов для контент-плана с определением пригодности для рекламы.

    Поддерживает:
    - Несколько лотов одним сообщением (с номерами 1. 2. 3.)
    - Один лот за раз
    """
    data = await state.get_data()
    lots = data.get("plan_lots", [])

    # Разбиваем сообщение на отдельные лоты
    lot_texts = split_lots_from_message(message.text)
    added_count = 0
    results = []

    for lot_text in lot_texts:
        # Определяем, подходит ли лот для рекламы
        is_for_ads, clean_text, parsed_data = parse_lot_for_ads(lot_text)
        _, reasons = check_ad_eligibility(parsed_data)

        # Сохраняем лот с метаданными
        lot_entry = {
            "text": clean_text,
            "is_for_ads": is_for_ads,
            "reasons": reasons,
            "parsed": parsed_data
        }
        lots.append(lot_entry)
        added_count += 1

        # Формируем статус для этого лота
        if is_for_ads:
            reason_str = f" ({', '.join(reasons)})" if reasons else " (ручная пометка)"
            status = f"📢 ADS{reason_str}"
        else:
            status = "📱 Канал"

        # Краткое название лота (первые 30 символов)
        short_name = clean_text[:30] + "..." if len(clean_text) > 30 else clean_text
        results.append(f"• {short_name} — {status}")

    await state.update_data(plan_lots=lots)

    # Формируем ответ
    if added_count == 1:
        response = f"✅ Лот добавлен (всего: {len(lots)})\n{results[0]}"
    else:
        results_text = "\n".join(results)
        response = f"✅ Добавлено {added_count} лотов (всего: {len(lots)})\n\n{results_text}"

    await message.answer(
        f"{response}\n\n"
        "Отправь ещё или нажми кнопку.",
        reply_markup=get_plan_skip_keyboard(show_clear=len(lots) > 0, show_manual=len(lots) > 0)
    )


async def process_plan_clear_lots(callback: CallbackQuery, state: FSMContext):
    """Очистка всех лотов"""
    await callback.answer("Лоты очищены")
    await state.update_data(plan_lots=[])

    await callback.message.edit_text(
        "🗑 Лоты очищены\n\n"
        "Шаг 1/3: *ЛОТЫ*\n\n"
        "Отправь лоты для продвижения:\n"
        "• Название ЖК\n"
        "• Ссылка на сайт\n"
        "• Цена/платёж\n"
        "• Особенности\n\n"
        "Можно несколько сообщений подряд.",
        parse_mode="Markdown",
        reply_markup=get_plan_skip_keyboard(show_clear=False)
    )


async def process_plan_skip_lots(callback: CallbackQuery, state: FSMContext):
    """Переход к живому контенту"""
    await callback.answer()
    await callback.message.answer(
        "Шаг 2/3: *ЖИВОЙ КОНТЕНТ*\n\n"
        "Что есть для публикации?\n"
        "• Ссылки на Instagram/Reels\n"
        "• Темы для кружков\n"
        "• Идеи для историй\n\n"
        "Можно несколько сообщений.",
        parse_mode="Markdown",
        reply_markup=get_plan_skip_keyboard()
    )
    await state.set_state(ContentStates.waiting_for_plan_live)


async def process_plan_live(message: types.Message, state: FSMContext):
    """Сбор живого контента"""
    data = await state.get_data()
    live = data.get("plan_live", [])
    live.append(message.text)
    await state.update_data(plan_live=live)

    await message.answer(
        f"✅ Добавлено ({len(live)})\n\n"
        "Отправь ещё или нажми кнопку.",
        reply_markup=get_plan_skip_keyboard()
    )


async def callback_plan_manual_themes(callback: CallbackQuery, state: FSMContext):
    """Переход к ручному вводу тем"""
    await callback.answer()
    await callback.message.edit_text(
        "📝 *РУЧНОЙ ВВОД ТЕМ*\n\n"
        "Напиши темы для постов (одна в строке):\n"
        "• Можно с нумерацией: 1. Тема первая\n"
        "• Можно без: просто текст\n"
        "• Одна тема = один пост\n\n"
        "Когда закончишь — нажми кнопку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="plan_skip_themes")],
            [InlineKeyboardButton(text="✅ Готово, генерировать", callback_data="plan_themes_done")]
        ])
    )
    await state.set_state(ContentStates.waiting_for_plan_manual_themes)
    await state.update_data(plan_manual_themes=[])


async def process_plan_manual_themes(message: types.Message, state: FSMContext):
    """Сбор ручных тем"""
    data = await state.get_data()
    themes = data.get("plan_manual_themes", [])

    # Парсим текст как ручные темы (поддерживаем нумерацию)
    new_themes = split_lots_from_message(message.text)  # Переиспользуем функцию для парсинга
    themes.extend(new_themes)

    await state.update_data(plan_manual_themes=themes)

    themes_list = "\n".join([f"• {t[:50]}" for t in themes])
    await message.answer(
        f"✅ Добавлено {len(new_themes)} тем (всего: {len(themes)})\n\n{themes_list}\n\n"
        "Отправь ещё или нажми кнопку.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="plan_skip_themes")],
            [InlineKeyboardButton(text="✅ Готово, генерировать", callback_data="plan_themes_done")]
        ])
    )


async def callback_plan_skip_themes(callback: CallbackQuery, state: FSMContext):
    """Пропуск ручных тем и переход к живому контенту"""
    await callback.answer()
    await callback.message.edit_text(
        "Шаг 2/3: *ЖИВОЙ КОНТЕНТ*\n\n"
        "Что есть для публикации?\n"
        "• Ссылки на Instagram/Reels\n"
        "• Темы для кружков\n"
        "• Идеи для историй\n\n"
        "Можно несколько сообщений.",
        parse_mode="Markdown",
        reply_markup=get_plan_skip_keyboard()
    )
    await state.set_state(ContentStates.waiting_for_plan_live)


async def callback_plan_themes_done(callback: CallbackQuery, state: FSMContext):
    """Готово с ручными темами — переход к живому контенту"""
    await callback.answer()
    await callback.message.edit_text(
        "Шаг 2/3: *ЖИВОЙ КОНТЕНТ*\n\n"
        "Что еще есть для публикации?\n"
        "• Ссылки на Instagram/Reels\n"
        "• Темы для кружков\n"
        "• Идеи для историй\n\n"
        "Можно несколько сообщений или пропустить.",
        parse_mode="Markdown",
        reply_markup=get_plan_skip_keyboard()
    )
    await state.set_state(ContentStates.waiting_for_plan_live)


async def process_plan_skip_live(callback: CallbackQuery, state: FSMContext):
    """Переход к просьбам клиента"""
    await callback.answer()
    await callback.message.answer(
        "Шаг 3/3: *ПРОСЬБЫ КЛИЕНТА*\n\n"
        "Есть особые пожелания?\n"
        "• Темы постов\n"
        "• Акценты на объекты\n"
        "• События/акции\n\n"
        "Можно несколько сообщений.",
        parse_mode="Markdown",
        reply_markup=get_plan_skip_keyboard()
    )
    await state.set_state(ContentStates.waiting_for_plan_requests)


async def process_plan_requests(message: types.Message, state: FSMContext):
    """Сбор просьб клиента"""
    data = await state.get_data()
    requests = data.get("plan_requests", [])
    requests.append(message.text)
    await state.update_data(plan_requests=requests)

    await message.answer(
        f"✅ Добавлено ({len(requests)})\n\n"
        "Отправь ещё или нажми кнопку для генерации.",
        reply_markup=get_plan_skip_keyboard()
    )


async def process_plan_generate(callback: CallbackQuery, state: FSMContext):
    """Генерация контент-плана на основе собранных данных"""
    await callback.answer()
    data = await state.get_data()

    client = data.get("plan_client")
    lots = data.get("plan_lots", [])
    live = data.get("plan_live", [])
    requests = data.get("plan_requests", [])
    manual_themes = data.get("plan_manual_themes", [])
    period = data.get("plan_period", 7)
    posts_per_day = data.get("plan_posts_per_day", 1)
    events = data.get("plan_events", "")

    await callback.message.answer(f"⏳ Генерирую контент-план на {period} дней...")

    plan_id = await generate_content_plan_with_data(
        callback.message, client, lots, live, requests,
        period=period, posts_per_day=posts_per_day, events=events,
        manual_themes=manual_themes
    )

    # Сохраняем plan_id в state для работы с днями
    await state.update_data(
        current_client=client,
        current_plan_id=plan_id
    )

    # Проверяем есть ли ADS-лоты для ТЗ дизайнеру
    ads_lots = [lot for lot in lots if isinstance(lot, dict) and lot.get("is_for_ads")]

    if ads_lots:
        # Сохраняем данные для следующего шага
        await state.update_data(
            ads_lots=ads_lots,
            selected_lots=[i for i in range(len(ads_lots))],  # По умолчанию все выбраны
            current_brief_index=0
        )

        # Показываем кнопку для ТЗ дизайнеру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📤 Отправить ТЗ дизайнеру ({len(ads_lots)} лотов)", callback_data="plan_to_brief")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="plan_finish")]
        ])
        await callback.message.answer(
            f"📢 Есть {len(ads_lots)} лотов для Telegram Ads.\n"
            "Хочешь сгенерировать ТЗ для дизайнера?",
            reply_markup=keyboard
        )


async def generate_content_plan(message: types.Message, client_slug: str):
    """Быстрая генерация контент-плана (без сбора данных)"""
    await generate_content_plan_with_data(message, client_slug, [], [], [])


async def generate_content_plan_with_data(
    message: types.Message,
    client_slug: str,
    lots: list,
    live: list,
    requests: list,
    period: int = 7,
    posts_per_day: int = 1,
    events: str = "",
    manual_themes: list = None
) -> str:
    """Генерация контент-плана на основе собранных данных. Возвращает plan_id."""
    if manual_themes is None:
        manual_themes = []

    try:
        # Загружаем контекст клиента
        context = get_client_prompt(client_slug)

        # Формируем информацию о лотах с пометкой ADS
        lots_info = ""
        if lots:
            lots_for_ads = []
            lots_for_channel = []

            for i, lot in enumerate(lots, 1):
                # Поддержка старого формата (строка) и нового (dict)
                if isinstance(lot, dict):
                    lot_text = lot.get("text", "")
                    is_for_ads = lot.get("is_for_ads", False)
                    reasons = lot.get("reasons", [])
                else:
                    lot_text = lot
                    is_for_ads, _, parsed = parse_lot_for_ads(lot)
                    _, reasons = check_ad_eligibility(parsed)

                if is_for_ads:
                    reason_str = f" ({', '.join(reasons)})" if reasons else ""
                    lots_for_ads.append(f"{i}. 📢 {lot_text}{reason_str}")
                else:
                    lots_for_channel.append(f"{i}. 📱 {lot_text}")

            lots_info = "ЛОТЫ ДЛЯ ПРОДВИЖЕНИЯ:\n"
            if lots_for_ads:
                lots_info += "\n🎯 ДЛЯ TELEGRAM ADS:\n"
                lots_info += "\n".join(lots_for_ads) + "\n"
            if lots_for_channel:
                lots_info += "\n📱 ТОЛЬКО ДЛЯ КАНАЛА:\n"
                lots_info += "\n".join(lots_for_channel) + "\n"
        else:
            lots_info = "Лотов не указано — используй образовательный контент"

        # Живой контент
        live_info = ""
        if live:
            live_info = "\nЖИВОЙ КОНТЕНТ:\n"
            for item in live:
                live_info += f"• {item}\n"

        # Просьбы клиента
        requests_info = ""
        if requests:
            requests_info = "\nПРОСЬБЫ КЛИЕНТА:\n"
            for item in requests:
                requests_info += f"• {item}\n"

        # События/даты
        events_info = ""
        if events:
            events_info = f"\nВАЖНЫЕ ДАТЫ/СОБЫТИЯ:\n{events}\n"

        # Ручные темы
        themes_info = ""
        if manual_themes:
            themes_info = "\nРУЧНЫЕ ТЕМЫ ПОЛЬЗОВАТЕЛЯ (ПРИОРИТЕТ!!!):\n"
            for i, theme in enumerate(manual_themes, 1):
                themes_info += f"{i}. {theme}\n"
            themes_info += "\n⚠️ ОБЯЗАТЕЛЬНО включи эти темы в план в указанном порядке.\n"

        # Системный промпт
        system_prompt = f"""Ты — контент-стратег для агентства недвижимости премиум-сегмента.

{context}

Твоя задача: создать контент-план на {period} дней в формате КАЛЕНДАРЯ.

ПАРАМЕТРЫ:
- Период: {period} дней
- Постов в день: {posts_per_day}

ФОРМАТЫ КОНТЕНТА (используй разные):
🏢 ЛИДГЕН — пост про конкретный ЖК/лот
🎙 КРУЖОК — голосовой кружок от брокера (тема для записи)
📚 ЭКСПЕРТ — советы, ошибки, разборы
📰 ДАЙДЖЕСТ — лёгкий контент на выходные
📸 LIVE — подводка к материалу из Instagram

ПОМЕТКИ ЛОТОВ:
📢 ДЛЯ ADS — лот подходит для Telegram Ads (низкий ПВ, платёж, скидка, старт продаж)
📱 ТОЛЬКО КАНАЛ — лот только для канала, без рекламы

ПРАВИЛА:
1. По будням (Пн-Пт): лидген + кружки + эксперт
2. На выходные (Сб-Вс): дайджест или живой контент
3. Кружки — 2-3 раза в неделю
4. Для каждого кружка указывай тему и 2-3 тезиса
5. ПРИОРИТЕТ ручным темам пользователя — включи их все в план
6. Если указаны события/даты — обязательно учитывай их в плане
7. ОБЯЗАТЕЛЬНО указывай пометку 📢ADS или 📱КАНАЛ для каждого лидген-поста

НЕ используй markdown (звёздочки, подчёркивания).
Эмодзи используй для типов контента."""

        # Текущая дата
        today = datetime.now()
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        user_prompt = f"""Создай контент-план на {period} дней начиная с {today.strftime('%d.%m.%Y')} ({weekday_names[today.weekday()]}).
Постов в день: {posts_per_day}

{themes_info}
{lots_info}
{live_info}
{requests_info}
{events_info}

ФОРМАТ ОТВЕТА (строго):

📅 КОНТЕНТ-ПЛАН: {client_slug.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📆 [Дата] ([День недели])
[Эмодзи типа] [Тип]: [Тема] [📢ADS или 📱КАНАЛ для лидгена]
[Если кружок — добавь тезисы]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📆 [Следующая дата]...

ПРИМЕР для лидгена:
🏢 ЛИДГЕН: ЖК Река — платёж 89к/мес 📢ADS
🏢 ЛИДГЕН: ЖК Премиум — пентхаус с террасой 📱КАНАЛ

В конце:
💡 РЕКОМЕНДАЦИИ (2-3 пункта)"""

        # Генерация через Claude
        plan_text = generate_content(system_prompt, user_prompt)

        # Парсим план в структурированный формат
        days = parse_plan_from_text(plan_text, period)

        # Сохраняем план
        plan_id = save_plan(client_slug, days, period)

        # Отправляем результат
        max_length = 4000
        if len(plan_text) > max_length:
            await message.answer("📋 Контент-план готов:\n")
            parts = [plan_text[i:i+max_length] for i in range(0, len(plan_text), max_length)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(f"📋 Контент-план готов:\n\n{plan_text}")

        # Показываем кнопки дней
        plan_data = load_plan(client_slug, plan_id)
        if plan_data:
            await message.answer(
                "👇 Выбери день для действий:",
                reply_markup=get_plan_days_keyboard(plan_data)
            )

        return plan_id

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")
        return ""


# =============================================================================
# ТЗ ДИЗАЙНЕРУ ИЗ КОНТЕНТ-ПЛАНА
# =============================================================================

def get_lot_selection_keyboard(ads_lots: list, selected: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора лотов"""
    buttons = []
    for i, lot in enumerate(ads_lots):
        lot_text = lot.get("text", "")[:25]
        check = "✅" if i in selected else "☐"
        buttons.append([InlineKeyboardButton(
            text=f"{check} {lot_text}...",
            callback_data=f"lot_toggle_{i}"
        )])

    # Кнопки управления
    buttons.append([
        InlineKeyboardButton(text="✅ Все", callback_data="lot_select_all"),
        InlineKeyboardButton(text="☐ Сбросить", callback_data="lot_select_none")
    ])
    buttons.append([InlineKeyboardButton(text="➡️ Далее", callback_data="lot_selection_done")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def callback_plan_to_brief(callback: CallbackQuery, state: FSMContext):
    """Переход к выбору лотов для ТЗ"""
    await callback.answer()
    data = await state.get_data()

    ads_lots = data.get("ads_lots", [])
    selected = data.get("selected_lots", [])

    await callback.message.edit_text(
        "📋 Выбери лоты для ТЗ дизайнеру:\n\n"
        "(нажми на лот чтобы выбрать/убрать)",
        reply_markup=get_lot_selection_keyboard(ads_lots, selected)
    )


async def callback_lot_toggle(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора лота"""
    lot_index = int(callback.data.replace("lot_toggle_", ""))
    data = await state.get_data()

    selected = data.get("selected_lots", [])

    if lot_index in selected:
        selected.remove(lot_index)
    else:
        selected.append(lot_index)

    await state.update_data(selected_lots=selected)
    ads_lots = data.get("ads_lots", [])

    await callback.message.edit_reply_markup(
        reply_markup=get_lot_selection_keyboard(ads_lots, selected)
    )
    await callback.answer()


async def callback_lot_select_all(callback: CallbackQuery, state: FSMContext):
    """Выбрать все лоты"""
    data = await state.get_data()
    ads_lots = data.get("ads_lots", [])
    selected = list(range(len(ads_lots)))

    await state.update_data(selected_lots=selected)

    await callback.message.edit_reply_markup(
        reply_markup=get_lot_selection_keyboard(ads_lots, selected)
    )
    await callback.answer("Все выбраны")


async def callback_lot_select_none(callback: CallbackQuery, state: FSMContext):
    """Сбросить выбор"""
    data = await state.get_data()
    ads_lots = data.get("ads_lots", [])

    await state.update_data(selected_lots=[])

    await callback.message.edit_reply_markup(
        reply_markup=get_lot_selection_keyboard(ads_lots, [])
    )
    await callback.answer("Сброшено")


async def callback_lot_selection_done(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора лотов — генерация ТЗ"""
    await callback.answer()
    data = await state.get_data()

    ads_lots = data.get("ads_lots", [])
    selected = data.get("selected_lots", [])
    client = data.get("current_client")

    if not selected:
        await callback.message.edit_text("❌ Не выбрано ни одного лота")
        await state.clear()
        await state.update_data(current_client=client)
        return

    # Сохраняем выбранные лоты для обработки
    selected_lots_data = [ads_lots[i] for i in sorted(selected)]
    await state.update_data(
        briefs_to_generate=selected_lots_data,
        current_brief_index=0,
        generated_briefs=[]
    )

    await callback.message.edit_text(f"⏳ Генерирую ТЗ для {len(selected_lots_data)} лотов...")

    # Генерируем первый бриф
    await generate_next_brief(callback.message, state)


async def generate_next_brief(message: types.Message, state: FSMContext):
    """Генерация ТЗ для следующего лота"""
    data = await state.get_data()

    briefs_to_generate = data.get("briefs_to_generate", [])
    current_index = data.get("current_brief_index", 0)
    generated_briefs = data.get("generated_briefs", [])
    client = data.get("current_client")

    if current_index >= len(briefs_to_generate):
        # Все брифы сгенерированы — завершаем
        await message.answer(
            f"✅ Готово! Сгенерировано {len(generated_briefs)} ТЗ.\n"
            "Все отправлены дизайнеру."
        )
        await state.clear()
        await state.update_data(current_client=client)
        return

    lot = briefs_to_generate[current_index]
    lot_text = lot.get("text", "")

    # Генерируем ТЗ
    try:
        emoji_section = get_emoji_prompt_section(client)
        designer = get_client_designer(client)

        # Определяем формат и дату
        content_format = get_next_format()
        format_display = get_format_display(content_format)
        pub_date, pub_weekday = get_next_publish_date()

        system_prompt = f"""Ты — копирайтер. Создаёшь ТЗ для дизайнеров баннеров Telegram Ads.

ФОРМАТ ТЕКСТОВЫХ БЛОКОВ:
[ПЛАШКА 1] — Локация/Срочность (формула: [ВРЕМЯ] ДО [МЕСТО] или [СТАТУС])
[ПЛАШКА 2] — Дополнительный триггер (уникальная фишка в 2-3 словах)
[ЗАГОЛОВОК] — Основная выгода (тип объекта + главное УТП)

ПРАВИЛА:
- Генерируй ТОЛЬКО текстовые блоки (визуалы дизайнер берёт с сайта)
- НЕ указывай название ЖК и девелопера
- НЕ указывай размеры в пикселях
- Текст плашек: UPPERCASE, 2-4 слова
- Время до метро пиши как "мин." (не "минут")

ЗАПРЕЩЁННЫЕ УТП:
❌ "История встречается с будущим"
❌ "Пространство, созданное для вас"
❌ Любые абстракции

ИСПОЛЬЗУЙ конкретику:
✅ "7 МИН. ДО СИТИ"
✅ "КЛЮЧИ СЕЙЧАС"
✅ "ПЛАТЁЖ 89 000 ₽/МЕС"
"""

        user_prompt = f"""Данные лота:
{lot_text}

📅 Дата: {pub_date} ({pub_weekday})
🎬 Формат: {format_display}
📢 Тип: ДЛЯ TELEGRAM ADS

Сгенерируй 3 ВАРИАНТА текстовых блоков:
1. ФИНАНСЫ — акцент на доступности
2. ЛОКАЦИЯ — акцент на близости
3. ПРЕМИУМ — акцент на уникальности

Формат ответа:
📋 ТЗ ДЛЯ ДИЗАЙНЕРА

📅 Дата: {pub_date} ({pub_weekday})
🎬 Формат: {format_display}

═══════════════════════════════════════

🔥 ВАРИАНТ 1: ФИНАНСЫ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...

═══════════════════════════════════════

📍 ВАРИАНТ 2: ЛОКАЦИЯ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...

═══════════════════════════════════════

✨ ВАРИАНТ 3: ПРЕМИУМ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...
"""

        brief = generate_content(system_prompt, user_prompt)

        # Сохраняем бриф
        generated_briefs.append({
            "lot": lot,
            "brief": brief,
            "date": pub_date,
            "format": format_display
        })

        await state.update_data(
            generated_briefs=generated_briefs,
            current_brief_text=brief,
            current_lot=lot
        )

        # Показываем превью с кнопками
        short_lot = lot_text[:40] + "..." if len(lot_text) > 40 else lot_text

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="brief_edit")],
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="brief_send"),
                InlineKeyboardButton(text="⏭ Пропустить", callback_data="brief_skip")
            ]
        ])

        # Обрезаем бриф для превью
        preview = brief[:2000] + "..." if len(brief) > 2000 else brief

        await message.answer(
            f"📋 ТЗ {current_index + 1}/{len(briefs_to_generate)}\n"
            f"📍 {short_lot}\n\n"
            f"{preview}",
            reply_markup=keyboard
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации ТЗ: {e}")
        # Пропускаем этот лот и идём к следующему
        await state.update_data(current_brief_index=current_index + 1)
        await generate_next_brief(message, state)


async def callback_brief_edit(callback: CallbackQuery, state: FSMContext):
    """Редактирование ТЗ"""
    await callback.answer()
    data = await state.get_data()
    brief = data.get("current_brief_text", "")

    await callback.message.answer(
        "✏️ Отправь исправленный текст ТЗ.\n"
        "Или отправь только то, что нужно изменить — я пойму.\n\n"
        "Текущий текст скопирован выше ⬆️"
    )
    await state.set_state(ContentStates.waiting_for_brief_edit)


async def process_brief_edit(message: types.Message, state: FSMContext):
    """Обработка отредактированного ТЗ"""
    new_text = message.text
    data = await state.get_data()

    # Сохраняем новый текст
    await state.update_data(current_brief_text=new_text)
    await state.set_state(None)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ещё редактировать", callback_data="brief_edit")],
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="brief_send"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="brief_skip")
        ]
    ])

    preview = new_text[:2000] + "..." if len(new_text) > 2000 else new_text
    await message.answer(
        f"✅ Текст обновлён:\n\n{preview}",
        reply_markup=keyboard
    )


async def callback_brief_send(callback: CallbackQuery, state: FSMContext):
    """Отправка ТЗ дизайнеру"""
    await callback.answer("Отправляю...")
    data = await state.get_data()

    brief = data.get("current_brief_text", "")
    client = data.get("current_client")
    current_index = data.get("current_brief_index", 0)
    briefs_to_generate = data.get("briefs_to_generate", [])

    designer = get_client_designer(client)

    # Отправляем в рабочий чат
    if config.TEAM_CHAT_ID:
        try:
            bot: Bot = callback.message.bot
            ads_tag = "📢 ДЛЯ TELEGRAM ADS\n"
            designer_tag = f"👨‍🎨 {designer}\n" if designer else ""
            full_message = f"{ads_tag}{designer_tag}\n{brief}"

            max_length = 4000
            if len(full_message) > max_length:
                await bot.send_message(config.TEAM_CHAT_ID, f"{ads_tag}{designer_tag}")
                parts = [brief[i:i+max_length] for i in range(0, len(brief), max_length)]
                for part in parts:
                    await bot.send_message(config.TEAM_CHAT_ID, part)
            else:
                await bot.send_message(config.TEAM_CHAT_ID, full_message)

            await callback.message.answer(f"✅ ТЗ отправлено дизайнеру {designer or ''}")

        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка отправки: {e}")

    # Переходим к следующему
    await state.update_data(current_brief_index=current_index + 1)
    await generate_next_brief(callback.message, state)


async def callback_brief_skip(callback: CallbackQuery, state: FSMContext):
    """Пропуск текущего ТЗ"""
    await callback.answer("Пропущено")
    data = await state.get_data()

    current_index = data.get("current_brief_index", 0)

    await state.update_data(current_brief_index=current_index + 1)
    await generate_next_brief(callback.message, state)


async def callback_plan_finish(callback: CallbackQuery, state: FSMContext):
    """Завершение без генерации ТЗ"""
    await callback.answer()
    data = await state.get_data()
    client = data.get("current_client")

    await callback.message.edit_text("✅ Контент-план готов!")
    await state.clear()
    if client:
        await state.update_data(current_client=client)


async def cmd_brief(message: types.Message, state: FSMContext):
    """Команда /brief - генерация ТЗ для дизайнера"""
    # Показываем следующий формат и дату
    next_format = peek_next_format()
    format_display = get_format_display(next_format)

    await message.answer(
        "🎨 *ТЗ для дизайнера*\n\n"
        "Отправь данные по шаблону:\n\n"
        "🔗 *Ссылка:* https://jk-example.ru\n"
        "💰 *Цена:* от 25 млн\n"
        "💳 *ПВ/платёж:* от 2.5 млн / 150 тыс/мес\n"
        "🏷 *Скидка:* -10% до конца месяца\n"
        "✨ *Особенности:* терраса, вид на парк\n"
        "🏢 *Тип:* жилая / коммерция\n\n"
        f"📌 Следующий формат: *{format_display}*\n\n"
        "Распаршу сайт и сделаю 3 варианта текстов",
        parse_mode="Markdown"
    )
    await state.set_state(ContentStates.waiting_for_brief_data)


async def process_brief_data(message: types.Message, state: FSMContext):
    """Обработка данных для генерации брифа — шаг 1: парсинг"""
    user_input = message.text

    # Ищем URL в сообщении
    url = find_url_in_text(user_input)
    parsed_data = ""

    if url:
        await message.answer(f"⏳ Парсим сайт {url}...")
        parse_result = await parse_jk_website(url)

        if parse_result["parse_success"]:
            parsed_data = format_parsed_data(parse_result)
            # Показываем что нашли
            found_items = []
            if parse_result["name"]:
                found_items.append(f"📍 {parse_result['name']}")
            if parse_result["prices"]:
                found_items.append(f"💰 {', '.join(parse_result['prices'])}")
            if parse_result["metro"]:
                metro_str = [f"{m['station']} ({m['time']})" if m['time'] else m['station'] for m in parse_result['metro']]
                found_items.append(f"🚇 {', '.join(metro_str)}")
            if parse_result["features"]:
                found_items.append(f"✨ {', '.join(parse_result['features'][:5])}")

            if found_items:
                await message.answer("✅ Найдено:\n" + "\n".join(found_items))
        else:
            await message.answer(f"⚠️ {parse_result['error']}. Работаю с ручными данными...")

    # Сохраняем данные и спрашиваем про рекламу
    await state.update_data(brief_input=user_input, brief_url=url, brief_parsed=parsed_data)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Да, под рекламу", callback_data="brief_ad_yes"),
            InlineKeyboardButton(text="📱 Только канал", callback_data="brief_ad_no")
        ]
    ])

    await message.answer(
        "❓ Это под рекламу (Telegram Ads)?",
        reply_markup=keyboard
    )
    await state.set_state(ContentStates.waiting_for_brief_ad_type)


async def callback_brief_ad_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа размещения (реклама/канал)"""
    is_for_ads = callback.data == "brief_ad_yes"
    await state.update_data(brief_is_for_ads=is_for_ads)

    # Если флаг ENABLE_BRIEF_SHORT — спрашиваем режим
    if config.ENABLE_BRIEF_SHORT:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ SHORT", callback_data="brief_mode_short"),
                InlineKeyboardButton(text="📋 NORMAL", callback_data="brief_mode_normal"),
            ],
            [
                InlineKeyboardButton(text="📚 PRO (3 варианта)", callback_data="brief_mode_pro"),
            ]
        ])

        await callback.message.edit_text(
            "🎨 Выбери режим ТЗ:\n\n"
            "⚡ *SHORT* — компактное (помещается на экран)\n"
            "📋 *NORMAL* — стандартное\n"
            "📚 *PRO* — 3 варианта с идеями",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await state.set_state(ContentStates.waiting_for_brief_mode)
        await callback.answer()
        return

    # Без флага — сразу генерируем NORMAL
    await generate_brief_with_mode(callback, state, "normal")


async def callback_brief_mode(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора режима ТЗ"""
    mode = callback.data.replace("brief_mode_", "")
    await generate_brief_with_mode(callback, state, mode)


async def generate_brief_with_mode(callback: CallbackQuery, state: FSMContext, mode: str):
    """Генерация ТЗ с выбранным режимом"""
    data = await state.get_data()
    is_for_ads = data.get("brief_is_for_ads", False)

    user_input = data.get("brief_input", "")
    url = data.get("brief_url")
    parsed_data = data.get("brief_parsed", "")

    # Определяем формат и дату
    content_format = get_next_format()
    format_display = get_format_display(content_format)
    pub_date, pub_weekday = get_next_publish_date()

    ad_type = "Реклама + канал" if is_for_ads else "Только канал"
    mode_display = {"short": "SHORT", "normal": "NORMAL", "pro": "PRO"}.get(mode, "NORMAL")

    await callback.message.edit_text(
        f"📅 Дата: {pub_date} ({pub_weekday})\n"
        f"🎬 Формат: {format_display}\n"
        f"📢 Тип: {ad_type}\n"
        f"🎨 Режим: {mode_display}\n\n"
        "⏳ Генерирую ТЗ..."
    )
    await callback.answer()

    try:
        # Получаем клиента из state
        client_slug = data.get("current_client")
        if not client_slug:
            await callback.message.answer("⚠️ Сначала выбери клиента")
            return
        emoji_section = get_emoji_prompt_section(client_slug)

        # === SHORT режим — компактное ТЗ ===
        if mode == "short":
            short_system = """Ты — копирайтер. Создаёшь КОМПАКТНОЕ ТЗ для дизайнера.

ФОРМАТ SHORT (строго):
1. ИДЕЯ УПАКОВКИ (1 строка)
2. КОЛ-ВО КАРТОЧЕК: N + ресайз сториз: да/нет
3. ТЕКСТЫ:
   [1] текст карточки 1
   [2] текст карточки 2
   ...
4. ПЛАШКА/ЗАГОЛОВОК (если нужно) — 1 строка

ЗАПРЕЩЕНО:
- Длинные описания
- Название ЖК и застройщика
- Больше 12 строк всего"""

            short_user = f"""Данные лота:
{user_input}

Создай КОМПАКТНОЕ ТЗ дизайнеру в формате SHORT.
Максимум 12 строк. Только главное."""

            brief = generate_content(short_system, short_user)

            # Отправляем в командный чат
            if config.TEAM_CHAT_ID:
                try:
                    bot: Bot = callback.message.bot
                    thread_id = config.CLIENT_THREADS.get(client_slug)
                    await bot.send_message(
                        config.TEAM_CHAT_ID,
                        f"🎨 *ТЗ SHORT* ({client_slug})\n\n{brief}",
                        message_thread_id=thread_id,
                        parse_mode="Markdown"
                    )
                    await callback.message.answer(f"✅ ТЗ SHORT отправлено\n\n{brief}")
                except Exception as e:
                    await callback.message.answer(f"📋 *ТЗ SHORT:*\n\n{brief}", parse_mode="Markdown")
            else:
                await callback.message.answer(f"📋 *ТЗ SHORT:*\n\n{brief}", parse_mode="Markdown")

            await state.clear()
            return

        # === NORMAL/PRO режимы — стандартный промпт ===
        # Системный промпт (ОБНОВЛЁННЫЙ)
        system_prompt = f"""Ты — копирайтер Apple Real Estate. Создаёшь ТЗ для дизайнеров и лидген-посты.

═══ КОНТЕКСТ КЛИЕНТА ═══
- Премиум недвижимость от 25 млн рублей
- Аудитория: покупатели 25-45 лет, семейная ипотека, инвесторы
- Стиль: премиум, но доступный (тёплый aspirational, не холодный luxury)

═══ TONE OF VOICE ═══
- Дружелюбно-профессиональный, как умный друг из отрасли
- Разговорный язык + storytelling + лёгкая ирония
- Конкретика вместо абстракций (цифры, сроки, факты)

═══ ЧАСТЬ 1: ТЗ ДЛЯ ДИЗАЙНЕРА ═══

ФОРМАТ ТЕКСТОВЫХ БЛОКОВ:
[ПЛАШКА 1] — Локация/Срочность (формула: [ВРЕМЯ] ДО [МЕСТО] или [СТАТУС])
[ПЛАШКА 2] — Дополнительный триггер (уникальная фишка в 2-3 словах)
[ЗАГОЛОВОК] — Основная выгода (тип объекта + главное УТП)

ПРАВИЛА ТЗ:
- Генерируй ТОЛЬКО текстовые блоки (визуалы дизайнер берёт с сайта)
- НЕ указывай название ЖК и девелопера в ТЗ
- НЕ указывай размеры в пикселях
- Каждый вариант — РАЗНЫЙ триггер
- Текст плашек: UPPERCASE, 2-4 слова
- Время до метро пиши как "мин." (не "минут")

═══ КРИТИЧНО: ЗАПРЕЩЁННЫЕ УТП (ВОДА) ═══
НЕ ИСПОЛЬЗУЙ абстрактные фразы:
❌ "История встречается с будущим"
❌ "Пространство, созданное для вас"
❌ "Новый уровень комфорта"
❌ "Где мечты становятся реальностью"
❌ "Идеальное место для жизни"

ИСПОЛЬЗУЙ только конкретные УТП:
✅ "7 МИН. ДО СИТИ"
✅ "КЛЮЧИ СЕЙЧАС"
✅ "ПЛАТЁЖ 89 000 ₽/МЕС"
✅ "СКИДКА 15%"
✅ "ОТ 25 МЛН"
✅ "РАССРОЧКА 0%"
✅ "ПОСЛЕДНИЕ 5 КВАРТИР"
✅ "У ПАРКА 50 ГА"
✅ "ПЕРВЫЙ ВЗНОС ОТ 2,5 МЛН"

ВАЖНО: Если есть данные о первом взносе — пиши "ПЕРВЫЙ ВЗНОС", не сокращай до "ВЗНОС"

═══ ЧАСТЬ 2: ЛИДГЕН-ПОСТ ═══

СТРУКТУРА ПОСТА:

1. ЗАГОЛОВОК
[Эмодзи по контексту] + [Тип объекта] + [Главное УТП] + [Финансовый триггер]

Эмодзи по контексту объекта:
{emoji_section}

2. ЭМОЦИОНАЛЬНЫЙ ХУК (1-2 строки)
Связан с контекстом объекта. Примеры:
- У парка: "Для тех, кто не выбирает между городом и природой"
- Готовый дом: "Дом сдан — живые фото, а не рендеры"
- Низкий платёж: "Платёж меньше аренды, но квартира — ваша"
- У воды: "Комплекс как кусочек моря в сердце столицы"
- Инвестиция: "Потенциал роста — до +40%"

3. ЛОКАЦИЯ (📍)
Конкретика: "5 мин. до м. Деловой центр", "15 мин. до Сити", "Рядом парк 50 га"

4. ФИНАНСЫ (💰 или —)
Взнос, платёж, рассрочка, скидка. Сравнения: "меньше аренды", "низкий порог входа"

5. ФИШКИ (▪️)
Вводная: "А теперь — к фишкам ⬇️" или "Всё продумано до мелочей 👇"
▪️ Инфраструктура, уникальность, локация, выгода

6. CTA (⚪️)
⚪️ + Действие + «КЛЮЧЕВОЕ_СЛОВО» — [конкретный результат]
Ключевое слово = тип сделки (ИНВЕСТ, ГОТОВО, ПОКАЗ, СЕМЕЙНАЯ)

═══ ЗАПРЕТЫ ═══
- Канцелярит ("осуществить покупку")
- Абстракции ("мы лучшие", "высокое качество")
- Банальные CTA ("Звоните!", "Успейте!")
- Длинные предложения (более 2 строк)
- Эмодзи для украшения (только функционально)
- Название ЖК и девелопера в тексте"""

        # User-промпт
        parsed_section = ""
        if parsed_data:
            parsed_section = f"""

ДАННЫЕ С САЙТА (автоматический парсинг):
{parsed_data}"""

        user_prompt = f"""ДАННЫЕ ЛОТА (ручной ввод):
{user_input}
{parsed_section}

ПАРАМЕТРЫ ПУБЛИКАЦИИ:
📅 Дата: {pub_date} ({pub_weekday})
🎬 Формат: {format_display}
📢 Тип: {ad_type}

ЗАДАЧА:
Сгенерируй 3 ВАРИАНТА текстовых блоков для баннера.

Каждый вариант должен использовать РАЗНЫЙ главный триггер:
1. ВАРИАНТ "ФИНАНСЫ" — акцент на доступности (ПЕРВЫЙ ВЗНОС, рассрочка, платёж)
2. ВАРИАНТ "ЛОКАЦИЯ" — акцент на близости к метро/центру
3. ВАРИАНТ "ПРЕМИУМ" — акцент на уникальности (вид, терраса, ключи сразу)

ФОРМАТ ОТВЕТА (строго соблюдай):

📋 ТЗ ДЛЯ ДИЗАЙНЕРА

📅 Дата: {pub_date} ({pub_weekday})
🎬 Формат: {format_display}
📢 Тип: {ad_type}
🔗 Визуалы: {url if url else "[Взять у клиента]"}

═══════════════════════════════════════

🔥 ВАРИАНТ 1: ФИНАНСЫ

[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...

💡 Идея: [краткое объяснение за что зацепиться]

═══════════════════════════════════════

📍 ВАРИАНТ 2: ЛОКАЦИЯ

[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...

💡 Идея: [краткое объяснение за что зацепиться]

═══════════════════════════════════════

✨ ВАРИАНТ 3: ПРЕМИУМ

[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...

💡 Идея: [краткое объяснение за что зацепиться]

═══════════════════════════════════════

📝 ЛИДГЕН-ПОСТ

Напиши готовый пост для Telegram-канала.

ПРАВИЛА:
1. Заголовок: [Эмодзи по контексту объекта] + тип + УТП + финансы
2. Хук: связан с контекстом объекта (природа/готовность/инвестиция/семья)
3. Локация: 📍 мин. до метро + до Сити/центра/парка
4. Финансы: 💰 взнос, платёж (сравнение "меньше аренды")
5. Фишки: "А теперь — к фишкам ⬇️" + ▪️ списком
6. CTA: ⚪️ Напишите «СЛОВО» — [конкретный результат]

Формат: короткие абзацы, разговорный язык, конкретные цифры."""

        # Генерация через Claude
        brief = generate_content(system_prompt, user_prompt)

        # Двойная проверка УТП на "воду"
        brief = await validate_utp_text(brief)

        # Разделяем на ТЗ дизайнеру и текст поста
        max_length = 4000
        if "📝 ЛИДГЕН-ПОСТ" in brief:
            parts = brief.split("📝 ЛИДГЕН-ПОСТ")
            designer_brief = parts[0].strip()
            post_text = "📝 ЛИДГЕН-ПОСТ" + parts[1].strip()
        else:
            designer_brief = brief
            post_text = None

        # Получаем дизайнера клиента
        designer = get_client_designer(client_slug)

        # Отправляем ТЗ в чат дизайнеров (если настроен)
        if config.TEAM_CHAT_ID:
            try:
                bot: Bot = callback.message.bot
                designer_tag = f"👨‍🎨 {designer}\n" if designer else ""
                # Добавляем яркую пометку ДЛЯ ADS
                ads_tag = "📢 ДЛЯ TELEGRAM ADS\n" if is_for_ads else "📱 Только канал\n"
                designer_message = f"{ads_tag}{designer_tag}\n{designer_brief}"

                if len(designer_message) > max_length:
                    header = f"{ads_tag}{designer_tag}"
                    await bot.send_message(config.TEAM_CHAT_ID, header)
                    msg_parts = [designer_brief[i:i+max_length] for i in range(0, len(designer_brief), max_length)]
                    for part in msg_parts:
                        await bot.send_message(config.TEAM_CHAT_ID, part)
                else:
                    await bot.send_message(config.TEAM_CHAT_ID, designer_message)
            except Exception as chat_error:
                await callback.message.answer(f"⚠️ Не удалось отправить в рабочий чат: {chat_error}")

        # Добавляем в очередь брифов
        add_brief_to_queue({
            "date": pub_date,
            "weekday": pub_weekday,
            "format": content_format,
            "ad_type": ad_type,
            "url": url,
            "designer_brief": designer_brief[:500] if designer_brief else ""
        })

        # Отправляем текст поста оператору
        if post_text:
            if len(post_text) > max_length:
                msg_parts = [post_text[i:i+max_length] for i in range(0, len(post_text), max_length)]
                for part in msg_parts:
                    await callback.message.answer(part)
            else:
                await callback.message.answer(post_text)
            confirm_msg = f"✅ ТЗ отправлено дизайнеру {designer}" if designer else "✅ ТЗ отправлено"
            await callback.message.answer(confirm_msg)
        else:
            await callback.message.answer(brief)
            await callback.message.answer("✅ Готово")

    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка генерации: {str(e)}\n\n"
            "Проверь формат данных и попробуй снова."
        )

    await state.clear()


async def validate_utp_text(text: str) -> str:
    """
    Двойная проверка текста на 'воду' и литературщину.
    Если найдены абстракции — переписывает их.
    """
    # Паттерны плохих УТП
    bad_patterns = [
        "история встречается",
        "пространство для жизни",
        "новый уровень комфорта",
        "где мечты становятся",
        "идеальное место",
        "пространство, созданное для",
        "новый взгляд на",
        "лучший выбор для",
        "уникальная возможность",
        "эксклюзивное предложение"
    ]

    # Проверяем наличие плохих паттернов
    text_lower = text.lower()
    has_bad_patterns = any(pattern in text_lower for pattern in bad_patterns)

    if not has_bad_patterns:
        return text  # Всё ок, возвращаем как есть

    # Если есть проблемы — отправляем на переработку
    validation_prompt = """Проверь текст ТЗ для баннера недвижимости.

НАЙДИ И ЗАМЕНИ абстрактные фразы на конкретные УТП:

ПЛОХО (абстракции):
- "История встречается с будущим" → замени на конкретику про объект
- "Пространство для жизни" → замени на площадь или планировку
- "Новый уровень комфорта" → замени на конкретную фишку

ХОРОШО (конкретика):
- "7 МИН. ДО СИТИ"
- "КЛЮЧИ СЕЙЧАС"
- "ПЛАТЁЖ 89 000 ₽/МЕС"
- "СКИДКА 15%"

Верни исправленный текст. Сохрани всю структуру и форматирование."""

    try:
        corrected = generate_content(validation_prompt, f"Текст для проверки:\n\n{text}")
        return corrected
    except Exception:
        return text  # При ошибке возвращаем оригинал


async def cmd_live(message: types.Message, state: FSMContext):
    """Команда /live - подводка к Instagram-посту"""
    await message.answer(
        "📸 **Живой контент из Instagram**\n\n"
        "Отправь:\n"
        "• Ссылку на Instagram-пост\n"
        "• ИЛИ описание материала (тема, о чём говорится)\n\n"
        "Я напишу подводку в стиле клиента на основе контекста.",
        parse_mode="Markdown"
    )
    await state.set_state(ContentStates.waiting_for_live_link)


async def process_live_content(message: types.Message, state: FSMContext):
    """Обработка запроса на живой контент"""
    user_input = message.text
    data = await state.get_data()
    client_slug = data.get("current_client")
    if not client_slug:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    await message.answer("⏳ Пишу подводку к Instagram-материалу...")

    try:
        context = get_client_prompt(client_slug)

        # Получаем случайные вариации
        structure = get_random_instagram_structure()
        opener_example = get_random_instagram_opener()
        style = get_random_style_instruction()

        system_prompt = f"""{context}

Ты пишешь ПОДВОДКУ К INSTAGRAM-МАТЕРИАЛУ для Telegram-канала.

{structure}

ПРИМЕРЫ НАЧАЛА (для вдохновения):
"{opener_example}"

СТИЛЬ: {style}

ПРАВИЛА:
- Подводка должна интриговать, но не раскрывать всё
- Лёгкий, живой тон
- НЕ используй markdown
- Эмодзи для структуры
- Каждая подводка должна быть уникальной"""

        user_prompt = f"""Напиши подводку к Instagram-материалу:

{user_input}

Сделай пост готовым к публикации в Telegram."""

        post = generate_content(system_prompt, user_prompt)

        max_length = 4000
        if len(post) > max_length:
            parts = [post[i:i+max_length] for i in range(0, len(post), max_length)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(f"✅ Подводка готова:\n\n{post}")

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")

    await state.clear()


async def cmd_voice_intro(message: types.Message, state: FSMContext):
    """Команда /voice_intro - подводка к голосовому контенту"""
    await message.answer(
        "🎙 **Подводка к голосовому контенту**\n\n"
        "Отправь:\n"
        "• Транскрипцию голосового сообщения/подкаста\n"
        "• ИЛИ тему для сценария (если материал ещё не записан)\n\n"
        "**Workflow:**\n"
        "1️⃣ Если материал есть → транскрипция → подводка\n"
        "2️⃣ Если нет → сценарий для записи → потом подводка",
        parse_mode="Markdown"
    )
    await state.set_state(ContentStates.waiting_for_voice_topic)


async def process_voice_content(message: types.Message, state: FSMContext):
    """Обработка запроса на голосовой контент"""
    user_input = message.text
    data = await state.get_data()
    client_slug = data.get("current_client")
    if not client_slug:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    # Определяем тип запроса — транскрипция (длинный текст) или тема (короткий)
    is_transcription = len(user_input) > 200

    if is_transcription:
        await message.answer("⏳ Пишу подводку к голосовому на основе транскрипции...")
    else:
        await message.answer("⏳ Генерирую сценарий для записи голосового...")

    try:
        context = get_client_prompt(client_slug)

        if is_transcription:
            # Получаем случайные вариации
            structure = get_random_voice_structure()
            style = get_random_style_instruction()

            # Генерируем подводку к уже записанному голосовому
            system_prompt = f"""{context}

Ты пишешь ПОДВОДКУ К ГОЛОСОВОМУ СООБЩЕНИЮ для Telegram-канала.

{structure}

СТИЛЬ: {style}

ПРАВИЛА:
- Подводка должна заинтриговать
- Выдели ключевую мысль из транскрипции
- НЕ используй markdown
- Каждая подводка должна быть уникальной"""

            user_prompt = f"""На основе транскрипции голосового напиши подводку:

ТРАНСКРИПЦИЯ:
{user_input}

Сделай пост готовым к публикации."""

        else:
            # Генерируем сценарий для записи
            system_prompt = f"""{context}

Ты пишешь СЦЕНАРИЙ для записи голосового сообщения/подкаста брокером.

ФОРМАТ ВЫВОДА:
🎙 СЦЕНАРИЙ ГОЛОСОВОГО

📌 ТЕМА: [Название]

⏱ ХРОНОМЕТРАЖ: 1-2 минуты

📝 ТЕКСТ (что говорить):

[Начало — привлечь внимание]
...

[Основная часть — раскрыть тему]
...

[Финал — вывод + призыв]
...

💡 СОВЕТ: [Как подать]

ПРАВИЛА:
- Текст должен звучать естественно при озвучке
- Короткие предложения
- Конкретные примеры
- НЕ используй markdown"""

            user_prompt = f"""Напиши сценарий для голосового на тему:

{user_input}

Сделай сценарий готовым для записи."""

        result = generate_content(system_prompt, user_prompt)

        max_length = 4000
        if len(result) > max_length:
            parts = [result[i:i+max_length] for i in range(0, len(result), max_length)]
            for part in parts:
                await message.answer(part)
        else:
            prefix = "✅ Подводка готова" if is_transcription else "✅ Сценарий готов"
            await message.answer(f"{prefix}:\n\n{result}")

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")

    await state.clear()


async def cmd_add_channel(message: types.Message, state: FSMContext):
    """Команда /add_channel - добавить канал конкурента для парсинга"""
    # Парсим аргументы: /add_channel @channel_name client_slug
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if len(args) < 1:
        clients = list_clients()
        clients_list = ", ".join(clients) if clients else "нет клиентов"

        await message.answer(
            f"📡 Добавление канала для парсинга\n\n"
            f"Формат: /add_channel @channel_name client_slug\n\n"
            f"Пример: /add_channel @leaseandsale apple_real_estate\n\n"
            f"Доступные клиенты: {clients_list}"
        )
        return

    channel = args[0]

    # Если клиент не указан — используем первого
    if len(args) < 2:
        clients = list_clients()
        if len(clients) == 1:
            client_slug = clients[0]
        else:
            await message.answer(
                f"❌ Укажи клиента: /add_channel {channel} client_slug\n\n"
                f"Доступные клиенты: {', '.join(clients)}"
            )
            return
    else:
        client_slug = args[1].lower()

    # Проверяем клиента
    clients = list_clients()
    if client_slug not in clients:
        await message.answer(f"❌ Клиент '{client_slug}' не найден")
        return

    # Добавляем канал
    success = add_client_channel(client_slug, channel)

    if success:
        await message.answer(
            f"✅ Канал {channel} добавлен для {client_slug}\n\n"
            f"Он будет парситься при следующем запуске парсера."
        )
    else:
        await message.answer(f"⚠️ Канал {channel} уже добавлен для {client_slug}")


# =============================================================================
# КОМАНДА /post — ГЕНЕРАЦИЯ ПОСТОВ
# =============================================================================

async def cmd_post(message: types.Message, state: FSMContext):
    """Команда /post - генерация постов"""
    # Берём клиента из state (выбран ранее)
    data = await state.get_data()
    client_slug = data.get("current_client")

    if not client_slug:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    await state.update_data(client_slug=client_slug)

    # Формируем клавиатуру
    buttons = [
        [InlineKeyboardButton(text="🏢 Лидген-карточка", callback_data="post_leadgen")],
        [InlineKeyboardButton(text="📦 Лидген + карточки", callback_data="post_leadgen_cards")],
    ]

    # Кнопка "Пакет по лоту" — только при флаге
    if config.ENABLE_PACKAGE_BY_LOT:
        buttons.append([InlineKeyboardButton(text="📦 Пакет по лоту", callback_data="post_package_lot")])

    buttons.extend([
        [InlineKeyboardButton(text="🎠 Лидген-карусель (5-8)", callback_data="post_leadgen_carousel")],
        [InlineKeyboardButton(text="🔀 A/B баннер (2 варианта)", callback_data="post_leadgen_ab")],
        [InlineKeyboardButton(text="🎙 Пост с кружком", callback_data="post_circle")],
        [InlineKeyboardButton(text="📰 Дайджест", callback_data="post_digest")],
        [InlineKeyboardButton(text="📚 Экспертный контент", callback_data="post_expert")],
        [InlineKeyboardButton(text="😂 Мем", callback_data="post_meme")]
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "📝 Генерация поста\n\n"
        "Выбери формат:",
        reply_markup=keyboard
    )


async def callback_post_format(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата поста — сначала спрашиваем дату"""
    format_type = callback.data.replace("post_", "")
    await state.update_data(post_format=format_type)

    data = await state.get_data()
    client_slug = data.get("current_client") or data.get("client_slug")
    if not client_slug:
        await callback.message.answer("⚠️ Сначала выбери клиента")
        await callback.answer()
        return

    # Лидген + карточки — переход в отдельный handler
    if format_type == "leadgen_cards":
        from handlers.leadgen_cards_handler import cmd_leadgen_cards
        await cmd_leadgen_cards(callback.message, state)
        await callback.answer()
        return

    # Пакет по лоту — переход в отдельный handler
    if format_type == "package_lot":
        from handlers.package_lot_handler import cmd_package_by_lot
        await cmd_package_by_lot(callback.message, state)
        await callback.answer()
        return

    # Мемы — без выбора даты
    if format_type == "meme":
        await show_meme_references(callback, state)
        return

    # Для всех остальных форматов — сначала спрашиваем дату
    format_names = {
        "leadgen": "🏢 Лидген-карточка",
        "leadgen_carousel": "🎠 Лидген-карусель (5-8 карточек)",
        "leadgen_ab": "🔀 A/B баннер (2 варианта)",
        "circle": "🎙 Пост с кружком",
        "digest": "📰 Дайджест",
        "expert": "📚 Экспертный контент"
    }
    format_name = format_names.get(format_type, "Пост")

    await callback.message.edit_text(
        f"{format_name}\n\n"
        "📅 На какую дату нужен пост?",
        reply_markup=get_post_date_keyboard()
    )
    await callback.answer()


async def callback_post_date(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора даты публикации"""
    date_value = callback.data.replace("post_date_", "")

    if date_value == "today":
        post_date = datetime.now().strftime("%Y-%m-%d")
    elif date_value == "custom":
        await callback.message.edit_text(
            "📅 Введи дату в формате ДД.ММ или ДД.ММ.ГГГГ:"
        )
        await state.set_state(ContentStates.waiting_for_post_date)
        await callback.answer()
        return
    else:
        post_date = date_value  # Уже в формате YYYY-MM-DD

    await state.update_data(post_date=post_date)

    # Переходим к следующему шагу в зависимости от формата
    await show_post_input_step(callback.message, state, edit=True)
    await callback.answer()


async def process_post_date_input(message: types.Message, state: FSMContext):
    """Обработка ручного ввода даты"""
    date_text = message.text.strip()

    # Парсим дату
    try:
        if len(date_text.split(".")) == 2:
            # ДД.ММ
            day, month = date_text.split(".")
            year = datetime.now().year
            post_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            # ДД.ММ.ГГГГ
            day, month, year = date_text.split(".")
            if len(year) == 2:
                year = f"20{year}"
            post_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Проверяем валидность
        datetime.strptime(post_date, "%Y-%m-%d")
    except (ValueError, AttributeError):
        await message.answer("❌ Неверный формат. Введи дату как ДД.ММ или ДД.ММ.ГГГГ:")
        return

    await state.update_data(post_date=post_date)
    await show_post_input_step(message, state, edit=False)


async def show_post_input_step(message_or_callback, state: FSMContext, edit: bool = False):
    """Показать следующий шаг ввода в зависимости от формата"""
    data = await state.get_data()
    post_format = data.get("post_format")
    client_slug = data.get("current_client") or data.get("client_slug")
    post_date = data.get("post_date", "")

    # Форматируем дату для отображения
    try:
        date_obj = datetime.strptime(post_date, "%Y-%m-%d")
        date_display = date_obj.strftime("%d.%m")
    except:
        date_display = post_date

    if post_format == "leadgen":
        lots = get_client_lots(client_slug, status="READY_FOR_CONTENT")

        if lots:
            lots_text = "Выбери лот (напиши номер) или отправь ссылку на ЖК:\n\n"
            for i, lot in enumerate(lots, 1):
                lot_name = lot.get("lot_name", "Без названия")
                lots_text += f"{i}. {lot_name}\n"

            text = (
                f"🏢 Лидген-карточка на {date_display}\n\n"
                f"{lots_text}\n"
                "Или отправь ссылку на сайт ЖК — распаршу и сгенерирую пост."
            )
        else:
            text = (
                f"🏢 Лидген-карточка на {date_display}\n\n"
                "Лотов пока нет. Отправь ссылку на сайт ЖК — распаршу и сгенерирую пост."
            )
        await state.set_state(ContentStates.waiting_for_post_lot)

    elif post_format == "circle":
        text = (
            f"🎙 Пост с кружком на {date_display}\n\n"
            "Отправь тему или ключевые тезисы из кружка брокера.\n\n"
            "Если кружок ещё не записан — используй /circle для получения ТЗ."
        )
        await state.set_state(ContentStates.waiting_for_post_lot)

    elif post_format == "digest":
        text = (
            f"📰 Дайджест на {date_display}\n\n"
            "Напиши тему дайджеста или что включить:\n"
            "• Итоги недели\n"
            "• Тренды рынка\n"
            "• Подборка объектов\n"
            "• Ответы на частые вопросы"
        )
        await state.set_state(ContentStates.waiting_for_post_digest_topic)

    elif post_format == "expert":
        text = (
            f"📚 Экспертный контент на {date_display}\n\n"
            "Напиши тему для экспертного поста:\n"
            "• Советы покупателям\n"
            "• Разбор ошибок\n"
            "• Ответ на частый вопрос\n"
            "• Сравнение (аренда vs ипотека)\n\n"
            "Пример: \"5 ошибок при покупке первой квартиры\""
        )
        await state.set_state(ContentStates.waiting_for_post_lot)

    elif post_format == "leadgen_carousel":
        text = (
            f"🎠 Лидген-карусель на {date_display}\n\n"
            "Отправь данные объекта для карусели из 5-8 карточек:\n"
            "• Локация, цена, платёж\n"
            "• Преимущества (3-5 пунктов)\n"
            "• Инфраструктура\n"
            "• Условия покупки\n\n"
            "Можно отправить ссылку на сайт ЖК."
        )
        await state.set_state(ContentStates.waiting_for_post_lot)

    elif post_format == "leadgen_ab":
        text = (
            f"🔀 A/B баннер на {date_display}\n\n"
            "Отправь данные объекта для 2 вариантов баннера:\n"
            "• Вариант A — рациональный (цифры, выгода)\n"
            "• Вариант B — эмоциональный (образы, lifestyle)\n\n"
            "Отправь ссылку на ЖК или описание."
        )
        await state.set_state(ContentStates.waiting_for_post_lot)

    else:
        text = f"Пост на {date_display}\n\nОтправь данные для генерации."
        await state.set_state(ContentStates.waiting_for_post_lot)

    if edit and hasattr(message_or_callback, 'edit_text'):
        await message_or_callback.edit_text(text)
    else:
        await message_or_callback.answer(text)


def get_meme_references_keyboard(count: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора референса для мема"""
    buttons = []
    for i in range(1, count + 1):
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ Выбрать #{i}",
                callback_data=f"post_meme_select_{i}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔄 Другие", callback_data="post_meme_refresh"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="post_meme_cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_meme_references(callback: CallbackQuery, state: FSMContext):
    """Показать референсы для мема"""
    references = get_top_references(n=3, days=7)

    if not references:
        await callback.message.edit_text(
            "😢 Нет подходящих референсов для мемов.\n\n"
            "Парсер не собрал посты за последние 7 дней."
        )
        await callback.answer()
        return

    await state.update_data(meme_references=references)

    preview_lines = ["😂 *Выбери референс для мема:*\n"]
    for i, ref in enumerate(references, 1):
        preview_lines.append(format_reference_preview(ref, i))
        preview_lines.append("")

    await callback.message.edit_text(
        "\n".join(preview_lines),
        parse_mode="Markdown",
        reply_markup=get_meme_references_keyboard(len(references))
    )
    await callback.answer()


async def process_post_lot(message: types.Message, state: FSMContext):
    """Обработка ввода для генерации поста"""
    user_input = message.text
    data = await state.get_data()
    post_format = data.get("post_format", "leadgen")
    client_slug = data.get("current_client") or data.get("client_slug")

    await message.answer("⏳ Генерирую пост...")

    try:
        # Загружаем контекст клиента
        context = get_client_prompt(client_slug)

        # Определяем тип поста и формируем промпт
        if post_format == "leadgen":
            # Собираем данные из всех источников
            url = find_url_in_text(user_input)
            user_text = re.sub(r'https?://[^\s]+', '', user_input).strip()  # текст без URL
            lot_data_parts = []

            # 1. Текст пользователя — всегда в приоритете
            if user_text and not user_text.isdigit():
                lot_data_parts.append(f"ДАННЫЕ ОТ ПОЛЬЗОВАТЕЛЯ:\n{user_text}")

            # 2. Парсинг сайта (если есть URL)
            if url:
                parse_result = await parse_jk_website(url)
                if parse_result["parse_success"]:
                    parsed = format_parsed_data(parse_result)
                    if parsed.strip():
                        lot_data_parts.append(f"ДАННЫЕ С САЙТА:\n{parsed}")
                else:
                    # Сайт плохо парсится — ищем в интернете по названию из URL
                    domain_match = re.search(r'//(?:www\.)?([^/]+)', url)
                    if domain_match:
                        search_query = domain_match.group(1).replace('.ru', '').replace('.com', '').replace('-', ' ')
                        search_result = await search_jk_info(search_query)
                        if search_result:
                            lot_data_parts.append(search_result)
                        else:
                            lot_data_parts.append(f"[Сайт {url} не удалось распарсить, используй данные пользователя]")

            # 3. Номер лота из списка
            if user_text.isdigit():
                lots = get_client_lots(client_slug, status="READY_FOR_CONTENT")
                lot_index = int(user_text) - 1
                if 0 <= lot_index < len(lots):
                    lot = lots[lot_index]
                    lot_data_parts.append(f"""ДАННЫЕ ЛОТА:
Название: {lot.get('lot_name', 'Не указано')}
Цена: {lot.get('price', 'Не указана')}
Первый взнос: {lot.get('downpayment', 'Не указан')}
Платёж в месяц: {lot.get('monthly_payment', 'Не указан')}
Локация: {lot.get('location', 'Не указана')}
Особенности: {lot.get('features', 'Не указаны')}""")

            # Объединяем все данные
            lot_data = "\n\n".join(lot_data_parts) if lot_data_parts else user_input

            # Определяем тип лота (инвестиции/коммерция или жилая)
            is_investment = detect_investment_lot(lot_data)

            # Получаем случайные вариации
            structure = get_random_leadgen_structure(is_investment)
            hook_example = get_random_leadgen_hook(is_investment)
            style = get_random_style_instruction()

            # Разные правила для разных типов
            if is_investment:
                lot_type = "ИНВЕСТИЦИОННУЮ КАРТОЧКУ (коммерция/офисы)"
                rules = """ПРАВИЛА:
- НЕ используй markdown (звёздочки, подчёркивания)
- ЗАПРЕЩЕНО указывать название ЖК, девелопера, застройщика — используй "Проект", "Комплекс", "БЦ у метро"
- Акцент на доходность, окупаемость, финансовые условия
- Укажи расчётную доходность если есть данные
- Используй термины: резиденты, арендаторы, порог входа, пассивный доход
- Локация с акцентом на деловую инфраструктуру (БЦ, ТЦ, МЦК)
- CTA с акцентом на условия/бронь

ЗАПРЕЩЁННО КАТЕГОРИЧЕСКИ (КЛИШЕ):
❌ "История встречается с будущим"
❌ "Пространство, созданное для вас"
❌ Философские размышления без цифр
❌ "Премиум-класс" без конкретики

ОБЯЗАТЕЛЬНО:
✅ Точный % доходности (не "хорошая доходность")
✅ Точный размер инвестиций и схема платежа
✅ Конкретная локация (БЦ у какого метро, какие компании рядом)
✅ Реальные факты (спрос арендаторов, потенциал района)
СТИЛЬ: Профессиональный, как инвестиционный консультант, только цифры и факты."""
            else:
                lot_type = "ЛИДГЕН-КАРТОЧКУ для Telegram-канала"
                rules = """ПРАВИЛА:
- НЕ используй markdown (звёздочки, подчёркивания)
- ЗАПРЕЩЕНО указывать название ЖК, девелопера, застройщика — используй "Жилой комплекс", "Проект", "Комплекс у парка"
- Короткие абзацы (1-2 строки)
- Конкретные цифры
- CTA с тематическим ключевым словом

ЗАПРЕЩЁННО КАТЕГОРИЧЕСКИ (КЛИШЕ):
❌ "Представьте..." (перегруженные лирические вступления)
❌ "История встречается с будущим"
❌ "Пространство, созданное для вас"
❌ "Вот такую штуку..." (типичное клише)
❌ "Красивая/комфортная жизнь" без примеров
❌ "Идеально подойдёт для" (нужны КОНКРЕТНЫЕ причины!)
❌ Размывание первого взноса ("от X") без точной суммы

ПРИМЕРЫ ПРАВИЛЬНОГО КОНТЕНТА:
✅ Вместо "Терраса с видом на речные панорамы" → конкретно: "Терраса 40м² с видом на Москву-реку"
✅ Вместо "Выгодные условия" → конкретно: "Платёж 89 тыс./мес, первый взнос 2,5 млн, ключи в день покупки"
✅ Вместо "Близко к метро" → конкретно: "7 мин пешком до метро" или "100м от Третьего кольца"
✅ Вместо философии → факты: "Подземный паркинг, фитнес, детский сад"

СТИЛЬ: Острый, практичный. Как опытный брокер рассказывает коллеге о квартире, не красивые слова."""

            # Получаем требования к стилю клиента
            style_section = get_style_prompt_section(client_slug)
            length_req = get_post_length_requirements(client_slug)

            system_prompt = f"""{context}

Ты пишешь {lot_type}.

ВАЖНО О СТРУКТУРЕ:
- Используй ИМЕННО ЭТУ структуру (не из ToV, там только пример):
{structure}

ПРИМЕРЫ ХУКОВ (для вдохновения, НЕ КОПИРУЙ дословно — придумай свой):
"{hook_example}"

СТИЛЬ: {style}

{rules}
- КАЖДЫЙ пост должен быть УНИКАЛЬНЫМ — другая структура, другие формулировки
- НЕ копируй примеры из ToV дословно — бери только стиль и тон

{style_section}"""

            user_prompt = f"""Напиши лидген-карточку на основе данных:

{lot_data}

КРИТИЧЕСКИ ВАЖНО:
- Используй ТОЛЬКО данные выше. НЕ ВЫДУМЫВАЙ локации, метро, районы, цены.
- ДАННЫЕ ОТ ПОЛЬЗОВАТЕЛЯ имеют ВЫСШИЙ ПРИОРИТЕТ — это точная информация.
- Название ЖК и застройщика — служебная информация. В посте их указывать ЗАПРЕЩЕНО.
- Используй общие формулировки: "Жилой комплекс", "Проект", "Комплекс у парка".
- Пост должен быть НЕ КОРОЧЕ {length_req.get('min_words', 80)} слов.

Сделай пост готовым к публикации в Telegram."""

        elif post_format == "circle":
            # Получаем случайные вариации
            structure = get_random_circle_structure()
            opener_example = get_random_circle_opener()
            style = get_random_style_instruction()

            system_prompt = f"""{context}

Ты пишешь ПОДВОДКУ К КРУЖКУ от брокера для Telegram-канала.

{structure}

ПРИМЕРЫ НАЧАЛА (для вдохновения):
"{opener_example}"

СТИЛЬ: {style}

ПРАВИЛА:
- Подводка должна заинтриговать
- Не раскрывай всё содержание — только затравку
- НЕ используй markdown
- Каждая подводка должна быть уникальной"""

            user_prompt = f"""Напиши подводку к кружку брокера на тему:

{user_input}

Сделай пост готовым к публикации."""

        elif post_format == "expert":
            # Получаем случайные вариации
            structure = get_random_expert_structure()
            opener_example = get_random_expert_opener()
            style = get_random_style_instruction()

            system_prompt = f"""{context}

Ты пишешь ЭКСПЕРТНЫЙ ПОСТ для Telegram-канала.

{structure}

ПРИМЕРЫ ЗАГОЛОВКОВ (для вдохновения):
"{opener_example}"

СТИЛЬ: {style}

ПРАВИЛА:
- 3-5 пунктов максимум
- Конкретные примеры
- НЕ используй markdown
- Разговорный стиль с экспертизой
- Каждый пост должен быть уникальным по структуре"""

            user_prompt = f"""Напиши экспертный пост на тему:

{user_input}

Сделай пост готовым к публикации."""

        elif post_format == "leadgen_carousel":
            # Лидген-карусель 5-8 карточек
            style_section = get_style_prompt_section(client_slug)

            system_prompt = f"""{context}

Ты создаёшь ЛИДГЕН-КАРУСЕЛЬ из 5-8 карточек для Telegram.

СТРУКТУРА КАРУСЕЛИ:
1. КАРТОЧКА-ХУК: Проблема/вопрос ЦА (зацепить внимание)
2. КАРТОЧКА-ПРОБЛЕМА: Усиление боли (почему это важно)
3. КАРТОЧКА-РЕШЕНИЕ: Как этот объект решает проблему
4. КАРТОЧКА-КЕЙС: Цифры/факты/социальное доказательство
5. КАРТОЧКА-ОФФЕР: Условия покупки (цена, платёж, взнос)
6. КАРТОЧКА-CTA: Призыв к действию

ФОРМАТ ОТВЕТА:
Для каждой карточки укажи:
📌 КАРТОЧКА N — [НАЗВАНИЕ]
[ТЕКСТ НА КАРТОЧКЕ]: короткий, 1-3 строки
[ВИЗУАЛ]: что показать на фоне
---

ТЕКСТ ПОСТА (подводка к карусели):
[3-5 строк — интрига, зачем листать]

ПРАВИЛА:
- НЕ используй markdown
- ЗАПРЕЩЕНО название ЖК и застройщика
- Каждая карточка — самодостаточная мысль
- Стрелки → между карточками подразумеваются

{style_section}"""

            user_prompt = f"""Создай лидген-карусель на основе данных:

{user_input}

Сделай 6-8 карточек + текст поста."""

        elif post_format == "leadgen_ab":
            # A/B баннер — 2 варианта
            style_section = get_style_prompt_section(client_slug)

            system_prompt = f"""{context}

Ты создаёшь A/B БАННЕР — 2 варианта одного оффера для тестирования.

ВАРИАНТ A — РАЦИОНАЛЬНЫЙ:
- Акцент на цифрах: цена, платёж, экономия
- Логические аргументы
- Факты и сравнения

ВАРИАНТ B — ЭМОЦИОНАЛЬНЫЙ:
- Акцент на образах: lifestyle, статус, комфорт
- Эмоциональные триггеры
- Истории и сценарии

ФОРМАТ ОТВЕТА:

🔵 ВАРИАНТ A: РАЦИОНАЛЬНЫЙ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...
💡 Идея: почему это сработает

═══════════════════════════════════════

🟠 ВАРИАНТ B: ЭМОЦИОНАЛЬНЫЙ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...
💡 Идея: почему это сработает

═══════════════════════════════════════

ТЕКСТ ПОСТА (общий):
[Пост для обоих баннеров]

ПРАВИЛА:
- НЕ используй markdown
- ЗАПРЕЩЕНО название ЖК
- Варианты должны быть ПРИНЦИПИАЛЬНО разными по подходу

{style_section}"""

            user_prompt = f"""Создай A/B баннер на основе данных:

{user_input}

Сделай 2 контрастных варианта + текст поста."""

        else:
            # Дайджест обрабатывается отдельно
            await state.clear()
            return

        # Генерация через Claude С ПАМЯТЬЮ
        post = generate_content_with_memory(client_slug, system_prompt, user_prompt)

        # Валидация и автоисправление поста
        post = fix_post_issues(post, client_slug)
        validation = validate_post(post, client_slug)

        # Извлекаем метаданные из поста
        metadata = extract_metadata_from_post(post)

        # Сохраняем в журнал с метаданными
        format_map = {
            "leadgen": "lidgen",
            "leadgen_carousel": "lidgen_carousel",
            "leadgen_ab": "lidgen_ab",
            "circle": "circle",
            "expert": "expert"
        }
        journal_format = format_map.get(post_format, post_format)
        # Используем выбранную дату или сегодня
        post_date = data.get("post_date") or datetime.now().strftime("%Y-%m-%d")
        add_journal_entry(
            client_slug=client_slug,
            date=post_date,
            format_type=journal_format,
            text=post,
            status="planned" if post_date > datetime.now().strftime("%Y-%m-%d") else "published",
            source="bot_generated",
            hook_type=metadata.get("hook_type"),
            angle=metadata.get("angle"),
            cta=metadata.get("cta")
        )

        # Сохраняем пост в state для возможного редактирования
        await state.update_data(
            generated_post=post,
            post_system_prompt=system_prompt,
            post_user_prompt=user_prompt
        )

        # Формируем статус валидации
        validation_status = ""
        if not validation["valid"]:
            issues_text = "\n".join([f"⚠️ {i}" for i in validation["issues"]])
            validation_status = f"\n\n---\n{issues_text}"

        word_info = f"📊 {validation['word_count']} слов"

        # Отправляем результат с кнопками
        max_length = 3500  # Меньше, чтобы влезли кнопки
        if len(post) > max_length:
            parts = [post[i:i+max_length] for i in range(0, len(post), max_length)]
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    await message.answer(f"{part}\n\n{word_info}{validation_status}", reply_markup=get_post_edit_keyboard())
                else:
                    await message.answer(part)
        else:
            await message.answer(
                f"✅ Пост готов:\n\n{post}\n\n{word_info}{validation_status}",
                reply_markup=get_post_edit_keyboard()
            )

    except Exception as e:
        error_msg = str(e).replace("_", "\\_").replace("*", "\\*")
        await message.answer(f"❌ Ошибка генерации: {error_msg}")
        await state.clear()


async def process_post_digest(message: types.Message, state: FSMContext):
    """Обработка генерации дайджеста"""
    user_input = message.text
    data = await state.get_data()
    client_slug = data.get("current_client") or data.get("client_slug")

    await message.answer("⏳ Генерирую дайджест...")

    try:
        context = get_client_prompt(client_slug)

        system_prompt = f"""{context}

Ты пишешь ДАЙДЖЕСТ для Telegram-канала (выходной/лёгкий контент).

СТРУКТУРА:
1. Эмодзи + Заголовок (📰 Дайджест недели / 🔥 Топ-3 новости)
2. Краткое вступление
3. 3-5 пунктов с информацией
4. Лёгкий CTA или вопрос для вовлечения

ПРАВИЛА:
- Лёгкий, читабельный формат
- Без агрессивных продаж
- НЕ используй markdown
- Можно использовать эмодзи для структуры"""

        user_prompt = f"""Напиши дайджест на тему:

{user_input}

Сделай пост готовым к публикации."""

        post = generate_content(system_prompt, user_prompt)

        # Сохраняем в журнал с выбранной датой
        post_date = data.get("post_date") or datetime.now().strftime("%Y-%m-%d")
        add_journal_entry(
            client_slug=client_slug,
            date=post_date,
            format_type="digest",
            text=post,
            status="planned" if post_date > datetime.now().strftime("%Y-%m-%d") else "published",
            source="bot_generated"
        )

        max_length = 4000
        if len(post) > max_length:
            parts = [post[i:i+max_length] for i in range(0, len(post), max_length)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(f"✅ Дайджест готов (сохранён в журнал):\n\n{post}")

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")

    await state.clear()


# =============================================================================
# МЕМ ИЗ МЕНЮ /post
# =============================================================================

async def callback_post_meme_select(callback: CallbackQuery, state: FSMContext):
    """Выбор референса для мема из меню /post"""
    data = await state.get_data()
    client = data.get("current_client") or data.get("client_slug")
    references = data.get("meme_references", [])

    index = int(callback.data.replace("post_meme_select_", ""))
    reference = get_reference_by_index(references, index)

    if not reference:
        await callback.answer("Референс не найден")
        return

    await callback.answer("Генерирую мем...")

    # Генерируем мем
    from utils.client_context import load_client_context
    client_context = load_client_context(client)

    system_prompt = f"""Ты — креативный SMM-специалист агентства недвижимости.
Адаптируй популярный мем под тематику недвижимости.

КОНТЕКСТ: {get_client_prompt(client)}

СТИЛЬ:
- Ироничный, но не токсичный
- Связь с болями ЦА (выбор, ипотека, ожидание/реальность)
- Короткий текст (до 200 символов)
- Без прямой рекламы"""

    user_prompt = f"""РЕФЕРЕНС:
{reference.get('text', '')}

Источник: @{reference.get('channel', 'unknown')}

---

ФОРМАТ ОТВЕТА:

МЕМНЫЙ ПОСТ
[Текст поста — до 200 символов]

---

ТЗ ДИЗАЙНЕРУ

ИДЕЯ: [концепция в 1-2 предложения]
ТЕКСТ НА КАРТИНКЕ: [если нужен]
ВИЗУАЛ: [что изобразить]
РЕФЕРЕНС: https://t.me/{reference.get('channel', '')}/{reference.get('message_id', '')}"""

    try:
        meme_content = generate_content(system_prompt, user_prompt)

        await state.update_data(generated_meme=meme_content, meme_reference=reference)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💾 Сохранить", callback_data="post_meme_save"),
                InlineKeyboardButton(text="🔄 Другой", callback_data="post_meme_refresh"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_meme_cancel")]
        ])

        await callback.message.edit_text(
            f"😂 *Мем готов!*\n\n{meme_content}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    except Exception as e:
        await callback.message.edit_text(f"Ошибка генерации: {str(e)}")


async def callback_post_meme_save(callback: CallbackQuery, state: FSMContext):
    """Сохранение мема в журнал"""
    data = await state.get_data()
    client = data.get("current_client") or data.get("client_slug")
    meme_content = data.get("generated_meme", "")

    if not meme_content:
        await callback.answer("Нет мема для сохранения")
        return

    add_journal_entry(
        client_slug=client,
        date=datetime.now().strftime("%Y-%m-%d"),
        format_type="meme",
        text=meme_content,
        status="published",
        source="bot_generated"
    )

    await callback.message.edit_text(
        f"✅ *Мем сохранён в журнал!*\n\n{meme_content}",
        parse_mode="Markdown"
    )
    await callback.answer("Сохранено!")


async def callback_post_meme_refresh(callback: CallbackQuery, state: FSMContext):
    """Обновить референсы"""
    references = get_top_references(n=3, days=14)

    if not references:
        await callback.answer("Нет других референсов")
        return

    await state.update_data(meme_references=references)

    preview_lines = ["😂 *Выбери референс для мема:*\n"]
    for i, ref in enumerate(references, 1):
        preview_lines.append(format_reference_preview(ref, i))
        preview_lines.append("")

    await callback.message.edit_text(
        "\n".join(preview_lines),
        parse_mode="Markdown",
        reply_markup=get_meme_references_keyboard(len(references))
    )
    await callback.answer()


async def callback_post_meme_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена мема"""
    await callback.message.edit_text("Отменено")
    await callback.answer()


# =============================================================================
# КОМАНДА /circle — ТЗ ДЛЯ ЗАПИСИ КРУГОВ
# =============================================================================

async def cmd_circle(message: types.Message, state: FSMContext):
    """Команда /circle - ТЗ для брокера на запись кружка"""
    clients = list_clients()

    if not clients:
        await message.answer("❌ Нет клиентов. Создай клиента через /newclient")
        return

    client_slug = clients[0]
    await state.update_data(client_slug=client_slug)

    # Получаем лоты
    lots = get_client_lots(client_slug, status="READY_FOR_CONTENT")

    if lots:
        lots_info = "На основе лотов:\n"
        for lot in lots[:3]:  # Берём до 3 лотов
            lots_info += f"• {lot.get('lot_name', 'Без названия')}\n"
        lots_info += "\n"
    else:
        lots_info = ""

    await message.answer(
        f"🎙 ТЗ для записи кружка\n\n"
        f"{lots_info}"
        f"Напиши тему или выбери из предложенных:\n"
        f"• Почему сейчас лучшее время для покупки\n"
        f"• Как выбрать квартиру для семьи\n"
        f"• Частая ошибка покупателей\n"
        f"• Кейс недавней сделки\n\n"
        f"Или просто напиши свою тему."
    )
    await state.set_state(ContentStates.waiting_for_circle_topic)


async def process_circle_topic(message: types.Message, state: FSMContext):
    """Обработка генерации ТЗ для кружка"""
    user_input = message.text
    data = await state.get_data()
    client_slug = data.get("current_client") or data.get("client_slug")

    await message.answer("⏳ Генерирую ТЗ для брокера...")

    try:
        context = get_client_prompt(client_slug)
        lots = get_client_lots(client_slug, status="READY_FOR_CONTENT")

        lots_info = ""
        if lots:
            lots_info = "ДОСТУПНЫЕ ЛОТЫ:\n"
            for lot in lots[:3]:
                lots_info += f"- {lot.get('lot_name', '')}: {lot.get('price', '')} | {lot.get('location', '')}\n"

        system_prompt = f"""{context}

Ты составляешь ТЗ для брокера на запись голосового кружка в Telegram.

ФОРМАТ ВЫВОДА:
🎙 ТЗ ДЛЯ КРУЖКА

📌 ТЕМА: [Название темы]

🎯 ЦЕЛЬ: [Что должен понять зритель]

📝 ТЕЗИСЫ (о чём говорить):
1. [Первый тезис]
2. [Второй тезис]
3. [Третий тезис]
4. [Четвёртый тезис]
5. [Пятый тезис]

⏱ ХРОНОМЕТРАЖ: 30-60 секунд

💡 СОВЕТ: [Как подать материал]

ПРАВИЛА:
- Тезисы должны быть конкретными, не абстрактными
- Брокер говорит своими словами, не читает
- Если есть подходящий лот — привязать к нему
- НЕ используй markdown"""

        user_prompt = f"""Составь ТЗ для брокера на запись кружка.

ТЕМА: {user_input}

{lots_info}

Сделай ТЗ готовым для пересылки брокеру в Telegram."""

        tz = generate_content(system_prompt, user_prompt)

        await message.answer(f"✅ ТЗ готово (можно переслать брокеру):\n\n{tz}")

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")

    await state.clear()


# =============================================================================
# РЕДАКТИРОВАНИЕ СГЕНЕРИРОВАННОГО ПОСТА
# =============================================================================

async def callback_post_regen(callback: CallbackQuery, state: FSMContext):
    """Перегенерировать пост с теми же параметрами"""
    data = await state.get_data()
    system_prompt = data.get("post_system_prompt")
    user_prompt = data.get("post_user_prompt")
    client_slug = data.get("current_client") or data.get("client_slug")

    if not system_prompt or not user_prompt:
        await callback.answer("Данные потеряны, начни заново")
        return

    await callback.message.edit_text("⏳ Перегенерирую пост...")
    await callback.answer()

    try:
        post = generate_content(system_prompt, user_prompt)

        await state.update_data(generated_post=post)

        max_length = 3500
        if len(post) > max_length:
            await callback.message.edit_text(post[:max_length])
            await callback.message.answer(
                post[max_length:],
                reply_markup=get_post_edit_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"✅ Пост готов:\n\n{post}",
                reply_markup=get_post_edit_keyboard()
            )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")


async def callback_post_edit_request(callback: CallbackQuery, state: FSMContext):
    """Запросить изменения в посте"""
    await callback.message.answer(
        "✏️ Напиши, что изменить в посте:\n\n"
        "Примеры:\n"
        "• Сделай короче\n"
        "• Добавь цену 25 млн\n"
        "• Убери про ипотеку\n"
        "• Сделай более дерзким"
    )
    await state.set_state(ContentStates.waiting_for_post_edit)
    await callback.answer()


async def process_post_edit(message: types.Message, state: FSMContext):
    """Обработка инструкции по редактированию поста"""
    edit_instruction = message.text
    data = await state.get_data()

    original_post = data.get("generated_post")
    client_slug = data.get("current_client") or data.get("client_slug")

    if not original_post:
        await message.answer("❌ Пост потерян, начни заново")
        await state.clear()
        return

    await message.answer("⏳ Редактирую пост...")

    try:
        context = get_client_prompt(client_slug) if client_slug else ""

        system_prompt = f"""{context}

Ты редактор постов. Твоя задача — изменить пост согласно инструкции пользователя.
Сохраняй общий стиль и tone of voice.
НЕ используй markdown в итоговом тексте."""

        user_prompt = f"""ОРИГИНАЛЬНЫЙ ПОСТ:
{original_post}

ИНСТРУКЦИЯ ПО ИЗМЕНЕНИЮ:
{edit_instruction}

Выдай ТОЛЬКО отредактированный пост, без комментариев."""

        edited_post = generate_content(system_prompt, user_prompt)

        await state.update_data(generated_post=edited_post)
        await state.set_state(None)

        max_length = 3500
        if len(edited_post) > max_length:
            await message.answer(edited_post[:max_length])
            await message.answer(
                edited_post[max_length:],
                reply_markup=get_post_edit_keyboard()
            )
        else:
            await message.answer(
                f"✅ Пост отредактирован:\n\n{edited_post}",
                reply_markup=get_post_edit_keyboard()
            )

    except Exception as e:
        await message.answer(f"❌ Ошибка редактирования: {str(e)}")
        await state.set_state(None)


async def callback_post_harder(callback: CallbackQuery, state: FSMContext):
    """Сделать пост жёстче (редакторский проход)"""
    data = await state.get_data()
    post = data.get("generated_post", "")

    if not post:
        await callback.answer("Пост не найден")
        return

    await callback.answer("Делаю жёстче...")
    await callback.message.edit_text("⏳ Редактирую — делаю жёстче...")

    try:
        harder_post = editor_pass(post, direction="harder")
        await state.update_data(generated_post=harder_post)

        max_length = 3500
        if len(harder_post) > max_length:
            await callback.message.edit_text(harder_post[:max_length])
            await callback.message.answer(
                harder_post[max_length:],
                reply_markup=get_post_edit_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"💪 Пост стал жёстче:\n\n{harder_post}",
                reply_markup=get_post_edit_keyboard()
            )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")


async def callback_post_softer(callback: CallbackQuery, state: FSMContext):
    """Сделать пост мягче (редакторский проход)"""
    data = await state.get_data()
    post = data.get("generated_post", "")

    if not post:
        await callback.answer("Пост не найден")
        return

    await callback.answer("Делаю мягче...")
    await callback.message.edit_text("⏳ Редактирую — делаю мягче...")

    try:
        softer_post = editor_pass(post, direction="softer")
        await state.update_data(generated_post=softer_post)

        max_length = 3500
        if len(softer_post) > max_length:
            await callback.message.edit_text(softer_post[:max_length])
            await callback.message.answer(
                softer_post[max_length:],
                reply_markup=get_post_edit_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"🌸 Пост стал мягче:\n\n{softer_post}",
                reply_markup=get_post_edit_keyboard()
            )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")


async def callback_post_copy(callback: CallbackQuery, state: FSMContext):
    """Скопировать пост (просто подтверждение)"""
    data = await state.get_data()
    post = data.get("generated_post", "")

    if post:
        # Отправляем пост без форматирования для удобного копирования
        await callback.message.answer(post)
        await callback.answer("Пост отправлен для копирования")
    else:
        await callback.answer("Пост не найден")


def get_post_brief_keyboard(is_compact: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура согласования ТЗ из поста"""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Согласовать", callback_data="post_brief_approve"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_brief_edit")
        ]
    ]

    # Кнопка развернуть/свернуть
    if is_compact:
        buttons.append([InlineKeyboardButton(text="📖 Развернуть ТЗ", callback_data="post_brief_expand")])
    else:
        buttons.append([InlineKeyboardButton(text="📝 Короткое ТЗ", callback_data="post_brief_compact")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад к посту", callback_data="post_brief_back")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_brief_format_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора формата ТЗ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Баннер (1 картинка)", callback_data="brief_format_banner")],
        [InlineKeyboardButton(text="🎬 ГИФ-слайдер (2-3 слайда)", callback_data="brief_format_slider")],
        [InlineKeyboardButton(text="📑 Галерея (4-5 карточек)", callback_data="brief_format_gallery")],
        [InlineKeyboardButton(text="🎠 Карусель (5-8 карточек)", callback_data="brief_format_carousel")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="brief_format_back")]
    ])


async def callback_post_brief(callback: CallbackQuery, state: FSMContext):
    """Выбор формата ТЗ дизайнеру через post_actions"""
    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")

    if not post:
        await callback.answer("Пост не найден")
        return

    if not client_slug:
        await callback.answer("Сначала выбери клиента")
        return

    await callback.answer()

    # Используем клавиатуру из post_actions
    await callback.message.edit_text(
        "🎨 Выбери формат дизайна:\n\n"
        "📱 **Баннер** — 1 статичная картинка\n"
        "🎬 **ГИФ-слайдер** — анимация 2-3 слайдов\n"
        "📑 **Галерея** — карусель 4-5 карточек\n"
        "🎠 **Карусель** — лидген 5-8 карточек\n\n"
        "💡 **Компактное ТЗ** — короткое (800-1200 символов)\n"
        "📋 **Подробное ТЗ** — развернутое с примерами",
        reply_markup=get_design_type_keyboard(),
        parse_mode="Markdown"
    )


def get_brief_prompts(format_type: str, emoji_section: str) -> tuple[str, str]:
    """Получить system_prompt и user_prompt для формата ТЗ"""

    if format_type == "banner":
        system_prompt = f"""Ты — копирайтер. Создаёшь ТЗ для дизайнеров баннеров Telegram.

ФОРМАТ: СТАТИЧНЫЙ БАННЕР (1 картинка)

ТЕКСТОВЫЕ БЛОКИ:
[ПЛАШКА 1] — Локация/Срочность (формула: [ВРЕМЯ] ДО [МЕСТО] или [СТАТУС])
[ПЛАШКА 2] — Дополнительный триггер (уникальная фишка в 2-3 словах)
[ЗАГОЛОВОК] — Основная выгода (тип объекта + главное УТП)

ПРАВИЛА:
- Генерируй ТОЛЬКО текстовые блоки (визуалы дизайнер берёт с сайта)
- НЕ указывай название ЖК и девелопера
- НЕ указывай размеры в пикселях
- Текст плашек: UPPERCASE, 2-4 слова
- Время до метро: "мин." (не "минут")
- Если есть данные о первом взносе — пиши "ПЕРВЫЙ ВЗНОС", не сокращай

ЗАПРЕЩЕНО (вода):
❌ "История встречается с будущим"
❌ "Пространство, созданное для вас"

ИСПОЛЬЗУЙ конкретные УТП:
✅ "7 МИН. ДО СИТИ"
✅ "КЛЮЧИ СЕЙЧАС"
✅ "ПЕРВЫЙ ВЗНОС ОТ 2,5 МЛН"

Эмодзи клиента:
{emoji_section}"""

        user_prompt_template = """ТЕКСТ ПОСТА:
{post}

ЗАДАЧА:
Сгенерируй 3 ВАРИАНТА текстовых блоков для БАННЕРА (1 картинка).

Каждый вариант — РАЗНЫЙ триггер:
1. ВАРИАНТ "ФИНАНСЫ" — акцент на доступности
2. ВАРИАНТ "ЛОКАЦИЯ" — акцент на близости к метро/центру
3. ВАРИАНТ "ПРЕМИУМ" — акцент на уникальности

ФОРМАТ ОТВЕТА:

📋 ТЗ ДЛЯ ДИЗАЙНЕРА
🖼 Формат: Баннер (1 картинка)

═══════════════════════════════════════

🔥 ВАРИАНТ 1: ФИНАНСЫ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...
💡 Идея: [краткое объяснение]

═══════════════════════════════════════

📍 ВАРИАНТ 2: ЛОКАЦИЯ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...
💡 Идея: [краткое объяснение]

═══════════════════════════════════════

✨ ВАРИАНТ 3: ПРЕМИУМ
[ПЛАШКА 1]: ...
[ПЛАШКА 2]: ...
[ЗАГОЛОВОК]: ...
💡 Идея: [краткое объяснение]"""

    elif format_type == "slider":
        system_prompt = f"""Ты — копирайтер. Создаёшь ТЗ для дизайнеров ГИФ-слайдеров Telegram.

ФОРМАТ: ГИФ-СЛАЙДЕР (анимация 2-3 кадров)

СТРУКТУРА СЛАЙДЕРА:
- СЛАЙД 1: Хук/интрига (крупный текст, цепляет внимание)
- СЛАЙД 2: Раскрытие УТП (детали предложения)
- СЛАЙД 3 (опционально): CTA или финальный оффер

ПРАВИЛА:
- Каждый слайд — отдельный смысловой блок
- Текст на слайде: 1-2 строки максимум
- Анимация должна "рассказывать историю"
- НЕ указывай название ЖК и девелопера
- Время до метро: "мин." (не "минут")

ЗАПРЕЩЕНО (вода):
❌ Абстрактные фразы
❌ Длинные тексты на слайдах

Эмодзи клиента:
{emoji_section}"""

        user_prompt_template = """ТЕКСТ ПОСТА:
{post}

ЗАДАЧА:
Сгенерируй 2 ВАРИАНТА ТЗ для ГИФ-СЛАЙДЕРА (анимация 2-3 кадров).

ФОРМАТ ОТВЕТА:

📋 ТЗ ДЛЯ ДИЗАЙНЕРА
🎬 Формат: ГИФ-слайдер (2-3 кадра)

═══════════════════════════════════════

🔥 ВАРИАНТ 1

СЛАЙД 1 (хук):
[ТЕКСТ]: ...
[ВИЗУАЛ]: краткое описание

СЛАЙД 2 (раскрытие):
[ТЕКСТ]: ...
[ВИЗУАЛ]: краткое описание

СЛАЙД 3 (оффер):
[ТЕКСТ]: ...
[ВИЗУАЛ]: краткое описание

💡 Идея анимации: [как слайды связаны]

═══════════════════════════════════════

📍 ВАРИАНТ 2

СЛАЙД 1 (хук):
[ТЕКСТ]: ...
[ВИЗУАЛ]: краткое описание

СЛАЙД 2 (раскрытие):
[ТЕКСТ]: ...
[ВИЗУАЛ]: краткое описание

СЛАЙД 3 (оффер):
[ТЕКСТ]: ...
[ВИЗУАЛ]: краткое описание

💡 Идея анимации: [как слайды связаны]"""

    else:  # gallery
        system_prompt = f"""Ты — копирайтер. Создаёшь ТЗ для дизайнеров галерей/каруселей Telegram.

ФОРМАТ: ГАЛЕРЕЯ (4-5 карточек для свайпа)

СТРУКТУРА ГАЛЕРЕИ:
- КАРТОЧКА 1 (главная): Крупная цена/платёж + локация + стрелка →
- КАРТОЧКА 2: Визуал проекта + ключевое УТП
- КАРТОЧКА 3: Инфраструктура (школы, сады, парки)
- КАРТОЧКА 4: Карта локации / время до метро
- КАРТОЧКА 5: Условия покупки (взнос, рассрочка, ипотека)

ПРАВИЛА:
- Каждая карточка — самодостаточна
- На главной карточке обязательно стрелка → (призыв листать)
- Крупные цифры: цена, платёж, взнос
- НЕ указывай название ЖК
- Время до метро: "мин."

СТИЛЬ ТЕКСТА В ПОСТЕ:
- Раскрывающаяся структура "Это про..."
- Вопрос в заголовке
- Триггеры через эмодзи

Эмодзи клиента:
{emoji_section}"""

        user_prompt_template = """ТЕКСТ ПОСТА:
{post}

ЗАДАЧА:
Сгенерируй ТЗ для ГАЛЕРЕИ (4-5 карточек карусели).

ФОРМАТ ОТВЕТА:

📋 ТЗ ДЛЯ ДИЗАЙНЕРА
📑 Формат: Галерея (4-5 карточек)

═══════════════════════════════════════

КАРТОЧКА 1 (главная):
[КРУПНЫЙ ТЕКСТ]: цена или платёж
[ПОДТЕКСТ]: локация
[ЭЛЕМЕНТ]: стрелка → (листай)

КАРТОЧКА 2 (УТП):
[ТЕКСТ]: главное преимущество
[ВИЗУАЛ]: что показать

КАРТОЧКА 3 (инфраструктура):
[ТЕКСТ]: что рядом
[ВИЗУАЛ]: иконки/фото

КАРТОЧКА 4 (локация):
[ТЕКСТ]: время до метро/центра
[ВИЗУАЛ]: карта или схема

КАРТОЧКА 5 (условия):
[ТЕКСТ]: взнос, рассрочка, ипотека
[ВИЗУАЛ]: цифры крупно

═══════════════════════════════════════

📝 ТЕКСТ ПОСТА (раскрывающийся):

[Заголовок-вопрос]
...это про что?

[Блок 1]
🏎️ Это про...
[текст]

[Блок 2]
👥 Это про...
[текст]

[Блок 3]
🏙 Это про...
[текст]

[Вывод + CTA]
📌 Сохраняйте и пишите..."""

    return system_prompt, user_prompt_template


async def callback_brief_format(callback: CallbackQuery, state: FSMContext):
    """Генерация ТЗ в выбранном формате — по умолчанию КОМПАКТНОЕ"""
    from utils.design_brief import generate_compact_brief, generate_detailed_brief

    format_type = callback.data.replace("brief_format_", "")

    if format_type == "back":
        # Возврат к посту
        data = await state.get_data()
        post = data.get("generated_post", "")
        preview = post[:3500] + "..." if len(post) > 3500 else post
        await callback.message.edit_text(
            f"📝 Пост:\n\n{preview}",
            reply_markup=get_post_edit_keyboard()
        )
        await callback.answer()
        return

    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")

    format_names = {
        "banner": "баннер",
        "slider": "ГИФ-слайдер",
        "gallery": "галерею",
        "carousel": "карусель"
    }

    await callback.message.edit_text(f"⏳ Генерирую КОРОТКОЕ ТЗ на {format_names.get(format_type, 'креатив')}...")
    await callback.answer()

    try:
        emoji_section = get_emoji_prompt_section(client_slug)

        # Генерируем КОМПАКТНОЕ ТЗ по умолчанию
        brief = generate_compact_brief(post, format_type, emoji_section)

        # Сохраняем ТЗ и формат в state
        await state.update_data(
            post_brief=brief,
            brief_format=format_type,
            brief_is_compact=True
        )

        # Подсчитываем символы
        char_count = len(brief)
        status = "✅" if char_count <= 1200 else "⚠️"

        preview = brief[:3500] + "..." if len(brief) > 3500 else brief
        await callback.message.answer(
            f"🎨 Короткое ТЗ ({char_count} симв.) {status}\n\n{preview}",
            reply_markup=get_post_brief_keyboard(is_compact=True)
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")
        await callback.message.answer(
            "Вернуться к посту:",
            reply_markup=get_post_edit_keyboard()
        )


async def callback_post_brief_expand(callback: CallbackQuery, state: FSMContext):
    """Развернуть ТЗ — сгенерировать подробную версию"""
    from utils.design_brief import generate_detailed_brief

    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")
    format_type = data.get("brief_format", "banner")

    await callback.answer("Генерирую подробное ТЗ...")
    await callback.message.edit_text("⏳ Генерирую ПОДРОБНОЕ ТЗ...")

    try:
        emoji_section = get_emoji_prompt_section(client_slug)
        detailed_brief = generate_detailed_brief(post, format_type, emoji_section)

        await state.update_data(
            post_brief=detailed_brief,
            brief_is_compact=False
        )

        char_count = len(detailed_brief)
        preview = detailed_brief[:3500] + "..." if len(detailed_brief) > 3500 else detailed_brief
        await callback.message.answer(
            f"📖 Подробное ТЗ ({char_count} симв.)\n\n{preview}",
            reply_markup=get_post_brief_keyboard(is_compact=False)
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")


async def callback_post_brief_compact(callback: CallbackQuery, state: FSMContext):
    """Свернуть ТЗ — сгенерировать короткую версию"""
    from utils.design_brief import generate_compact_brief

    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")
    format_type = data.get("brief_format", "banner")

    await callback.answer("Генерирую короткое ТЗ...")
    await callback.message.edit_text("⏳ Генерирую КОРОТКОЕ ТЗ...")

    try:
        emoji_section = get_emoji_prompt_section(client_slug)
        compact_brief = generate_compact_brief(post, format_type, emoji_section)

        await state.update_data(
            post_brief=compact_brief,
            brief_is_compact=True
        )

        char_count = len(compact_brief)
        status = "✅" if char_count <= 1200 else "⚠️"
        preview = compact_brief[:3500] + "..." if len(compact_brief) > 3500 else compact_brief
        await callback.message.answer(
            f"📝 Короткое ТЗ ({char_count} симв.) {status}\n\n{preview}",
            reply_markup=get_post_brief_keyboard(is_compact=True)
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")


async def callback_post_brief_approve(callback: CallbackQuery, state: FSMContext):
    """Согласовать и отправить ТЗ дизайнеру"""
    data = await state.get_data()
    brief = data.get("post_brief", "")
    client_slug = data.get("current_client")

    if not brief:
        await callback.answer("ТЗ не найдено")
        return

    await callback.answer("Отправляю дизайнеру...")

    bot: Bot = callback.message.bot
    success = await send_brief_to_designer(bot, client_slug, brief)

    designer = get_client_designer(client_slug)

    if success:
        await callback.message.edit_text(
            f"✅ ТЗ отправлено дизайнеру {designer or ''}"
        )
    else:
        await callback.message.edit_text(
            f"⚠️ Не удалось отправить в чат. ТЗ:\n\n{brief[:2000]}"
        )


async def callback_post_brief_edit(callback: CallbackQuery, state: FSMContext):
    """Редактировать ТЗ из поста"""
    await callback.answer()
    await callback.message.answer("✏️ Напиши исправленный текст ТЗ:")
    await state.set_state(ContentStates.waiting_for_post_brief_edit)


async def process_post_brief_edit(message: types.Message, state: FSMContext):
    """Обработка отредактированного ТЗ из поста"""
    new_brief = message.text

    await state.update_data(post_brief=new_brief)
    await state.set_state(None)

    preview = new_brief[:3500] + "..." if len(new_brief) > 3500 else new_brief
    await message.answer(
        f"✅ ТЗ обновлено:\n\n{preview}",
        reply_markup=get_post_brief_keyboard()
    )


async def callback_post_brief_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться к посту"""
    data = await state.get_data()
    post = data.get("generated_post", "")

    await callback.answer()

    if post:
        preview = post[:3500] + "..." if len(post) > 3500 else post
        await callback.message.edit_text(
            f"📝 Пост:\n\n{preview}",
            reply_markup=get_post_edit_keyboard()
        )
    else:
        await callback.message.edit_text(
            "Пост не найден",
            reply_markup=None
        )


# =============================================================================
# СЦЕНАРИЙ ИЗ ПОСТА
# =============================================================================

def get_script_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа сценария"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎙 Голосовое (45-90 сек)", callback_data="script_type_voice")],
        [InlineKeyboardButton(text="⭕ Кружок (20-40 сек)", callback_data="script_type_circle")],
        [InlineKeyboardButton(text="⬅️ Назад к посту", callback_data="script_back")]
    ])


def get_script_result_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после генерации сценария"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="script_regen"),
            InlineKeyboardButton(text="📋 Скопировать", callback_data="script_copy")
        ],
        [InlineKeyboardButton(text="⬅️ Назад к посту", callback_data="script_back")]
    ])


async def callback_post_to_script(callback: CallbackQuery, state: FSMContext):
    """Конвертация поста в сценарий — выбор типа через post_actions"""
    data = await state.get_data()
    post = data.get("generated_post", "")

    if not post:
        await callback.answer("Пост не найден")
        return

    await callback.answer()

    # Используем клавиатуру из post_actions
    await callback.message.edit_text(
        "🎙️ Выбери тип и длительность сценария:\n\n"
        "🎙 **Голосовое** — 45-120 сек, с таймкодами и интонациями\n"
        "⭕ **Кружок** — 20-40 сек, с визуальными подсказками",
        reply_markup=get_script_type_keyboard(post_id=None),
        parse_mode="Markdown"
    )


async def callback_script_type(callback: CallbackQuery, state: FSMContext):
    """Генерация сценария выбранного типа"""
    from utils.script_generator import generate_voice_script, generate_circle_script

    script_type = callback.data.replace("script_type_", "")

    if script_type == "back":
        data = await state.get_data()
        post = data.get("generated_post", "")
        if post:
            preview = post[:3500] + "..." if len(post) > 3500 else post
            await callback.message.edit_text(
                f"📝 Пост:\n\n{preview}",
                reply_markup=get_post_edit_keyboard()
            )
        await callback.answer()
        return

    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")

    type_names = {"voice": "голосовое", "circle": "кружок"}
    await callback.message.edit_text(f"⏳ Генерирую сценарий для {type_names.get(script_type, 'контента')}...")
    await callback.answer()

    try:
        context = get_client_prompt(client_slug) if client_slug else ""

        if script_type == "voice":
            script = generate_voice_script(post, "medium", context)
        else:
            script = generate_circle_script(post, "short", context)

        # Сохраняем сценарий
        await state.update_data(
            generated_script=script,
            script_type=script_type
        )

        preview = script[:3500] + "..." if len(script) > 3500 else script
        emoji = "🎙" if script_type == "voice" else "⭕"
        await callback.message.answer(
            f"{emoji} Сценарий готов:\n\n{preview}",
            reply_markup=get_script_result_keyboard()
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")


async def callback_script_regen(callback: CallbackQuery, state: FSMContext):
    """Перегенерировать сценарий"""
    from utils.script_generator import generate_voice_script, generate_circle_script

    data = await state.get_data()
    post = data.get("generated_post", "")
    script_type = data.get("script_type", "voice")
    client_slug = data.get("current_client")

    await callback.answer("Перегенерирую...")
    await callback.message.edit_text("⏳ Генерирую новый вариант сценария...")

    try:
        context = get_client_prompt(client_slug) if client_slug else ""

        if script_type == "voice":
            script = generate_voice_script(post, "medium", context)
        else:
            script = generate_circle_script(post, "short", context)

        await state.update_data(generated_script=script)

        preview = script[:3500] + "..." if len(script) > 3500 else script
        emoji = "🎙" if script_type == "voice" else "⭕"
        await callback.message.answer(
            f"{emoji} Новый сценарий:\n\n{preview}",
            reply_markup=get_script_result_keyboard()
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")


async def callback_script_copy(callback: CallbackQuery, state: FSMContext):
    """Скопировать сценарий"""
    data = await state.get_data()
    script = data.get("generated_script", "")

    if script:
        await callback.message.answer(script)
        await callback.answer("Сценарий отправлен для копирования")
    else:
        await callback.answer("Сценарий не найден")


async def callback_script_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться к посту из сценария"""
    data = await state.get_data()
    post = data.get("generated_post", "")

    await callback.answer()

    if post:
        preview = post[:3500] + "..." if len(post) > 3500 else post
        await callback.message.edit_text(
            f"📝 Пост:\n\n{preview}",
            reply_markup=get_post_edit_keyboard()
        )
    else:
        await callback.message.edit_text("Пост не найден")


async def callback_post_done(callback: CallbackQuery, state: FSMContext):
    """Завершить работу с постом"""
    # Сохраняем current_client перед очисткой
    data = await state.get_data()
    client = data.get("current_client")

    await state.clear()

    if client:
        await state.update_data(current_client=client)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Готово!")


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.message.register(cmd_plan, Command("plan"))
    dp.message.register(cmd_brief, Command("brief"))
    dp.message.register(cmd_live, Command("live"))
    dp.message.register(cmd_voice_intro, Command("voice_intro"))
    dp.message.register(cmd_add_channel, Command("add_channel"))
    dp.message.register(cmd_post, Command("post"))
    dp.message.register(cmd_circle, Command("circle"))

    # Callback обработчики для мемов из /post (регистрируем ДО общего post_)
    dp.callback_query.register(callback_post_meme_select, F.data.startswith("post_meme_select_"))
    dp.callback_query.register(callback_post_meme_save, F.data == "post_meme_save")
    dp.callback_query.register(callback_post_meme_refresh, F.data == "post_meme_refresh")
    dp.callback_query.register(callback_post_meme_cancel, F.data == "post_meme_cancel")

    # Callback обработчики для редактирования поста (регистрируем ДО общего post_)
    dp.callback_query.register(callback_post_regen, F.data == "post_regen")
    dp.callback_query.register(callback_post_edit_request, F.data == "post_edit_request")
    dp.callback_query.register(callback_post_copy, F.data == "post_copy")
    dp.callback_query.register(callback_post_done, F.data == "post_done")
    dp.callback_query.register(callback_post_harder, F.data == "post_harder")
    dp.callback_query.register(callback_post_softer, F.data == "post_softer")

    # ТЗ из поста (регистрируем ДО общего post_)
    dp.callback_query.register(callback_post_brief, F.data == "post_brief")
    # Новые обработчики из post_actions
    dp.callback_query.register(callback_design_type, F.data.startswith("design_"))
    dp.callback_query.register(callback_brief_format, F.data.startswith("brief_format_"))
    dp.callback_query.register(callback_post_brief_approve, F.data == "post_brief_approve")
    dp.callback_query.register(callback_post_brief_edit, F.data == "post_brief_edit")
    dp.callback_query.register(callback_post_brief_back, F.data == "post_brief_back")
    dp.callback_query.register(callback_post_brief_expand, F.data == "post_brief_expand")
    dp.callback_query.register(callback_post_brief_compact, F.data == "post_brief_compact")
    dp.message.register(process_post_brief_edit, ContentStates.waiting_for_post_brief_edit)

    # Сценарий из поста (регистрируем ДО общего post_)
    dp.callback_query.register(callback_post_to_script, F.data == "post_to_script")
    # Новые обработчики из post_actions для сценариев
    dp.callback_query.register(callback_script_type_new, F.data.startswith("script_"))
    dp.callback_query.register(callback_script_type, F.data.startswith("script_type_"))
    dp.callback_query.register(callback_script_regen, F.data == "script_regen")
    dp.callback_query.register(callback_script_copy, F.data == "script_copy")
    dp.callback_query.register(callback_script_back, F.data == "script_back")

    # Выбор даты поста (регистрируем ДО общего post_)
    dp.callback_query.register(callback_post_date, F.data.startswith("post_date_"))
    dp.message.register(process_post_date_input, ContentStates.waiting_for_post_date)

    # Callback обработчики для inline-кнопок
    dp.callback_query.register(callback_post_format, F.data.startswith("post_"))
    dp.callback_query.register(callback_brief_ad_type, F.data.startswith("brief_ad_"))
    dp.callback_query.register(callback_brief_mode, F.data.startswith("brief_mode_"))

    # Callback для контент-плана: начальные вопросы
    dp.callback_query.register(callback_plan_period, F.data.startswith("plan_period_"))
    dp.callback_query.register(callback_plan_posts, F.data.startswith("plan_posts_"))
    dp.callback_query.register(callback_plan_events_skip, F.data == "plan_events_skip")

    # Callback для контент-плана: сбор данных
    dp.callback_query.register(process_plan_clear_lots, F.data == "plan_clear_lots", ContentStates.waiting_for_plan_lots)
    dp.callback_query.register(callback_plan_manual_themes, F.data == "plan_manual_themes", ContentStates.waiting_for_plan_lots)
    dp.callback_query.register(process_plan_skip_lots, F.data == "plan_skip", ContentStates.waiting_for_plan_lots)
    dp.callback_query.register(callback_plan_skip_themes, F.data == "plan_skip_themes", ContentStates.waiting_for_plan_manual_themes)
    dp.callback_query.register(callback_plan_themes_done, F.data == "plan_themes_done", ContentStates.waiting_for_plan_manual_themes)
    dp.callback_query.register(process_plan_skip_live, F.data == "plan_skip", ContentStates.waiting_for_plan_live)
    dp.callback_query.register(process_plan_generate, F.data == "plan_skip", ContentStates.waiting_for_plan_requests)
    dp.callback_query.register(process_plan_generate, F.data == "plan_generate")

    # Callback для ТЗ из контент-плана
    dp.callback_query.register(callback_plan_to_brief, F.data == "plan_to_brief")
    dp.callback_query.register(callback_plan_finish, F.data == "plan_finish")
    dp.callback_query.register(callback_lot_toggle, F.data.startswith("lot_toggle_"))
    dp.callback_query.register(callback_lot_select_all, F.data == "lot_select_all")
    dp.callback_query.register(callback_lot_select_none, F.data == "lot_select_none")
    dp.callback_query.register(callback_lot_selection_done, F.data == "lot_selection_done")
    dp.callback_query.register(callback_brief_edit, F.data == "brief_edit")
    dp.callback_query.register(callback_brief_send, F.data == "brief_send")
    dp.callback_query.register(callback_brief_skip, F.data == "brief_skip")

    # FSM обработчики
    dp.message.register(process_plan_events_text, ContentStates.waiting_for_plan_info)
    dp.message.register(process_plan_lots, ContentStates.waiting_for_plan_lots)
    dp.message.register(process_plan_manual_themes, ContentStates.waiting_for_plan_manual_themes)
    dp.message.register(process_plan_live, ContentStates.waiting_for_plan_live)
    dp.message.register(process_plan_requests, ContentStates.waiting_for_plan_requests)
    dp.message.register(process_brief_data, ContentStates.waiting_for_brief_data)
    dp.message.register(process_brief_edit, ContentStates.waiting_for_brief_edit)
    dp.message.register(process_live_content, ContentStates.waiting_for_live_link)
    dp.message.register(process_voice_content, ContentStates.waiting_for_voice_topic)
    dp.message.register(process_post_lot, ContentStates.waiting_for_post_lot)
    dp.message.register(process_post_digest, ContentStates.waiting_for_post_digest_topic)
    dp.message.register(process_circle_topic, ContentStates.waiting_for_circle_topic)
    dp.message.register(process_post_edit, ContentStates.waiting_for_post_edit)

# =============================================================================
# НОВЫЕ ОБРАБОТЧИКИ ИЗ POST_ACTIONS.PY
# =============================================================================

async def callback_design_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа дизайна через post_actions клавиатуру"""
    data_str = callback.data
    
    # Обработка отмены
    if data_str.endswith("design_cancel"):
        data = await state.get_data()
        post = data.get("generated_post", "")
        preview = post[:3500] + "..." if len(post) > 3500 else post
        await callback.message.edit_text(
            f"📝 Пост:\n\n{preview}",
            reply_markup=get_post_edit_keyboard()
        )
        await callback.answer()
        return
    
    # Разбор формата: design_banner, design_slider, etc.
    if "design_banner" in data_str:
        format_type = "banner"
        brief_mode = "compact"
    elif "design_slider" in data_str:
        format_type = "slider"
        brief_mode = "compact"
    elif "design_gallery" in data_str:
        format_type = "gallery"
        brief_mode = "compact"
    elif "design_carousel" in data_str:
        format_type = "carousel"
        brief_mode = "compact"
    elif "design_compact" in data_str:
        # Компактное ТЗ для текущего формата
        data = await state.get_data()
        format_type = data.get("brief_format", "banner")
        brief_mode = "compact"
    elif "design_detailed" in data_str:
        # Подробное ТЗ для текущего формата
        data = await state.get_data()
        format_type = data.get("brief_format", "banner")
        brief_mode = "detailed"
    else:
        await callback.answer("Неизвестный формат")
        return
    
    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")
    
    if not post:
        await callback.answer("Пост не найден")
        return
    
    format_names = {
        "banner": "баннер",
        "slider": "ГИФ-слайдер",
        "gallery": "галерею",
        "carousel": "карусель"
    }
    
    mode_names = {
        "compact": "КОРОТКОЕ",
        "detailed": "ПОДРОБНОЕ"
    }
    
    await callback.message.edit_text(
        f"⏳ Генерирую {mode_names[brief_mode]} ТЗ на {format_names.get(format_type, 'креатив')}..."
    )
    await callback.answer()
    
    try:
        emoji_section = get_emoji_prompt_section(client_slug)

        # Используем generate_design_for_post из post_actions
        brief = generate_design_for_post(
            post_text=post,
            design_type=format_type,
            brief_mode=brief_mode,
            client_context=emoji_section
        )
        
        # Сохраняем ТЗ и формат в state
        await state.update_data(
            post_brief=brief,
            brief_format=format_type,
            brief_is_compact=(brief_mode == "compact")
        )
        
        # Подсчитываем символы
        char_count = len(brief)
        mode_display = "Короткое" if brief_mode == "compact" else "Подробное"
        status = "✅" if (brief_mode == "compact" and char_count <= 1200) else ""
        
        preview = brief[:3500] + "..." if len(brief) > 3500 else brief
        await callback.message.answer(
            f"🎨 {mode_display} ТЗ ({char_count} симв.) {status}\n\n{preview}",
            reply_markup=get_post_brief_keyboard(is_compact=(brief_mode == "compact"))
        )
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")
        await callback.message.answer(
            "Вернуться к посту:",
            reply_markup=get_post_edit_keyboard()
        )



async def callback_script_type_new(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа сценария через post_actions клавиатуру"""
    data_str = callback.data
    
    # Обработка отмены
    if data_str.endswith("script_cancel"):
        data = await state.get_data()
        post = data.get("generated_post", "")
        preview = post[:3500] + "..." if len(post) > 3500 else post
        await callback.message.edit_text(
            f"📝 Пост:\n\n{preview}",
            reply_markup=get_post_edit_keyboard()
        )
        await callback.answer()
        return
    
    # Разбор формата: script_voice_short, script_circle_medium, etc.
    if "script_voice" in data_str:
        script_type = "voice"
        if "short" in data_str:
            duration = "short"  # 45-60
        elif "long" in data_str:
            duration = "long"   # 90-120
        else:
            duration = "medium" # 60-90
    elif "script_circle" in data_str:
        script_type = "circle"
        if "medium" in data_str:
            duration = "medium" # 30-40
        else:
            duration = "short"  # 20-30
    else:
        await callback.answer("Неизвестный формат сценария")
        return
    
    data = await state.get_data()
    post = data.get("generated_post", "")
    client_slug = data.get("current_client")
    
    if not post:
        await callback.answer("Пост не найден")
        return
    
    duration_names = {
        ("voice", "short"): "45-60 сек",
        ("voice", "medium"): "60-90 сек",
        ("voice", "long"): "90-120 сек",
        ("circle", "short"): "20-30 сек",
        ("circle", "medium"): "30-40 сек"
    }
    
    type_emoji = "🎙" if script_type == "voice" else "⭕"
    duration_text = duration_names.get((script_type, duration), "средней длительности")
    
    await callback.message.edit_text(
        f"⏳ Генерирую {type_emoji} сценарий ({duration_text})..."
    )
    await callback.answer()
    
    try:
        context = get_client_prompt(client_slug) if client_slug else ""
        
        # Используем generate_script_for_post из post_actions
        script = await generate_script_for_post(
            post_text=post,
            script_type=script_type,
            duration=duration,
            client_context=context
        )
        
        # Сохраняем сценарий
        await state.update_data(
            generated_script=script,
            script_type=script_type,
            script_duration=duration
        )
        
        preview = script[:3500] + "..." if len(script) > 3500 else script
        await callback.message.answer(
            f"{type_emoji} Сценарий готов ({duration_text}):\n\n{preview}",
            reply_markup=get_script_result_keyboard()
        )
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")
        await callback.message.answer(
            "Вернуться к посту:",
            reply_markup=get_post_edit_keyboard()
        )

