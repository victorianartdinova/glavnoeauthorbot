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
    get_week_start, get_entries_by_date, get_entries_by_week,
    clear_day, clear_week, fill_week_from_plan, get_week_stats,
    FORMAT_MAP
)
from utils.history_index import find_similar_entries, get_stats, build_history_index


class JournalStates(StatesGroup):
    """Состояния для журнала"""
    waiting_for_format = State()  # Выбор формата при пересылке
    waiting_for_date = State()    # Выбор даты публикации
    # Ручное добавление
    waiting_for_manual_format = State()
    waiting_for_manual_topic = State()
    waiting_for_manual_date = State()
    waiting_for_custom_date = State()  # Ввод даты вручную
    # Управление журналом
    waiting_for_edit_day_formats = State()  # Ввод форматов для дня


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
    week_str = week_start.strftime('%Y-%m-%d')

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
        ],
        [
            InlineKeyboardButton(
                text="➕ Добавить пост",
                callback_data="journal_add_manual"
            ),
        ],
        # Кнопки управления
        [
            InlineKeyboardButton(
                text="✏️ Изменить день",
                callback_data=f"journal_edit_day_{week_str}"
            ),
            InlineKeyboardButton(
                text="🗑 Очистить день",
                callback_data=f"journal_clear_day_{week_str}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🧹 Очистить неделю",
                callback_data=f"journal_clear_week_{week_str}"
            ),
            InlineKeyboardButton(
                text="📥 Заполнить из плана",
                callback_data=f"journal_fill_week_{week_str}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔍 Похожие за 30 дней",
                callback_data="journal_similar"
            ),
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="journal_stats"
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


# =============================================================================
# РУЧНОЕ ДОБАВЛЕНИЕ ПОСТА
# =============================================================================

def get_manual_format_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора формата для ручного добавления"""
    buttons = [
        [
            InlineKeyboardButton(text="🏢 Лидген", callback_data="manual_format_lidgen"),
            InlineKeyboardButton(text="📈 Кейс", callback_data="manual_format_case"),
        ],
        [
            InlineKeyboardButton(text="😂 Мем", callback_data="manual_format_meme"),
            InlineKeyboardButton(text="💡 Эксперт", callback_data="manual_format_expert"),
        ],
        [
            InlineKeyboardButton(text="📰 Дайджест", callback_data="manual_format_digest"),
            InlineKeyboardButton(text="📱 Live", callback_data="manual_format_live"),
        ],
        [
            InlineKeyboardButton(text="🎙 Кружок", callback_data="manual_format_circle"),
            InlineKeyboardButton(text="🎤 Подкаст", callback_data="manual_format_podcast"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="journal_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manual_date_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора даты для ручного добавления"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="manual_date_today"),
            InlineKeyboardButton(text="📅 Вчера", callback_data="manual_date_yesterday"),
        ],
        [
            InlineKeyboardButton(text="✏️ Ввести дату", callback_data="manual_date_custom"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="journal_cancel")]
    ])


async def callback_journal_add_manual(callback: CallbackQuery, state: FSMContext):
    """Начало ручного добавления поста"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    await callback.message.edit_text(
        "➕ *Добавить пост в журнал*\n\n"
        "Выбери формат:",
        parse_mode="Markdown",
        reply_markup=get_manual_format_keyboard()
    )
    await state.set_state(JournalStates.waiting_for_manual_format)
    await callback.answer()


async def callback_manual_format(callback: CallbackQuery, state: FSMContext):
    """Выбор формата при ручном добавлении"""
    format_type = callback.data.replace("manual_format_", "")
    await state.update_data(manual_format=format_type)

    format_name = FORMAT_MAP.get(format_type, format_type)

    await callback.message.edit_text(
        f"✅ Формат: *{format_name}*\n\n"
        "Напиши тему или краткое описание поста:",
        parse_mode="Markdown"
    )
    await state.set_state(JournalStates.waiting_for_manual_topic)
    await callback.answer()


async def process_manual_topic(message: types.Message, state: FSMContext):
    """Обработка темы поста"""
    topic = message.text
    await state.update_data(manual_topic=topic)

    data = await state.get_data()
    format_type = data.get("manual_format", "")
    format_name = FORMAT_MAP.get(format_type, format_type)

    await message.answer(
        f"✅ Формат: *{format_name}*\n"
        f"✅ Тема: {topic[:50]}{'...' if len(topic) > 50 else ''}\n\n"
        "Выбери дату публикации:",
        parse_mode="Markdown",
        reply_markup=get_manual_date_keyboard()
    )
    await state.set_state(JournalStates.waiting_for_manual_date)


