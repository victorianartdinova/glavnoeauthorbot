"""
Handler для "Пакет по лоту" — конвейер генерации лидген-контента
Включается только при ENABLE_PACKAGE_BY_LOT=1
"""
from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
from utils.lot_card_store import (
    create_lot_from_facts, format_lot_for_prompt, get_lot_by_id
)
from utils.client_context import get_client_prompt
from utils.memory_store import get_banned_phrases, format_banned_phrases_for_prompt
from utils.anti_repeat import format_do_not_repeat_for_prompt
from utils.claude_api import generate_content
from utils.team_chat import send_brief_short_to_team


class PackageLotStates(StatesGroup):
    """Состояния FSM для Пакет по лоту"""
    waiting_for_url = State()
    waiting_for_facts = State()
    waiting_for_date = State()  # для записи в план


# === ПРОМПТЫ ===

PACKAGE_SYSTEM_PROMPT = """Ты — копирайтер премиальной недвижимости. Твоя задача — создать ПОЛНЫЙ ПАКЕТ контента для лидген-карусели.

ПРАВИЛА:
1. НЕ указывай название ЖК и застройщика
2. Время до метро: "мин." (не "минут")
3. Все тексты — короткие, для карточек
4. Каждая карточка — 1-2 предложения максимум
5. Заголовки — разных типов (см. ниже)

СТРУКТУРА ОТВЕТА:

## ЗАГОЛОВКИ (5 вариантов)
1. [ЦИФРА] — с конкретной цифрой
2. [КОНТРАСТ] — противопоставление
3. [СТРАХ] — что потеряешь
4. [ВЫГОДА] — что получишь
5. [ИНСАЙТ] — неочевидное

## КАРТОЧКИ (6-10 штук)
[1] текст первой карточки
[2] текст второй карточки
...

## CTA (2 варианта)
1. ...
2. ...

## ТЗ ДИЗАЙНЕРУ (SHORT)
ИДЕЯ: одна строка
КОЛ-ВО КАРТОЧЕК: N + ресайз сториз: да/нет
ТЕКСТЫ:
[1] ...
[2] ...
ПЛАШКА: если нужна
"""


def get_package_result_keyboard(lot_id: str) -> InlineKeyboardMarkup:
    """Клавиатура после генерации пакета"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 ТЗ SHORT", callback_data=f"pkg:brief:{lot_id}"),
            InlineKeyboardButton(text="🗓 В план", callback_data=f"pkg:plan:{lot_id}"),
        ],
        [
            InlineKeyboardButton(text="🔁 Ещё 3 заголовка", callback_data=f"pkg:more_titles:{lot_id}"),
            InlineKeyboardButton(text="🔄 Перегенерировать", callback_data=f"pkg:regen:{lot_id}"),
        ],
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="pkg:done"),
        ],
    ])


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Стартовая клавиатура"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без URL (только факты)", callback_data="pkg:skip_url")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="pkg:cancel")],
    ])


async def cmd_package_by_lot(message: types.Message, state: FSMContext):
    """Команда 📦 Пакет по лоту"""
    data = await state.get_data()
    client_slug = data.get("current_client")

    if not client_slug:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    await state.update_data(pkg_client=client_slug)

    await message.answer(
        "📦 *Пакет по лоту*\n\n"
        "Отправь ссылку на проект \\(или пропусти\\)\\.\n\n"
        "Потом я спрошу факты \\— и сгенерирую:\n"
        "• 6\\-10 карточек\n"
        "• 5 заголовков\n"
        "• 2 CTA\n"
        "• Короткое ТЗ дизайнеру",
        parse_mode="MarkdownV2",
        reply_markup=get_start_keyboard()
    )
    await state.set_state(PackageLotStates.waiting_for_url)


async def callback_skip_url(callback: types.CallbackQuery, state: FSMContext):
    """Пропуск URL"""
    await state.update_data(pkg_url="")
    await callback.message.edit_text(
        "📝 *Отправь факты о лоте*\n\n"
        "Формат \\(буллетами\\):\n"
        "```\n"
        "Название проекта\n"
        "\\- УТП 1\n"
        "\\- УТП 2\n"
        "\\- УТП 3\n"
        "Цена: от 25 млн\n"
        "Платёж: 150 тыс/мес\n"
        "Метро: 5 мин до Спартак\n"
        "```",
        parse_mode="MarkdownV2"
    )
    await state.set_state(PackageLotStates.waiting_for_facts)
    await callback.answer()


async def callback_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена"""
    await state.clear()
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


