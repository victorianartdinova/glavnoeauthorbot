"""
Обработчик мемов — /meme
"""
from aiogram import types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime

from utils.meme_sources import get_top_references, format_reference_preview, get_reference_by_index
from utils.content_journal import add_entry
from utils.client_context import load_client_context, get_client_prompt
from utils.claude_api import generate_content


class MemeStates(StatesGroup):
    """Состояния для мемов"""
    waiting_for_reference_choice = State()  # Выбор референса


def get_references_keyboard(count: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора референса"""
    buttons = []

    for i in range(1, count + 1):
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ Выбрать #{i}",
                callback_data=f"meme_select_{i}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔄 Другие референсы", callback_data="meme_refresh"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="meme_cancel")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_meme_save_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после генерации мема"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💾 Сохранить в журнал", callback_data="meme_save"),
            InlineKeyboardButton(text="🔄 Другой мем", callback_data="meme_refresh"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="meme_cancel")]
    ])


async def cmd_meme(message: types.Message, state: FSMContext):
    """Команда /meme — генерация мема из референсов"""
    data = await state.get_data()
    client = data.get("current_client")

    if not client:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    # Получаем референсы
    references = get_top_references(n=3, days=7)

    if not references:
        await message.answer(
            "😢 Нет подходящих референсов для мемов.\n\n"
            "Возможные причины:\n"
            "• Парсер не собрал посты за последние 7 дней\n"
            "• Нет постов, подходящих под критерии мемогенности"
        )
        return

    # Сохраняем референсы в state
    await state.update_data(meme_references=references)

    # Формируем превью
    preview_lines = ["😂 *Выбери референс для мема:*\n"]

    for i, ref in enumerate(references, 1):
        preview_lines.append(format_reference_preview(ref, i))
        preview_lines.append("")

    await message.answer(
        "\n".join(preview_lines),
        parse_mode="Markdown",
        reply_markup=get_references_keyboard(len(references))
    )
    await state.set_state(MemeStates.waiting_for_reference_choice)


async def callback_meme_select(callback: CallbackQuery, state: FSMContext):
    """Выбор референса для мема"""
    data = await state.get_data()
    client = data.get("current_client")
    references = data.get("meme_references", [])

    index = int(callback.data.replace("meme_select_", ""))
    reference = get_reference_by_index(references, index)

    if not reference:
        await callback.answer("❌ Референс не найден")
        return

    await callback.answer("⏳ Генерирую мем...")

    # Загружаем контекст клиента
    client_context = load_client_context(client)

    # Генерируем мем
    system_prompt = f"""Ты — креативный SMM-специалист агентства недвижимости.
Твоя задача — адаптировать популярный мем/пост под тематику недвижимости.

КОНТЕКСТ КЛИЕНТА:
{get_client_prompt(client)}

ЦЕЛЕВАЯ АУДИТОРИЯ:
- Покупатели недвижимости премиум-сегмента (от 25 млн ₽)
- Москва и МО
- Понимают юмор, ценят самоиронию
- Устали от типичной рекламы

СТИЛЬ:
- Ироничный, но не токсичный
- Связь с болями ЦА (выбор, ипотека, ожидание/реальность)
- Короткий текст (до 200 символов)
- Без прямой рекламы — это именно мем"""

    user_prompt = f"""РЕФЕРЕНС ДЛЯ АДАПТАЦИИ:
{reference.get('text', '')}

Источник: @{reference.get('channel', 'unknown')}

---

Создай мем для недвижимости на основе этого референса.

ФОРМАТ ОТВЕТА:

МЕМНЫЙ ПОСТ
[Текст поста для канала — до 200 символов, ироничный, связан с недвижимостью]

---

ТЗ ДИЗАЙНЕРУ

ИДЕЯ: [описание концепции мема в 1-2 предложения]
ТЕКСТ НА КАРТИНКЕ: [короткий текст для визуала, если нужен]
ВИЗУАЛ: [что изобразить, какой стиль — мем-шаблон, фото, иллюстрация]
РЕФЕРЕНС: https://t.me/{reference.get('channel', '')}/{reference.get('message_id', '')}"""

    try:
        meme_content = generate_content(system_prompt, user_prompt)

        # Сохраняем сгенерированный мем
        await state.update_data(
            generated_meme=meme_content,
            meme_reference=reference
        )

        await callback.message.edit_text(
            f"😂 *Мем готов!*\n\n{meme_content}",
            parse_mode="Markdown",
            reply_markup=get_meme_save_keyboard()
        )

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка генерации: {str(e)}"
        )

    await callback.answer()


async def callback_meme_save(callback: CallbackQuery, state: FSMContext):
    """Сохранение мема в журнал"""
    data = await state.get_data()
    client = data.get("current_client")
    meme_content = data.get("generated_meme", "")

    if not meme_content:
        await callback.answer("❌ Нет мема для сохранения")
        return

    # Сохраняем в журнал
    entry_id = add_entry(
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

    await state.set_state(None)
    await callback.answer("Сохранено!")


async def callback_meme_refresh(callback: CallbackQuery, state: FSMContext):
    """Обновить референсы"""
    data = await state.get_data()
    client = data.get("current_client")

    # Получаем новые референсы (с другим offset можно сделать позже)
    references = get_top_references(n=3, days=14)  # Расширяем диапазон

    if not references:
        await callback.answer("😢 Нет других референсов")
        return

    await state.update_data(meme_references=references)

    preview_lines = ["😂 *Выбери референс для мема:*\n"]

    for i, ref in enumerate(references, 1):
        preview_lines.append(format_reference_preview(ref, i))
        preview_lines.append("")

    await callback.message.edit_text(
        "\n".join(preview_lines),
        parse_mode="Markdown",
        reply_markup=get_references_keyboard(len(references))
    )
    await callback.answer()


async def callback_meme_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена генерации мема"""
    await state.set_state(None)
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


def register_handlers(dp: Dispatcher):
    """Регистрация хендлеров мемов"""
    # Команда /meme
    dp.message.register(cmd_meme, Command("meme"))

    # Callbacks
    dp.callback_query.register(
        callback_meme_select,
        F.data.startswith("meme_select_")
    )
    dp.callback_query.register(
        callback_meme_save,
        F.data == "meme_save"
    )
    dp.callback_query.register(
        callback_meme_refresh,
        F.data == "meme_refresh"
    )
    dp.callback_query.register(
        callback_meme_cancel,
        F.data == "meme_cancel"
    )