async def callback_manual_date(callback: CallbackQuery, state: FSMContext):
    """Выбор даты при ручном добавлении"""
    date_choice = callback.data.replace("manual_date_", "")

    if date_choice == "custom":
        await callback.message.edit_text(
            "✏️ Введи дату в формате *ДД.ММ* или *ДД.ММ.ГГГГ*\n\n"
            "Примеры: `15.01` или `15.01.2026`",
            parse_mode="Markdown"
        )
        await state.set_state(JournalStates.waiting_for_custom_date)
        await callback.answer()
        return

    if date_choice == "today":
        pub_date = datetime.now().strftime("%Y-%m-%d")
    elif date_choice == "yesterday":
        pub_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        pub_date = datetime.now().strftime("%Y-%m-%d")

    await save_manual_entry(callback.message, state, pub_date)
    await callback.answer("Сохранено!")


async def process_custom_date(message: types.Message, state: FSMContext):
    """Обработка ввода даты вручную"""
    import re

    text = message.text.strip()
    today = datetime.now()

    # Паттерны: ДД.ММ.ГГГГ или ДД.ММ или ДД
    match_full = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', text)
    match_short = re.match(r'^(\d{1,2})\.(\d{1,2})$', text)
    match_day = re.match(r'^(\d{1,2})$', text)

    try:
        if match_full:
            day, month, year = int(match_full.group(1)), int(match_full.group(2)), int(match_full.group(3))
            pub_date = datetime(year, month, day).strftime("%Y-%m-%d")
        elif match_short:
            day, month = int(match_short.group(1)), int(match_short.group(2))
            pub_date = datetime(today.year, month, day).strftime("%Y-%m-%d")
        elif match_day:
            day = int(match_day.group(1))
            pub_date = datetime(today.year, today.month, day).strftime("%Y-%m-%d")
        else:
            await message.answer(
                "Неверный формат. Введи дату как *15.01* или *15.01.2026*",
                parse_mode="Markdown"
            )
            return

        await save_manual_entry(message, state, pub_date)

    except ValueError:
        await message.answer(
            "Неверная дата. Проверь число и месяц.",
            parse_mode="Markdown"
        )