async def process_url(message: types.Message, state: FSMContext):
    """Обработка URL"""
    url = message.text.strip()

    # Простая валидация
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "⚠️ Это не похоже на ссылку\\. Отправь URL или нажми *Без URL*",
            parse_mode="MarkdownV2",
            reply_markup=get_start_keyboard()
        )
        return

    await state.update_data(pkg_url=url)
    await message.answer(
        "✅ URL сохранён\\!\n\n"
        "📝 Теперь отправь *факты о лоте* \\(буллетами\\):\n"
        "```\n"
        "\\- УТП 1\n"
        "\\- УТП 2\n"
        "Цена: от X млн\n"
        "Платёж: X тыс/мес\n"
        "Метро: X мин до станции\n"
        "```",
        parse_mode="MarkdownV2"
    )
    await state.set_state(PackageLotStates.waiting_for_facts)


async def process_facts(message: types.Message, state: FSMContext):
    """Обработка фактов и генерация пакета"""
    facts_text = message.text.strip()

    if len(facts_text) < 20:
        await message.answer("⚠️ Слишком мало информации. Добавь больше фактов.")
        return

    data = await state.get_data()
    client_slug = data.get("pkg_client") or data.get("current_client")
    url = data.get("pkg_url", "")

    # Сохраняем лот
    lot = create_lot_from_facts(
        client_slug=client_slug,
        url=url,
        facts_text=facts_text
    )

    await state.update_data(pkg_lot_id=lot["lot_id"], pkg_lot=lot)

    # Генерируем пакет
    await message.answer("⏳ Генерирую пакет контента...")

    try:
        package = await generate_package(client_slug, lot)
        await state.update_data(pkg_result=package)

        # Отправляем результат
        await send_package_result(message, lot, package)

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {str(e)}")
        return

    await state.set_state(None)


async def generate_package(client_slug: str, lot: dict) -> dict:
    """
    Генерация полного пакета контента.

    Returns:
        {
            "titles": [...],  # 5 заголовков
            "cards": [...],   # 6-10 карточек
            "ctas": [...],    # 2 CTA
            "brief_short": str  # Короткое ТЗ
        }
    """
    # Собираем контекст
    lot_context = format_lot_for_prompt(lot)

    # Клиентский контекст
    try:
        client_context = get_client_prompt(client_slug)
    except:
        client_context = ""

    # Антиповторы
    anti_repeat = format_do_not_repeat_for_prompt(client_slug)

    # Бан-фразы
    banned = format_banned_phrases_for_prompt(client_slug)

    user_prompt = f"""{lot_context}

{client_context}

{anti_repeat}

{banned}

Создай ПОЛНЫЙ ПАКЕТ контента для лидген-карусели.
Следуй структуре из системного промпта."""

    response = await generate_content(
        system_prompt=PACKAGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=2500
    )

    # Парсим ответ
    return parse_package_response(response)


def parse_package_response(response: str) -> dict:
    """Парсинг ответа Claude в структуру"""
    result = {
        "titles": [],
        "cards": [],
        "ctas": [],
        "brief_short": "",
        "raw": response
    }

    lines = response.split("\n")
    current_section = None

    for line in lines:
        line_stripped = line.strip()

        # Определяем секцию
        if "ЗАГОЛОВК" in line.upper():
            current_section = "titles"
            continue
        elif "КАРТОЧК" in line.upper():
            current_section = "cards"
            continue
        elif "CTA" in line.upper():
            current_section = "ctas"
            continue
        elif "ТЗ ДИЗАЙНЕР" in line.upper() or "BRIEF" in line.upper():
            current_section = "brief"
            continue

        # Собираем контент секции
        if not line_stripped:
            continue

        if current_section == "titles":
            # Ищем нумерованные заголовки
            if line_stripped and line_stripped[0].isdigit():
                # Убираем номер и скобки типа
                title = line_stripped.split(".", 1)[-1].strip()
                title = title.split("—", 1)[-1].strip() if "—" in title else title
                if title:
                    result["titles"].append(title)

        elif current_section == "cards":
            # Ищем [1], [2] и т.д.
            if line_stripped.startswith("[") and "]" in line_stripped:
                card_text = line_stripped.split("]", 1)[-1].strip()
                if card_text:
                    result["cards"].append(card_text)

        elif current_section == "ctas":
            if line_stripped and line_stripped[0].isdigit():
                cta = line_stripped.split(".", 1)[-1].strip()
                if cta:
                    result["ctas"].append(cta)

        elif current_section == "brief":
            result["brief_short"] += line + "\n"

    result["brief_short"] = result["brief_short"].strip()

    return result


