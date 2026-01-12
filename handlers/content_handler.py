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
from utils.claude_api import generate_content
from utils.jk_parser import find_url_in_text, parse_jk_website, format_parsed_data
from utils.ad_eligibility import check_ad_eligibility, parse_lot_for_ads
from utils.content_journal import add_entry as add_journal_entry
from utils.meme_sources import get_top_references, format_reference_preview, get_reference_by_index


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
    waiting_for_live_link = State()
    waiting_for_voice_topic = State()
    waiting_for_plan_client = State()
    waiting_for_channel = State()
    # Новые состояния для /post
    waiting_for_post_format = State()
    waiting_for_post_lot = State()
    waiting_for_post_digest_topic = State()
    waiting_for_circle_topic = State()
    # Состояния для контент-плана
    waiting_for_plan_info = State()  # НОВОЕ: сбор базовой информации
    waiting_for_plan_lots = State()
    waiting_for_plan_live = State()
    waiting_for_plan_requests = State()
    # Состояния для ТЗ из контент-плана
    waiting_for_brief_edit = State()  # Редактирование ТЗ перед отправкой


def get_plan_skip_keyboard(show_clear: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для пропуска шага"""
    buttons = [
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="plan_skip")],
        [InlineKeyboardButton(text="✅ Готово, генерировать К-П", callback_data="plan_generate")],
    ]
    if show_clear:
        buttons.append([InlineKeyboardButton(text="🗑 Очистить лоты", callback_data="plan_clear_lots")])
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
        reply_markup=get_plan_skip_keyboard(show_clear=len(lots) > 0)
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
    period = data.get("plan_period", 7)
    posts_per_day = data.get("plan_posts_per_day", 1)
    events = data.get("plan_events", "")

    await callback.message.answer(f"⏳ Генерирую контент-план на {period} дней...")

    plan_id = await generate_content_plan_with_data(
        callback.message, client, lots, live, requests,
        period=period, posts_per_day=posts_per_day, events=events
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
    events: str = ""
) -> str:
    """Генерация контент-плана на основе собранных данных. Возвращает plan_id."""

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
5. ПРИОРИТЕТ просьбам клиента — они важнее всего
6. Если указаны события/даты — обязательно учитывай их в плане
7. ОБЯЗАТЕЛЬНО указывай пометку 📢ADS или 📱КАНАЛ для каждого лидген-поста

НЕ используй markdown (звёздочки, подчёркивания).
Эмодзи используй для типов контента."""

        # Текущая дата
        today = datetime.now()
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        user_prompt = f"""Создай контент-план на {period} дней начиная с {today.strftime('%d.%m.%Y')} ({weekday_names[today.weekday()]}).
Постов в день: {posts_per_day}

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
    client = data.get("current_client", "apple_real_estate")

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
    client = data.get("current_client", "apple_real_estate")

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
    client = data.get("current_client", "apple_real_estate")
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
    data = await state.get_data()

    user_input = data.get("brief_input", "")
    url = data.get("brief_url")
    parsed_data = data.get("brief_parsed", "")

    # Определяем формат и дату
    content_format = get_next_format()
    format_display = get_format_display(content_format)
    pub_date, pub_weekday = get_next_publish_date()

    ad_type = "Реклама + канал" if is_for_ads else "Только канал"

    await callback.message.edit_text(
        f"📅 Дата: {pub_date} ({pub_weekday})\n"
        f"🎬 Формат: {format_display}\n"
        f"📢 Тип: {ad_type}\n\n"
        "⏳ Генерирую ТЗ..."
    )
    await callback.answer()

    try:
        # Получаем эмодзи клиента
        client_slug = "apple_real_estate"
        emoji_section = get_emoji_prompt_section(client_slug)

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
1. ВАРИАНТ "ФИНАНСЫ" — акцент на доступности (взнос, рассрочка, платёж)
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
    clients = list_clients()
    client_slug = clients[0] if clients else "apple_real_estate"

    await message.answer("⏳ Пишу подводку к Instagram-материалу...")

    try:
        context = get_client_prompt(client_slug)

        system_prompt = f"""{context}

Ты пишешь ПОДВОДКУ К INSTAGRAM-МАТЕРИАЛУ для Telegram-канала.

СТРУКТУРА:
1. Эмодзи + Заголовок (привлекающий внимание)
2. Подводка (2-4 предложения) — зачем смотреть/читать
3. Указание что это из Instagram (📸 Смотри в наших Stories / Reels)
4. CTA (⚪️ "Напишите..." или "Подписывайтесь...")

ПРАВИЛА:
- Подводка должна интриговать, но не раскрывать всё
- Лёгкий, живой тон
- НЕ используй markdown
- Эмодзи для структуры"""

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
    clients = list_clients()
    client_slug = clients[0] if clients else "apple_real_estate"

    # Определяем тип запроса — транскрипция (длинный текст) или тема (короткий)
    is_transcription = len(user_input) > 200

    if is_transcription:
        await message.answer("⏳ Пишу подводку к голосовому на основе транскрипции...")
    else:
        await message.answer("⏳ Генерирую сценарий для записи голосового...")

    try:
        context = get_client_prompt(client_slug)

        if is_transcription:
            # Генерируем подводку к уже записанному голосовому
            system_prompt = f"""{context}

Ты пишешь ПОДВОДКУ К ГОЛОСОВОМУ СООБЩЕНИЮ для Telegram-канала.

СТРУКТУРА:
1. Эмодзи + Интригующий заголовок
2. Подводка (2-3 предложения) — о чём голосовое, зачем слушать
3. [Здесь будет голосовое]
4. CTA (⚪️ "Напишите...")

ПРАВИЛА:
- Подводка должна заинтриговать
- Выдели ключевую мысль из транскрипции
- НЕ используй markdown"""

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
    clients = list_clients()

    if not clients:
        await message.answer("❌ Нет клиентов. Создай клиента через /newclient")
        return

    # Сохраняем клиента (берём первого или единственного)
    client_slug = clients[0]
    await state.update_data(client_slug=client_slug)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Лидген-карточка", callback_data="post_leadgen")],
        [InlineKeyboardButton(text="🎙 Пост с кружком", callback_data="post_circle")],
        [InlineKeyboardButton(text="📰 Дайджест", callback_data="post_digest")],
        [InlineKeyboardButton(text="📚 Экспертный контент", callback_data="post_expert")],
        [InlineKeyboardButton(text="😂 Мем", callback_data="post_meme")]
    ])

    await message.answer(
        "📝 Генерация поста\n\n"
        "Выбери формат:",
        reply_markup=keyboard
    )


async def callback_post_format(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора формата поста"""
    format_type = callback.data.replace("post_", "")
    await state.update_data(post_format=format_type)

    data = await state.get_data()
    client_slug = data.get("client_slug", "apple_real_estate")

    if format_type == "leadgen":
        # Показываем лоты для выбора
        lots = get_client_lots(client_slug, status="READY_FOR_CONTENT")

        if lots:
            lots_text = "Выбери лот (напиши номер) или отправь ссылку на ЖК:\n\n"
            for i, lot in enumerate(lots, 1):
                lot_name = lot.get("lot_name", "Без названия")
                lots_text += f"{i}. {lot_name}\n"

            await callback.message.edit_text(
                f"🏢 Лидген-карточка\n\n{lots_text}\n"
                "Или отправь ссылку на сайт ЖК — распаршу и сгенерирую пост."
            )
        else:
            await callback.message.edit_text(
                "🏢 Лидген-карточка\n\n"
                "Лотов пока нет. Отправь ссылку на сайт ЖК — распаршу и сгенерирую пост."
            )

        await state.set_state(ContentStates.waiting_for_post_lot)

    elif format_type == "circle":
        await callback.message.edit_text(
            "🎙 Пост с кружком\n\n"
            "Отправь тему или ключевые тезисы из кружка брокера.\n\n"
            "Если кружок ещё не записан — используй /circle для получения ТЗ."
        )
        await state.set_state(ContentStates.waiting_for_post_lot)

    elif format_type == "digest":
        await callback.message.edit_text(
            "📰 Дайджест\n\n"
            "Напиши тему дайджеста или что включить:\n"
            "• Итоги недели\n"
            "• Тренды рынка\n"
            "• Подборка объектов\n"
            "• Ответы на частые вопросы"
        )
        await state.set_state(ContentStates.waiting_for_post_digest_topic)

    elif format_type == "expert":
        await callback.message.edit_text(
            "📚 Экспертный контент\n\n"
            "Напиши тему для экспертного поста:\n"
            "• Советы покупателям\n"
            "• Разбор ошибок\n"
            "• Ответ на частый вопрос\n"
            "• Сравнение (аренда vs ипотека)\n\n"
            "Пример: \"5 ошибок при покупке первой квартиры\""
        )
        await state.set_state(ContentStates.waiting_for_post_lot)

    elif format_type == "meme":
        # Запускаем логику мемов
        await show_meme_references(callback, state)
        return

    await callback.answer()


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
    client_slug = data.get("client_slug", "apple_real_estate")

    await message.answer("⏳ Генерирую пост...")

    try:
        # Загружаем контекст клиента
        context = get_client_prompt(client_slug)

        # Определяем тип поста и формируем промпт
        if post_format == "leadgen":
            # Проверяем — это номер лота или ссылка?
            url = find_url_in_text(user_input)
            lot_data = ""

            if url:
                # Парсим сайт ЖК
                parse_result = await parse_jk_website(url)
                if parse_result["parse_success"]:
                    lot_data = format_parsed_data(parse_result)
            elif user_input.isdigit():
                # Берём лот по номеру
                lots = get_client_lots(client_slug, status="READY_FOR_CONTENT")
                lot_index = int(user_input) - 1
                if 0 <= lot_index < len(lots):
                    lot = lots[lot_index]
                    lot_data = f"""
Название: {lot.get('lot_name', 'Не указано')}
Цена: {lot.get('price', 'Не указана')}
Первый взнос: {lot.get('downpayment', 'Не указан')}
Платёж в месяц: {lot.get('monthly_payment', 'Не указан')}
Локация: {lot.get('location', 'Не указана')}
Особенности: {lot.get('features', 'Не указаны')}
"""
            else:
                lot_data = user_input

            system_prompt = f"""{context}

Ты пишешь ЛИДГЕН-КАРТОЧКУ для Telegram-канала.

СТРУКТУРА ПОСТА:
1. Эмодзи-заголовок (🔥/🏢/🏡) + Краткое описание выгоды
2. Эмоциональный хук (для кого подойдёт)
3. Ключевые характеристики:
   - 📍 Локация (минут до метро/центра)
   - Планировка/площадь
   - 💰 Цена и финансовые условия
4. Фишки проекта (через ▪️)
5. CTA с кнопкой (⚪️ "Напишите 'КЛЮЧЕВОЕ_СЛОВО'")

ПРАВИЛА:
- НЕ используй markdown (звёздочки, подчёркивания)
- Короткие абзацы (1-2 строки)
- Конкретные цифры
- CTA с тематическим ключевым словом"""

            user_prompt = f"""Напиши лидген-карточку на основе данных:

{lot_data}

Сделай пост готовым к публикации в Telegram."""

        elif post_format == "circle":
            system_prompt = f"""{context}

Ты пишешь ПОДВОДКУ К КРУЖКУ от брокера для Telegram-канала.

СТРУКТУРА:
1. Эмодзи + Интригующий заголовок (вопрос или утверждение)
2. Краткая подводка (2-3 предложения) — зачем слушать
3. [Здесь будет кружок]
4. CTA (⚪️ "Напишите...")

ПРАВИЛА:
- Подводка должна заинтриговать
- Не раскрывай всё содержание — только затравку
- НЕ используй markdown"""

            user_prompt = f"""Напиши подводку к кружку брокера на тему:

{user_input}

Сделай пост готовым к публикации."""

        elif post_format == "expert":
            system_prompt = f"""{context}

Ты пишешь ЭКСПЕРТНЫЙ ПОСТ для Telegram-канала.

СТРУКТУРА:
1. Заголовок с цифрой или вопросом
2. Вступление (контекст проблемы)
3. Список с нумерацией (1️⃣ 2️⃣ 3️⃣...)
   - Каждый пункт: тезис + пояснение
4. Вывод
5. CTA

ПРАВИЛА:
- 3-5 пунктов максимум
- Конкретные примеры
- НЕ используй markdown
- Разговорный стиль с экспертизой"""

            user_prompt = f"""Напиши экспертный пост на тему:

{user_input}

Сделай пост готовым к публикации."""

        else:
            # Дайджест обрабатывается отдельно
            await state.clear()
            return

        # Генерация через Claude
        post = generate_content(system_prompt, user_prompt)

        # Сохраняем в журнал
        format_map = {"leadgen": "lidgen", "circle": "circle", "expert": "expert"}
        journal_format = format_map.get(post_format, post_format)
        add_journal_entry(
            client_slug=client_slug,
            date=datetime.now().strftime("%Y-%m-%d"),
            format_type=journal_format,
            text=post,
            status="published",
            source="bot_generated"
        )

        # Отправляем результат
        max_length = 4000
        if len(post) > max_length:
            parts = [post[i:i+max_length] for i in range(0, len(post), max_length)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(f"✅ Пост готов (сохранён в журнал):\n\n{post}")

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")

    await state.clear()


async def process_post_digest(message: types.Message, state: FSMContext):
    """Обработка генерации дайджеста"""
    user_input = message.text
    data = await state.get_data()
    client_slug = data.get("client_slug", "apple_real_estate")

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

        # Сохраняем в журнал
        add_journal_entry(
            client_slug=client_slug,
            date=datetime.now().strftime("%Y-%m-%d"),
            format_type="digest",
            text=post,
            status="published",
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
    client = data.get("client_slug") or data.get("current_client", "apple_real_estate")
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
    client = data.get("client_slug") or data.get("current_client", "apple_real_estate")
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
    client_slug = data.get("client_slug", "apple_real_estate")

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

    # Callback обработчики для inline-кнопок
    dp.callback_query.register(callback_post_format, F.data.startswith("post_"))
    dp.callback_query.register(callback_brief_ad_type, F.data.startswith("brief_ad_"))

    # Callback для контент-плана: начальные вопросы
    dp.callback_query.register(callback_plan_period, F.data.startswith("plan_period_"))
    dp.callback_query.register(callback_plan_posts, F.data.startswith("plan_posts_"))
    dp.callback_query.register(callback_plan_events_skip, F.data == "plan_events_skip")

    # Callback для контент-плана: сбор данных
    dp.callback_query.register(process_plan_clear_lots, F.data == "plan_clear_lots", ContentStates.waiting_for_plan_lots)
    dp.callback_query.register(process_plan_skip_lots, F.data == "plan_skip", ContentStates.waiting_for_plan_lots)
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
    dp.message.register(process_plan_live, ContentStates.waiting_for_plan_live)
    dp.message.register(process_plan_requests, ContentStates.waiting_for_plan_requests)
    dp.message.register(process_brief_data, ContentStates.waiting_for_brief_data)
    dp.message.register(process_brief_edit, ContentStates.waiting_for_brief_edit)
    dp.message.register(process_live_content, ContentStates.waiting_for_live_link)
    dp.message.register(process_voice_content, ContentStates.waiting_for_voice_topic)
    dp.message.register(process_post_lot, ContentStates.waiting_for_post_lot)
    dp.message.register(process_post_digest, ContentStates.waiting_for_post_digest_topic)
    dp.message.register(process_circle_topic, ContentStates.waiting_for_circle_topic)
