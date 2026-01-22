"""
Обработчик фокуса недели — /focus команда для управления приоритетными лотами
"""
from aiogram import types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from utils.memory_store import (
    get_focus_lots, add_focus_lot, remove_focus_lot, clear_focus_lots,
    get_banned_phrases, add_banned_phrase, remove_banned_phrase
)


class FocusStates(StatesGroup):
    """Состояния для работы с фокусом"""
    waiting_for_lot_data = State()  # Ввод данных нового лота
    waiting_for_banned_phrase = State()  # Ввод запрещённой фразы


def get_focus_keyboard(lots: list) -> InlineKeyboardMarkup:
    """Клавиатура управления фокусом"""
    buttons = []

    # Кнопки для каждого лота (удалить)
    for lot in lots[:5]:  # Максимум 5
        lot_name = lot.get("name", "")[:25]
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {lot_name}",
                callback_data=f"focus_del_{lot['id']}"
            )
        ])

    # Кнопки управления
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить лот", callback_data="focus_add"),
    ])

    if lots:
        buttons.append([
            InlineKeyboardButton(text="🗑 Очистить все", callback_data="focus_clear"),
        ])

    buttons.append([
        InlineKeyboardButton(text="🚫 Запрещённые фразы", callback_data="focus_banned"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_banned_keyboard(phrases: list) -> InlineKeyboardMarkup:
    """Клавиатура управления запрещёнными фразами"""
    buttons = []

    # Кнопки для каждой фразы (удалить)
    for phrase in phrases[:5]:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {phrase[:20]}",
                callback_data=f"banned_del_{phrase[:30]}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Добавить фразу", callback_data="banned_add"),
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад к фокусу", callback_data="focus_back"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def cmd_focus(message: types.Message, state: FSMContext):
    """Команда /focus — показать и управлять фокусом недели"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    lots = get_focus_lots(client)

    lines = [f"🎯 *Фокус недели: {client}*\n"]

    if lots:
        lines.append("*Приоритетные лоты:*")
        for i, lot in enumerate(lots, 1):
            price = f" (от {lot['price_from']:,} ₽)".replace(",", " ") if lot.get("price_from") else ""
            features = f" — {', '.join(lot['key_features'])}" if lot.get("key_features") else ""
            lines.append(f"{i}. {lot['name']}{price}{features}")
    else:
        lines.append("📭 Лоты не добавлены")

    lines.append("\n👇 Управление:")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_focus_keyboard(lots)
    )


async def callback_focus_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться к фокусу"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Клиент не выбран")
        return

    lots = get_focus_lots(client)

    lines = [f"🎯 *Фокус недели: {client}*\n"]

    if lots:
        lines.append("*Приоритетные лоты:*")
        for i, lot in enumerate(lots, 1):
            price = f" (от {lot['price_from']:,} ₽)".replace(",", " ") if lot.get("price_from") else ""
            features = f" — {', '.join(lot['key_features'])}" if lot.get("key_features") else ""
            lines.append(f"{i}. {lot['name']}{price}{features}")
    else:
        lines.append("📭 Лоты не добавлены")

    lines.append("\n👇 Управление:")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_focus_keyboard(lots)
    )
    await callback.answer()


async def callback_focus_add(callback: CallbackQuery, state: FSMContext):
    """Начать добавление лота"""
    await callback.message.edit_text(
        "➕ *Добавить лот в фокус*\n\n"
        "Отправь данные лота в формате:\n"
        "`Название ЖК | цена от | особенности`\n\n"
        "Примеры:\n"
        "• `ЖК Легенда | 25000000 | у парка, последние лоты`\n"
        "• `ЖК Река | 18000000 | старт продаж, метро 5 мин`\n"
        "• `ЖК Премиум` (без цены и особенностей тоже ОК)",
        parse_mode="Markdown"
    )
    await state.set_state(FocusStates.waiting_for_lot_data)
    await callback.answer()


async def process_lot_data(message: types.Message, state: FSMContext):
    """Обработка данных нового лота"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Клиент не выбран")
        await state.set_state(None)
        return

    text = message.text.strip()

    # Парсим формат: Название | цена | особенности
    parts = [p.strip() for p in text.split("|")]

    name = parts[0] if parts else text
    price_from = None
    key_features = []

    if len(parts) > 1:
        # Пытаемся распарсить цену
        try:
            price_str = parts[1].replace(" ", "").replace("₽", "")
            price_from = int(price_str)
        except ValueError:
            # Если не число — это особенность
            key_features.append(parts[1])

    if len(parts) > 2:
        # Особенности через запятую
        key_features = [f.strip() for f in parts[2].split(",")]

    # Добавляем лот
    lot_id = add_focus_lot(
        client_slug=client,
        name=name,
        price_from=price_from,
        key_features=key_features if key_features else None,
        priority=len(get_focus_lots(client)) + 1
    )

    await state.set_state(None)

    # Показываем результат
    lots = get_focus_lots(client)

    price_display = f" (от {price_from:,} ₽)".replace(",", " ") if price_from else ""
    features_display = f" — {', '.join(key_features)}" if key_features else ""

    await message.answer(
        f"✅ Лот добавлен:\n"
        f"*{name}*{price_display}{features_display}\n\n"
        f"Всего в фокусе: {len(lots)}",
        parse_mode="Markdown",
        reply_markup=get_focus_keyboard(lots)
    )


async def callback_focus_del(callback: CallbackQuery, state: FSMContext):
    """Удалить лот из фокуса"""
    lot_id = callback.data.replace("focus_del_", "")
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Клиент не выбран")
        return

    success = remove_focus_lot(client, lot_id)

    if success:
        await callback.answer("Лот удалён")
    else:
        await callback.answer("Лот не найден")

    # Обновляем список
    lots = get_focus_lots(client)

    lines = [f"🎯 *Фокус недели: {client}*\n"]

    if lots:
        lines.append("*Приоритетные лоты:*")
        for i, lot in enumerate(lots, 1):
            price = f" (от {lot['price_from']:,} ₽)".replace(",", " ") if lot.get("price_from") else ""
            features = f" — {', '.join(lot['key_features'])}" if lot.get("key_features") else ""
            lines.append(f"{i}. {lot['name']}{price}{features}")
    else:
        lines.append("📭 Лоты не добавлены")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_focus_keyboard(lots)
    )


