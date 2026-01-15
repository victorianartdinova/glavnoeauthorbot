"""
Leadgen Cards Handler — генерация лидген-постов с ТЗ на карусель
"""
import json
import asyncio
from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.leadgen_cards import (
    generate_leadgen_cards,
    validate_leadgen_input,
    EXAMPLE_INPUT
)
from utils.client_context import get_client_prompt
from utils.text_parser import parse_leadgen_text, ask_missing_fields
from utils.anti_spam import should_show_warning


class LeadgenCardsStates(StatesGroup):
    waiting_for_json = State()
    waiting_for_missing_data = State()

# Хранилище активных задач генерации (user_id -> asyncio.Task)
_active_tasks = {}


def get_leadgen_cards_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после генерации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="lc:regen"),
            InlineKeyboardButton(text="🎨 Дизайн", callback_data="lc:design"),
        ],
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="lc:done"),
        ],
    ])


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура старта"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Показать пример JSON", callback_data="lc:example")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="lc:cancel")],
    ])


async def cmd_leadgen_cards(message: types.Message, state: FSMContext):
    """Команда /leadgen_cards — генерация лидген-поста с карточками"""
    data = await state.get_data()
    client_slug = data.get("current_client")
    user_id = message.from_user.id

    if not client_slug:
        # Anti-spam: показываем предупреждение макс. раз в 60 сек
        if should_show_warning(user_id, "leadgen_no_client"):
            await message.answer("⚠️ Сначала выбери клиента")
        return

    await state.update_data(lc_client=client_slug)

    text = """📦 *Лидген-пост + ТЗ на карточки*

Отправь данные о проектах — в свободной форме.

Например:
```
ALIA
м. Спартак, 5 мин
Первый взнос: 8 млн
- Набережная Москвы-реки
- Сформированный район
https://presentation...

Upside Towers
м. Бутырская, 5 мин
ПВ от 40%
...
```

Бот сам распарсит и спросит, если чего-то не хватает."""

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_start_keyboard()
    )
    await state.set_state(LeadgenCardsStates.waiting_for_json)


async def callback_show_example(callback: types.CallbackQuery, state: FSMContext):
    """Показать пример JSON"""
    example_json = json.dumps(EXAMPLE_INPUT, ensure_ascii=False, indent=2)

    # Telegram ограничение — 4096 символов
    if len(example_json) > 3500:
        example_json = example_json[:3500] + "\n..."

    await callback.message.answer(
        f"📋 *Пример входных данных:*\n\n```json\n{example_json}\n```",
        parse_mode="Markdown"
    )
    await callback.answer()