async def callback_journal_similar(callback: CallbackQuery, state: FSMContext):
    """Показать похожие записи за 30 дней с примерами постов"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    await callback.answer("Анализирую...")

    # Сначала пересобираем индекс
    build_history_index(client, period_days=30)

    # Получаем статистику
    stats = get_stats(client)

    if not stats or not stats.get("hooks"):
        await callback.message.answer(
            "📭 Нет данных для анализа.\n"
            "Добавь несколько постов в журнал."
        )
        return

    # Загружаем журнал для примеров
    journal = load_journal(client)
    journal_by_id = {e.get("id"): e for e in journal}

    # Формируем отчёт о повторах
    lines = ["🔍 *Анализ контента за 30 дней*\n"]

    # Хуки с примерами
    hooks = stats.get("hooks", {})
    if hooks:
        hooks_map = {
            "financial": "💰 Финансовый",
            "location": "📍 Локация",
            "premium": "👑 Премиум",
            "urgency": "⏰ Срочность",
            "emotional": "❤️ Эмоции",
            "unknown": "❓ Прочее"
        }
        lines.append("*Хуки:*")
        for hook, count in sorted(hooks.items(), key=lambda x: -x[1]):
            name = hooks_map.get(hook, hook)
            warning = " ⚠️" if count >= 3 else ""
            lines.append(f"  {name}: {count}{warning}")

            # Добавляем примеры (до 2 постов)
            examples = _get_examples_by_hook(journal, hook, limit=2)
            for ex in examples:
                text_preview = ex[:40].replace("\n", " ") + "..."
                lines.append(f"    ↳ _{text_preview}_")
        lines.append("")

    # CTA с примерами
    ctas = stats.get("ctas", {})
    if ctas:
        lines.append("*CTA (слова):*")
        for cta, count in sorted(ctas.items(), key=lambda x: -x[1])[:5]:
            warning = " ⚠️" if count >= 2 else ""
            lines.append(f"  «{cta}»: {count}{warning}")
        lines.append("")

    # Углы с примерами
    angles = stats.get("angles", {})
    if angles:
        lines.append("*Углы подачи:*")
        for angle, count in sorted(angles.items(), key=lambda x: -x[1])[:5]:
            if angle == "unknown":
                continue  # Пропускаем unknown в отчёте
            warning = " ⚠️" if count >= 2 else ""
            lines.append(f"  {angle}: {count}{warning}")
        lines.append("")

    # Форматы
    formats = stats.get("formats", {})
    if formats:
        lines.append("*Форматы:*")
        for fmt, count in sorted(formats.items(), key=lambda x: -x[1]):
            lines.append(f"  {fmt}: {count}")

    lines.append("\n⚠️ = использовано часто, избегай повторов")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown"
    )


def _get_examples_by_hook(journal: list, hook_type: str, limit: int = 2) -> list:
    """Получить примеры постов по типу хука"""
    from utils.history_index import extract_hook_type

    examples = []
    for entry in reversed(journal):  # Сначала свежие
        text = entry.get("text", "")
        if text and extract_hook_type(text) == hook_type:
            examples.append(text)
            if len(examples) >= limit:
                break
    return examples


async def callback_journal_stats(callback: CallbackQuery, state: FSMContext):
    """Показать общую статистику журнала"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    await callback.answer()

    journal = load_journal(client)

    if not journal:
        await callback.message.answer("📭 Журнал пуст")
        return

    # Считаем статистику
    total = len(journal)
    published = len([e for e in journal if e.get("status") == "published"])
    planned = len([e for e in journal if e.get("status") == "planned"])

    # По форматам
    formats_count = {}
    for entry in journal:
        fmt = entry.get("format", "unknown")
        formats_count[fmt] = formats_count.get(fmt, 0) + 1

    # Последние 7 дней
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    last_week = [e for e in journal if e.get("date", "") >= week_ago]

    lines = [
        f"📊 *Статистика журнала: {client}*\n",
        f"📝 Всего записей: {total}",
        f"✅ Опубликовано: {published}",
        f"📋 В плане: {planned}",
        f"📅 За 7 дней: {len(last_week)}",
        "",
        "*По форматам:*"
    ]

    for fmt, count in sorted(formats_count.items(), key=lambda x: -x[1]):
        fmt_name = FORMAT_MAP.get(fmt, fmt)
        lines.append(f"  {fmt_name}: {count}")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown"
    )


async def save_manual_entry(message: types.Message, state: FSMContext, pub_date: str):
    """Сохранение записи в журнал"""
    data = await state.get_data()
    client = data.get("current_client")
    format_type = data.get("manual_format", "")
    topic = data.get("manual_topic", "")

    entry_id = add_entry(
        client_slug=client,
        date=pub_date,
        format_type=format_type,
        text=topic,
        status="published",
        source="manual"
    )

    format_name = FORMAT_MAP.get(format_type, format_type)
    date_display = datetime.strptime(pub_date, "%Y-%m-%d").strftime("%d.%m.%Y")

    await message.answer(
        f"✅ *Сохранено в журнал*\n\n"
        f"📅 Дата: {date_display}\n"
        f"📝 Формат: {format_name}\n"
        f"📄 Тема: {topic[:100]}{'...' if len(topic) > 100 else ''}",
        parse_mode="Markdown"
    )

    await state.set_state(None)


# =============================================================================
# УПРАВЛЕНИЕ ЖУРНАЛОМ: Изменить/Очистить день, Очистить/Заполнить неделю
# =============================================================================

