"""
Обработчик журнала контента — /journal + пересылка постов
"""
from aiogram import types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime, timedelta

from utils.content_journal import (
    add_entry, load_journal, format_journal_calendar,
    get_week_start, get_entries_by_date, FORMAT_MAP
)


class JournalStates(StatesGroup):
    """Состояния для журнала"""
    waiting_for_format = State()  # Выбор формата при пересылке
    waiting_for_date = State()    # Выбор даты публикации


def get_format_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора формата"""
    buttons = [
        [
            InlineKeyboardButton(text="🏢 Лидген", callback_data="journal_format_lidgen"),
            InlineKeyboardButton(text="📈 Кейс", callback_data="journal_format_case"),
        ],
        [
            InlineKeyboardButton(text="😂 Мем", callback_data="journal_format_meme"),
            InlineKeyboardButton(text="💡 Эксперт", callback_data="journal_format_expert"),
        ],
        [
            InlineKeyboardButton(text="📰 Дайджест", callback_data="journal_format_digest"),
            InlineKeyboardButton(text="📱 Live", callback_data="journal_format_live"),
        ],
        [
            InlineKeyboardButton(text="🎙 Кружок", callback_data="journal_format_circle"),
            InlineKeyboardButton(text="🎤 Подкаст", callback_data="journal_format_podcast"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="journal_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_date_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора даты"""
    today = datetime.now()
    buttons = [
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="journal_date_today"),
            InlineKeyboardButton(text="📅 Вчера", callback_data="journal_date_yesterday"),
        ],
        [
            InlineKeyboardButton(text="📅 Выбрать дату", callback_data="journal_date_custom"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="journal_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_week_nav_keyboard(week_start: datetime) -> InlineKeyboardMarkup:
    """Клавиатура навигации по неделям"""
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    buttons = [
        [
            InlineKeyboardButton(
                text="⬅️ Пред. неделя",
                callback_data=f"journal_week_{prev_week.strftime('%Y-%m-%d')}"
            ),
            InlineKeyboardButton(
                text="След. неделя ➡️",
                callback_data=f"journal_week_{next_week.strftime('%Y-%m-%d')}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📆 Текущая неделя",
                callback_data="journal_week_current"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def cmd_journal(message: types.Message, state: FSMContext):
    """Команда /journal — показать журнал контента"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    week_start = get_week_start()
    calendar_text = format_journal_calendar(client, week_start)

    await message.answer(
        calendar_text,
        parse_mode="Markdown",
        reply_markup=get_week_nav_keyboard(week_start)
    )


async def callback_journal_week(callback: CallbackQuery, state: FSMContext):
    """Навигация по неделям"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("⚠️ Сначала выбери клиента")
        return

    callback_data = callback.data

    if callback_data == "journal_week_current":
        week_start = get_week_start()
    else:
        # journal_week_YYYY-MM-DD
        date_str = callback_data.replace("journal_week_", "")
        week_start = datetime.strptime(date_str, "%Y-%m-%d")

    calendar_text = format_journal_calendar(client, week_start)

    await callback.message.edit_text(
        calendar_text,
        parse_mode="Markdown",
        reply_markup=get_week_nav_keyboard(week_start)
    )
    await callback.answer()


async def handle_forwarded_post(message: types.Message, state: FSMContext):
    """Обработка пересланного поста"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    # Сохраняем текст поста
    post_text = message.text or message.caption or ""

    if not post_text:
        await message.answer("⚠️ Не удалось получить текст поста")
        return

    await state.update_data(forwarded_post_text=post_text)

    await message.answer(
        "📝 *Сохранение в журнал*\n\n"
        "Выбери формат поста:",
        parse_mode="Markdown",
        reply_markup=get_format_keyboard()
    )
    await state.set_state(JournalStates.waiting_for_format)


async def callback_journal_format(callback: CallbackQuery, state: FSMContext):
    """Выбор формата поста"""
    format_type = callback.data.replace("journal_format_", "")

    await state.update_data(forwarded_post_format=format_type)
    await callback.answer()

    format_name = FORMAT_MAP.get(format_type, format_type)

    await callback.message.edit_text(
        f"✅ Формат: *{format_name}*\n\n"
        "Выбери дату публикации:",
        parse_mode="Markdown",
        reply_markup=get_date_keyboard()
    )
    await state.set_state(JournalStates.waiting_for_date)


async def callback_journal_date(callback: CallbackQuery, state: FSMContext):
    """Выбор даты публикации"""
    data = await state.get_data()
    client = data.get("current_client")
    post_text = data.get("forwarded_post_text", "")
    format_type = data.get("forwarded_post_format", "")

    date_choice = callback.data.replace("journal_date_", "")

    if date_choice == "today":
        pub_date = datetime.now().strftime("%Y-%m-%d")
    elif date_choice == "yesterday":
        pub_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        # TODO: calendar picker
        pub_date = datetime.now().strftime("%Y-%m-%d")

    # Сохраняем в журнал
    entry_id = add_entry(
        client_slug=client,
        date=pub_date,
        format_type=format_type,
        text=post_text,
        status="published",
        source="forwarded"
    )

    format_name = FORMAT_MAP.get(format_type, format_type)
    date_display = datetime.strptime(pub_date, "%Y-%m-%d").strftime("%d.%m.%Y")

    await callback.message.edit_text(
        f"✅ *Сохранено в журнал*\n\n"
        f"📅 Дата: {date_display}\n"
        f"📝 Формат: {format_name}\n"
        f"📄 Текст: {post_text[:100]}...",
        parse_mode="Markdown"
    )

    await state.set_state(None)
    await callback.answer("Сохранено!")


async def callback_journal_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена операции с журналом"""
    await state.set_state(None)
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


def register_handlers(dp: Dispatcher):
    """Регистрация хендлеров журнала"""
    # Команда /journal
    dp.message.register(cmd_journal, Command("journal"))

    # Пересланные сообщения (только если есть forward_date)
    dp.message.register(
        handle_forwarded_post,
        F.forward_date,
        ~F.text.startswith("/")
    )

    # Callbacks
    dp.callback_query.register(
        callback_journal_week,
        F.data.startswith("journal_week_")
    )
    dp.callback_query.register(
        callback_journal_format,
        F.data.startswith("journal_format_")
    )
    dp.callback_query.register(
        callback_journal_date,
        F.data.startswith("journal_date_")
    )
    dp.callback_query.register(
        callback_journal_cancel,
        F.data == "journal_cancel"
    )