async def callback_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена"""
    user_id = callback.from_user.id

    # Отменяем активную задачу если есть
    if user_id in _active_tasks:
        task = _active_tasks[user_id]
        if not task.done():
            task.cancel()
        del _active_tasks[user_id]

    await state.clear()
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


async def callback_done(callback: types.CallbackQuery, state: FSMContext):
    """Готово"""
    await state.clear()
    await callback.message.answer("✅ Готово! Используй текст и ТЗ.")
    await callback.answer()


async def callback_regen(callback: types.CallbackQuery, state: FSMContext):
    """Перегенерация"""
    data = await state.get_data()
    last_json = data.get("lc_last_json")

    if not last_json:
        await callback.answer("Нет данных для перегенерации", show_alert=True)
        return

    await callback.message.answer("🔄 Перегенерирую...")
    await process_json_input_internal(callback.message, state, last_json, is_regen=True)
    await callback.answer()


async def process_json_input(message: types.Message, state: FSMContext):
    """Обработка текста/JSON от пользователя"""
    text = message.text.strip()

    # Пытаемся сначала распарсить как JSON (обратная совместимость)
    input_json = None
    try:
        # Убираем markdown code block если есть
        clean_text = text
        if text.startswith("```"):
            clean_text = text.strip("`")
            if clean_text.startswith("json"):
                clean_text = clean_text[4:]
            clean_text = clean_text.strip()

        input_json = json.loads(clean_text)
    except json.JSONDecodeError:
        # Не JSON — парсим как текст
        parsed = parse_leadgen_text(text)

        # Проверяем, хватает ли данных
        missing = ask_missing_fields(parsed)

        if missing and len(missing) <= 3:
            # Не хватает 1-3 полей — спрашиваем
            await state.update_data(lc_parsed=parsed, lc_missing=missing, lc_missing_index=0)
            await message.answer(
                f"📝 Почти всё понял! Уточни:\n\n{missing[0]}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⏭ Пропустить", callback_data="lc:skip_missing")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="lc:cancel")]
                ])
            )
            await state.set_state(LeadgenCardsStates.waiting_for_missing_data)
            return

        # Преобразуем в структуру для генерации
        input_json = parsed

    await state.update_data(lc_last_json=input_json)
    await process_json_input_internal(message, state, input_json)


async def process_json_input_internal(
    message: types.Message,
    state: FSMContext,
    input_json: dict,
    is_regen: bool = False
):
    """Внутренняя обработка JSON с таймаутом"""
    data = await state.get_data()
    client_slug = data.get("lc_client") or data.get("current_client")
    user_id = message.from_user.id

    # Валидация
    is_valid, error, _ = validate_leadgen_input(input_json)
    if not is_valid:
        await message.answer(
            f"❌ *Ошибка валидации:*\n{error}",
            parse_mode="Markdown",
            reply_markup=get_start_keyboard()
        )
        return

    # Получаем контекст клиента
    client_context = ""
    if client_slug:
        try:
            client_context = get_client_prompt(client_slug)
        except:
            pass

    # Генерируем с таймаутом
    status_msg = await message.answer("⏳ Генерирую пост и ТЗ на карточки...")

    try:
        # Создаём задачу с таймаутом 120 сек
        task = asyncio.create_task(generate_leadgen_cards(
            input_json=input_json,
            client_context=client_context,
            client_slug=client_slug
        ))
        _active_tasks[user_id] = task

        result = await asyncio.wait_for(task, timeout=120.0)

        if user_id in _active_tasks:
            del _active_tasks[user_id]

    except asyncio.TimeoutError:
        if user_id in _active_tasks:
            del _active_tasks[user_id]
        await message.answer(
            "⏱ Генерация заняла слишком много времени. Попробуй упростить данные или повтори позже."
        )
        return
    except asyncio.CancelledError:
        await message.answer("❌ Генерация отменена")
        return
    except Exception as e:
        if user_id in _active_tasks:
            del _active_tasks[user_id]
        await message.answer(f"❌ Ошибка генерации: {str(e)}")
        return

    if not result["success"]:
        await message.answer(
            f"❌ *Ошибка генерации:*\n{result['error']}",
            parse_mode="Markdown",
            reply_markup=get_start_keyboard()
        )
        return

    # Отправляем результат
    # 1. Текст поста
    post_text = result["post_text"]
    await message.answer(
        f"✅ *ТЕКСТ ПОСТА*\n\n{post_text}",
        parse_mode="Markdown"
    )

    # 2. ТЗ на карточки (может быть длинным)
    cards_brief = result["cards_brief"]

    # Разбиваем на части если длинное
    if len(cards_brief) > 4000:
        chunks = split_text(cards_brief, 4000)
        await message.answer("🧩 *ТЗ НА КАРТОЧКИ*", parse_mode="Markdown")
        for i, chunk in enumerate(chunks):
            await message.answer(f"```\n{chunk}\n```", parse_mode="Markdown")
    else:
        await message.answer(
            f"🧩 *ТЗ НА КАРТОЧКИ*\n\n```\n{cards_brief}\n```",
            parse_mode="Markdown"
        )

    # 3. Блок ссылок + кнопки
    links = result["links_summary"]

    # Сохраняем данные для кнопки "Дизайн"
    await state.update_data(
        lc_last_brief=cards_brief,
        lc_last_post=post_text,
        lc_client=client_slug
    )

    await message.answer(
        f"{links}",
        reply_markup=get_leadgen_cards_keyboard()
    )


def split_text(text: str, max_len: int) -> list:
    """Разбить текст на части"""
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Ищем последний перенос строки до лимита
        split_pos = text.rfind("\n", 0, max_len)
        if split_pos == -1:
            split_pos = max_len
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


async def callback_design(callback: types.CallbackQuery, state: FSMContext):
    """Отправка ТЗ дизайнеру"""
    from utils.team_chat import send_brief_to_designer

    data = await state.get_data()
    brief = data.get("lc_last_brief", "")
    client_slug = data.get("lc_client") or data.get("current_client")

    if not brief:
        await callback.answer("ТЗ не найдено. Сгенерируй сначала карточки.", show_alert=True)
        return

    if not client_slug:
        await callback.answer("Клиент не выбран", show_alert=True)
        return

    # Отправляем в team chat
    bot = callback.message.bot
    success = await send_brief_to_designer(bot, client_slug, brief)

    if success:
        await callback.message.answer("✅ ТЗ отправлено дизайнеру в командный чат")
    else:
        # Если не удалось — показываем пользователю
        await callback.message.answer(f"📋 *ТЗ для дизайнера:*\n\n```\n{brief}\n```", parse_mode="Markdown")

    await callback.answer()


def register_handlers(dp: Dispatcher):
    """Регистрация хендлеров"""
    # Команда
    dp.message.register(cmd_leadgen_cards, Command("leadgen_cards"))

    # Callbacks
    dp.callback_query.register(callback_show_example, F.data == "lc:example")
    dp.callback_query.register(callback_cancel, F.data == "lc:cancel")
    dp.callback_query.register(callback_done, F.data == "lc:done")
    dp.callback_query.register(callback_regen, F.data == "lc:regen")
    dp.callback_query.register(callback_design, F.data == "lc:design")

    # State handler
    dp.message.register(process_json_input, LeadgenCardsStates.waiting_for_json)