def get_days_keyboard(week_start: datetime, action: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора дня недели для действия"""
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons = []
    row = []

    for i in range(7):
        day = week_start + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        label = f"{weekdays_ru[i]} {day.strftime('%d.%m')}"

        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"journal_{action}_select_{date_str}"
        ))

        if len(row) == 4 or i == 6:
            buttons.append(row)
            row = []

    buttons.append([
        InlineKeyboardButton(text="↩️ Назад", callback_data=f"journal_week_{week_start.strftime('%Y-%m-%d')}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def callback_edit_day(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования дня — показать выбор дня"""
    week_str = callback.data.replace("journal_edit_day_", "")
    week_start = datetime.strptime(week_str, "%Y-%m-%d")

    await state.update_data(journal_week_start=week_str)

    await callback.message.edit_text(
        "✏️ *Изменить день*\n\n"
        "Выбери день для редактирования:",
        parse_mode="Markdown",
        reply_markup=get_days_keyboard(week_start, "edit")
    )
    await callback.answer()


async def callback_edit_select_day(callback: CallbackQuery, state: FSMContext):
    """Выбран день для редактирования — показать текущие записи"""
    date_str = callback.data.replace("journal_edit_select_", "")
    data = await state.get_data()
    client = data.get("current_client")
    week_str = data.get("journal_week_start", "")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    await state.update_data(edit_day_date=date_str)

    # Получаем текущие записи
    entries = get_entries_by_date(client, date_str)

    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
    if entries:
        formats_list = ", ".join([e.get("format", "unknown").upper() for e in entries])
        current_text = f"Текущие: {formats_list}"
    else:
        current_text = "Пусто"

    await callback.message.edit_text(
        f"✏️ *Редактирование {date_display}*\n\n"
        f"{current_text}\n\n"
        "Введи новые форматы через запятую:\n"
        "`лидген, кейс, эксперт`\n\n"
        "Или напиши `очистить` чтобы удалить все записи дня.",
        parse_mode="Markdown"
    )
    await state.set_state(JournalStates.waiting_for_edit_day_formats)
    await callback.answer()


async def process_edit_day_formats(message: types.Message, state: FSMContext):
    """Обработка ввода форматов для дня"""
    data = await state.get_data()
    client = data.get("current_client")
    date_str = data.get("edit_day_date", "")
    week_str = data.get("journal_week_start", "")

    if not client or not date_str:
        await message.answer("❌ Ошибка: потеряны данные. Попробуй снова /journal")
        await state.set_state(None)
        return

    text = message.text.strip().lower()

    # Очистка дня
    if text in ["очистить", "clear", "удалить"]:
        deleted = clear_day(client, date_str)
        date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
        await message.answer(f"🗑 Удалено записей за {date_display}: {deleted}")
    else:
        # Парсим форматы
        format_aliases = {
            "лидген": "lidgen", "lidgen": "lidgen", "лид": "lidgen",
            "кейс": "case", "case": "case",
            "мем": "meme", "meme": "meme",
            "эксперт": "expert", "expert": "expert",
            "дайджест": "digest", "digest": "digest",
            "лайв": "live", "live": "live",
            "кружок": "circle", "circle": "circle",
            "подкаст": "podcast", "podcast": "podcast",
        }

        formats = [f.strip() for f in text.split(",") if f.strip()]
        valid_formats = []
        for f in formats:
            normalized = format_aliases.get(f.lower())
            if normalized:
                valid_formats.append(normalized)

        if not valid_formats:
            await message.answer(
                "❌ Не распознаны форматы.\n"
                "Доступные: лидген, кейс, мем, эксперт, дайджест, лайв, кружок, подкаст"
            )
            return

        # Очищаем день и добавляем новые записи
        clear_day(client, date_str)

        for fmt in valid_formats:
            add_entry(
                client_slug=client,
                date=date_str,
                format_type=fmt,
                text=f"[{fmt.upper()}]",
                status="planned",
                source="manual"
            )

        date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")
        formats_display = ", ".join([FORMAT_MAP.get(f, f) for f in valid_formats])
        await message.answer(f"✅ Обновлено {date_display}: {formats_display}")

    # Возвращаемся к журналу
    await state.set_state(None)

    if week_str:
        week_start = datetime.strptime(week_str, "%Y-%m-%d")
        calendar_text = format_journal_calendar(client, week_start)
        await message.answer(
            calendar_text,
            parse_mode="Markdown",
            reply_markup=get_week_nav_keyboard(week_start)
        )


async def callback_clear_day(callback: CallbackQuery, state: FSMContext):
    """Начало очистки дня — показать выбор дня"""
    week_str = callback.data.replace("journal_clear_day_", "")
    week_start = datetime.strptime(week_str, "%Y-%m-%d")

    await state.update_data(journal_week_start=week_str)

    await callback.message.edit_text(
        "🗑 *Очистить день*\n\n"
        "Выбери день для очистки:",
        parse_mode="Markdown",
        reply_markup=get_days_keyboard(week_start, "clearday")
    )
    await callback.answer()


async def callback_clear_day_select(callback: CallbackQuery, state: FSMContext):
    """Выбран день для очистки — удаляем записи"""
    date_str = callback.data.replace("journal_clearday_select_", "")
    data = await state.get_data()
    client = data.get("current_client")
    week_str = data.get("journal_week_start", "")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    deleted = clear_day(client, date_str)
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m")

    await callback.answer(f"Удалено: {deleted}")

    # Обновляем календарь
    if week_str:
        week_start = datetime.strptime(week_str, "%Y-%m-%d")
    else:
        week_start = get_week_start()

    calendar_text = format_journal_calendar(client, week_start)
    await callback.message.edit_text(
        calendar_text,
        parse_mode="Markdown",
        reply_markup=get_week_nav_keyboard(week_start)
    )


async def callback_clear_week(callback: CallbackQuery, state: FSMContext):
    """Очистка недели — запрос подтверждения"""
    week_str = callback.data.replace("journal_clear_week_", "")
    week_start = datetime.strptime(week_str, "%Y-%m-%d")

    await state.update_data(journal_week_start=week_str)

    week_display = f"{week_start.strftime('%d.%m')} — {(week_start + timedelta(days=6)).strftime('%d.%m')}"

    await callback.message.edit_text(
        f"🧹 *Очистить неделю {week_display}?*\n\n"
        "Все записи будут удалены!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, очистить", callback_data=f"journal_clear_week_confirm_{week_str}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"journal_week_{week_str}"),
            ]
        ])
    )
    await callback.answer()