async def send_package_result(message: types.Message, lot: dict, package: dict):
    """Отправка результата пользователю"""
    lot_id = lot.get("lot_id", "")

    # Блок 1: Заголовки
    titles_text = "🎯 *ЗАГОЛОВКИ*\n\n"
    if package["titles"]:
        titles_text += f"*Выбранный:* {package['titles'][0]}\n\n"
        titles_text += "*Альтернативы:*\n"
        for i, title in enumerate(package["titles"][1:5], 2):
            titles_text += f"{i}. {title}\n"
    else:
        titles_text += "_Не удалось распарсить заголовки_\n"

    await message.answer(titles_text, parse_mode="Markdown")

    # Блок 2: Карточки
    cards_text = "🃏 *КАРТОЧКИ*\n\n"
    if package["cards"]:
        for i, card in enumerate(package["cards"][:10], 1):
            cards_text += f"*[{i}]* {card}\n"
    else:
        cards_text += "_Не удалось распарсить карточки_\n"

    await message.answer(cards_text, parse_mode="Markdown")

    # Блок 3: CTA
    cta_text = "📢 *CTA*\n\n"
    if package["ctas"]:
        for i, cta in enumerate(package["ctas"][:2], 1):
            cta_text += f"{i}. {cta}\n"
    else:
        cta_text += "_Не удалось распарсить CTA_\n"

    await message.answer(
        cta_text,
        parse_mode="Markdown",
        reply_markup=get_package_result_keyboard(lot_id)
    )


async def callback_brief_short(callback: types.CallbackQuery, state: FSMContext):
    """Отправка короткого ТЗ дизайнеру"""
    data = await state.get_data()
    package = data.get("pkg_result", {})
    client_slug = data.get("pkg_client") or data.get("current_client")

    brief = package.get("brief_short", "")

    if not brief:
        # Генерируем на лету
        lot = data.get("pkg_lot", {})
        brief = generate_brief_short_from_package(lot, package)

    # Отправляем в командный чат (при флаге ENABLE_BRIEF_SHORT)
    if config.ENABLE_BRIEF_SHORT and client_slug:
        try:
            from aiogram import Bot
            bot = callback.message.bot
            success = await send_brief_short_to_team(bot, client_slug, brief)
            if success:
                await callback.message.answer("✅ ТЗ отправлено в командный чат")
            else:
                await callback.message.answer(f"📋 *ТЗ SHORT:*\n\n{brief}", parse_mode="Markdown")
        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка отправки: {e}\n\n📋 *ТЗ SHORT:*\n\n{brief}", parse_mode="Markdown")
    else:
        # Просто показываем пользователю
        await callback.message.answer(f"📋 *ТЗ SHORT:*\n\n{brief}", parse_mode="Markdown")

    await callback.answer()


def generate_brief_short_from_package(lot: dict, package: dict) -> str:
    """Генерация SHORT ТЗ из пакета"""
    lines = []

    # ИДЕЯ
    if package.get("titles"):
        lines.append(f"ИДЕЯ: {package['titles'][0]}")

    # КОЛ-ВО КАРТОЧЕК
    num_cards = len(package.get("cards", []))
    lines.append(f"КОЛ-ВО КАРТОЧЕК: {num_cards} + ресайз сториз: да")

    # ТЕКСТЫ
    lines.append("ТЕКСТЫ:")
    for i, card in enumerate(package.get("cards", [])[:10], 1):
        lines.append(f"[{i}] {card}")

    # ПЛАШКА
    numbers = lot.get("numbers", {})
    if numbers.get("price"):
        lines.append(f"ПЛАШКА: {numbers['price']}")

    return "\n".join(lines)