async def callback_focus_clear(callback: CallbackQuery, state: FSMContext):
    """Очистить все лоты"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Клиент не выбран")
        return

    clear_focus_lots(client)
    await callback.answer("Все лоты удалены")

    await callback.message.edit_text(
        f"🎯 *Фокус недели: {client}*\n\n"
        "📭 Лоты не добавлены\n\n"
        "👇 Управление:",
        parse_mode="Markdown",
        reply_markup=get_focus_keyboard([])
    )


# === ЗАПРЕЩЁННЫЕ ФРАЗЫ ===

async def callback_focus_banned(callback: CallbackQuery, state: FSMContext):
    """Показать запрещённые фразы"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Клиент не выбран")
        return

    phrases = get_banned_phrases(client)

    lines = [f"🚫 *Запрещённые фразы: {client}*\n"]

    if phrases:
        for phrase in phrases:
            lines.append(f"• {phrase}")
    else:
        lines.append("📭 Фразы не добавлены")

    lines.append("\n_Эти фразы НЕ будут использоваться в генерации_")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_banned_keyboard(phrases)
    )
    await callback.answer()


async def callback_banned_add(callback: CallbackQuery, state: FSMContext):
    """Добавить запрещённую фразу"""
    await callback.message.edit_text(
        "🚫 *Добавить запрещённую фразу*\n\n"
        "Напиши фразу, которую НЕ использовать:\n"
        "Например: `уникальный`, `эксклюзивный`, `идеальный`",
        parse_mode="Markdown"
    )
    await state.set_state(FocusStates.waiting_for_banned_phrase)
    await callback.answer()


async def process_banned_phrase(message: types.Message, state: FSMContext):
    """Обработка новой запрещённой фразы"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Клиент не выбран")
        await state.set_state(None)
        return

    phrase = message.text.strip().lower()
    add_banned_phrase(client, phrase)

    await state.set_state(None)

    phrases = get_banned_phrases(client)

    await message.answer(
        f"✅ Фраза добавлена: *{phrase}*\n\n"
        f"Всего запрещённых: {len(phrases)}",
        parse_mode="Markdown",
        reply_markup=get_banned_keyboard(phrases)
    )


async def callback_banned_del(callback: CallbackQuery, state: FSMContext):
    """Удалить запрещённую фразу"""
    phrase = callback.data.replace("banned_del_", "")
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await callback.answer("Клиент не выбран")
        return

    remove_banned_phrase(client, phrase)
    await callback.answer("Фраза удалена")

    phrases = get_banned_phrases(client)

    lines = [f"🚫 *Запрещённые фразы: {client}*\n"]

    if phrases:
        for p in phrases:
            lines.append(f"• {p}")
    else:
        lines.append("📭 Фразы не добавлены")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_banned_keyboard(phrases)
    )


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков фокуса"""
    # Команда /focus
    dp.message.register(cmd_focus, Command("focus"))

    # Callbacks для лотов
    dp.callback_query.register(callback_focus_back, F.data == "focus_back")
    dp.callback_query.register(callback_focus_add, F.data == "focus_add")
    dp.callback_query.register(callback_focus_del, F.data.startswith("focus_del_"))
    dp.callback_query.register(callback_focus_clear, F.data == "focus_clear")

    # Callbacks для запрещённых фраз
    dp.callback_query.register(callback_focus_banned, F.data == "focus_banned")
    dp.callback_query.register(callback_banned_add, F.data == "banned_add")
    dp.callback_query.register(callback_banned_del, F.data.startswith("banned_del_"))

    # FSM
    dp.message.register(process_lot_data, FocusStates.waiting_for_lot_data)
    dp.message.register(process_banned_phrase, FocusStates.waiting_for_banned_phrase)