async def callback_clear_week_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение очистки недели"""
    week_str = callback.data.replace("journal_clear_week_confirm_", "")
    week_start = datetime.strptime(week_str, "%Y-%m-%d")

    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    deleted = clear_week(client, week_start)
    await callback.answer(f"Удалено: {deleted}")

    calendar_text = format_journal_calendar(client, week_start)
    await callback.message.edit_text(
        calendar_text,
        parse_mode="Markdown",
        reply_markup=get_week_nav_keyboard(week_start)
    )


async def callback_fill_week(callback: CallbackQuery, state: FSMContext):
    """Заполнить неделю из контент-плана"""
    week_str = callback.data.replace("journal_fill_week_", "")
    week_start = datetime.strptime(week_str, "%Y-%m-%d")

    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Сначала выбери клиента")
        return

    added = fill_week_from_plan(client, week_start)

    if added == -1:
        await callback.answer("Нет контент-плана для этого клиента")
        await callback.message.answer(
            "📭 *Нет контент-плана*\n\n"
            "Сначала создай план командой /plan",
            parse_mode="Markdown"
        )
        return

    if added == 0:
        await callback.answer("Нет постов в плане на эту неделю")
        return

    await callback.answer(f"Добавлено: {added}")

    calendar_text = format_journal_calendar(client, week_start)
    await callback.message.edit_text(
        calendar_text,
        parse_mode="Markdown",
        reply_markup=get_week_nav_keyboard(week_start)
    )


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

    # Анализ и статистика
    dp.callback_query.register(
        callback_journal_similar,
        F.data == "journal_similar"
    )
    dp.callback_query.register(
        callback_journal_stats,
        F.data == "journal_stats"
    )

    # Ручное добавление поста
    dp.callback_query.register(
        callback_journal_add_manual,
        F.data == "journal_add_manual"
    )
    dp.callback_query.register(
        callback_manual_format,
        F.data.startswith("manual_format_")
    )
    dp.callback_query.register(
        callback_manual_date,
        F.data.startswith("manual_date_")
    )

    # FSM для ручного добавления
    dp.message.register(
        process_manual_topic,
        JournalStates.waiting_for_manual_topic
    )
    dp.message.register(
        process_custom_date,
        JournalStates.waiting_for_custom_date
    )

    # Управление журналом
    dp.callback_query.register(
        callback_edit_day,
        F.data.startswith("journal_edit_day_")
    )
    dp.callback_query.register(
        callback_edit_select_day,
        F.data.startswith("journal_edit_select_")
    )
    dp.callback_query.register(
        callback_clear_day,
        F.data.startswith("journal_clear_day_")
    )
    dp.callback_query.register(
        callback_clear_day_select,
        F.data.startswith("journal_clearday_select_")
    )
    dp.callback_query.register(
        callback_clear_week_confirm,
        F.data.startswith("journal_clear_week_confirm_")
    )
    dp.callback_query.register(
        callback_clear_week,
        F.data.startswith("journal_clear_week_")
    )
    dp.callback_query.register(
        callback_fill_week,
        F.data.startswith("journal_fill_week_")
    )
    dp.message.register(
        process_edit_day_formats,
        JournalStates.waiting_for_edit_day_formats
    )