def get_plan_date_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора даты для плана"""
    from datetime import datetime, timedelta

    today = datetime.now()
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    buttons = []
    # Сегодня
    buttons.append([
        InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data="pkg:plan_date:today"
        )
    ])

    # Следующие 5 рабочих дней
    row = []
    days_added = 0
    day_offset = 1
    while days_added < 5:
        next_day = today + timedelta(days=day_offset)
        if next_day.weekday() < 5:  # Пн-Пт
            weekday = weekdays_ru[next_day.weekday()]
            row.append(InlineKeyboardButton(
                text=f"{weekday} {next_day.strftime('%d.%m')}",
                callback_data=f"pkg:plan_date:{next_day.strftime('%Y-%m-%d')}"
            ))
            days_added += 1
            if len(row) == 3:
                buttons.append(row)
                row = []
        day_offset += 1

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="pkg:done")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def callback_add_to_plan(callback: types.CallbackQuery, state: FSMContext):
    """Добавление в план — шаг 1: выбор даты"""
    if not config.ENABLE_PLAN_EXPORT:
        await callback.answer("Функция выключена (ENABLE_PLAN_EXPORT=0)", show_alert=True)
        return

    await callback.message.answer(
        "📅 На какую дату добавить в план?",
        reply_markup=get_plan_date_keyboard()
    )
    await state.set_state(PackageLotStates.waiting_for_date)
    await callback.answer()


async def callback_plan_date(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора даты для плана"""
    from datetime import datetime
    from utils.plan_storage import add_post_to_day, load_plan, save_plan

    date_value = callback.data.replace("pkg:plan_date:", "")

    if date_value == "today":
        plan_date = datetime.now().strftime("%Y-%m-%d")
    else:
        plan_date = date_value

    data = await state.get_data()
    client_slug = data.get("pkg_client") or data.get("current_client")
    lot = data.get("pkg_lot", {})
    package = data.get("pkg_result", {})

    # Получаем заголовок
    title = package.get("titles", ["Лидген-карточки"])[0] if package.get("titles") else "Лидген-карточки"
    lot_id = lot.get("lot_id", "")

    # Загружаем текущий план
    plan = load_plan(client_slug)

    if plan:
        # Ищем день с нужной датой
        plan_id = plan.get("plan_id")
        target_day = None
        for day in plan.get("days", []):
            if date_value in day.get("date", "") or day.get("date", "") in plan_date:
                target_day = day
                break

        if target_day:
            # Добавляем пост к существующему дню
            post_id = add_post_to_day(
                client_slug=client_slug,
                plan_id=plan_id,
                day_num=target_day["day"],
                format_type="leadgen_cards",
                topic=title,
                is_ads=False
            )
            if post_id:
                await callback.message.answer(
                    f"✅ Добавлено в план!\n\n"
                    f"📅 Дата: {plan_date}\n"
                    f"📋 Формат: leadgen_cards\n"
                    f"📝 Тема: {title}\n"
                    f"🏷 Лот: {lot_id}"
                )
            else:
                await callback.message.answer("⚠️ Не удалось добавить в план")
        else:
            await callback.message.answer(
                f"⚠️ Нет дня {plan_date} в текущем плане.\n"
                f"Сначала создай план через 📅 Контент-план"
            )
    else:
        await callback.message.answer(
            f"⚠️ Нет активного плана для {client_slug}.\n"
            f"Сначала создай план через 📅 Контент-план"
        )

    await state.set_state(None)
    await callback.answer()


async def callback_more_titles(callback: types.CallbackQuery, state: FSMContext):
    """Генерация ещё 3 заголовков"""
    data = await state.get_data()
    lot = data.get("pkg_lot", {})
    client_slug = data.get("pkg_client") or data.get("current_client")

    await callback.message.answer("⏳ Генерирую ещё заголовки...")

    lot_context = format_lot_for_prompt(lot)

    response = await generate_content(
        system_prompt="Ты — копирайтер. Генерируй только заголовки.",
        user_prompt=f"""{lot_context}

Придумай 3 НОВЫХ заголовка для лидген-карточек.
Используй разные типы: цифра, контраст, выгода.
Формат:
1. ...
2. ...
3. ...""",
        max_tokens=300
    )

    await callback.message.answer(f"🎯 *Ещё заголовки:*\n\n{response}", parse_mode="Markdown")
    await callback.answer()


async def callback_regen(callback: types.CallbackQuery, state: FSMContext):
    """Перегенерация пакета"""
    data = await state.get_data()
    lot = data.get("pkg_lot")
    client_slug = data.get("pkg_client") or data.get("current_client")

    if not lot:
        await callback.answer("Нет данных для перегенерации", show_alert=True)
        return

    await callback.message.answer("🔄 Перегенерирую пакет...")

    try:
        package = await generate_package(client_slug, lot)
        await state.update_data(pkg_result=package)
        await send_package_result(callback.message, lot, package)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

    await callback.answer()


async def callback_done(callback: types.CallbackQuery, state: FSMContext):
    """Завершение"""
    await state.clear()
    await callback.message.answer("✅ Готово! Используй материалы.")
    await callback.answer()


def register_handlers(dp: Dispatcher):
    """Регистрация хендлеров (только если флаг включён)"""
    if not config.ENABLE_PACKAGE_BY_LOT:
        return

    # Callbacks
    dp.callback_query.register(callback_skip_url, F.data == "pkg:skip_url")
    dp.callback_query.register(callback_cancel, F.data == "pkg:cancel")
    dp.callback_query.register(callback_done, F.data == "pkg:done")

    # Callbacks с lot_id
    dp.callback_query.register(
        callback_brief_short,
        F.data.startswith("pkg:brief:")
    )
    dp.callback_query.register(
        callback_add_to_plan,
        F.data.startswith("pkg:plan:") & ~F.data.startswith("pkg:plan_date:")
    )
    dp.callback_query.register(
        callback_plan_date,
        F.data.startswith("pkg:plan_date:")
    )
    dp.callback_query.register(
        callback_more_titles,
        F.data.startswith("pkg:more_titles:")
    )
    dp.callback_query.register(
        callback_regen,
        F.data.startswith("pkg:regen:")
    )

    # State handlers
    dp.message.register(process_url, PackageLotStates.waiting_for_url)
    dp.message.register(process_facts, PackageLotStates.waiting_for_facts)
