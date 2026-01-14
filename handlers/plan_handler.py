"""
Обработчик контент-планов: просмотр, редактирование, действия с днями и постами
"""
from aiogram import types, Dispatcher, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import config
from utils.plan_storage import (
    load_plan, update_post, save_plan, parse_plan_from_text, get_day_display,
    add_post_to_day, delete_post_from_day, get_post_by_id, is_protected_format,
    delete_plan, list_plans
)
from utils.team_chat import send_brief_to_designer, send_post_to_operator
from utils.client_context import get_client_prompt, get_client_designer, get_emoji_prompt_section
from utils.claude_api import generate_content, generate_content_with_memory, validate_lidgen_topic
from utils.markdown_escape import escape_md


class PlanStates(StatesGroup):
    """Состояния для работы с планом"""
    editing_topic = State()           # Редактирование темы поста
    editing_post = State()            # Редактирование текста поста
    editing_brief = State()           # Редактирование ТЗ
    waiting_for_lot_data = State()    # Ожидание данных лота для ТЗ
    adding_post_topic = State()       # Ввод темы нового поста


def get_plan_days_keyboard(plan: dict, show_clear: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура с днями плана (по 4 в ряд)"""
    days = plan.get("days", [])
    buttons = []
    row = []

    for day in days:
        day_num = day["day"]
        # Проверяем статус всех постов дня
        posts = day.get("posts", [])
        all_done = all(p.get("status") == "done" for p in posts) if posts else False
        status_emoji = "✅" if all_done else ""
        posts_count = len(posts)
        btn_text = f"{status_emoji}{day_num}" + (f"({posts_count})" if posts_count > 1 else "")

        row.append(InlineKeyboardButton(
            text=btn_text,
            callback_data=f"plan_day_{day_num}"
        ))

        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Кнопка очистки плана
    if show_clear:
        buttons.append([InlineKeyboardButton(text="🗑 Очистить план", callback_data="plan_clear")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_post_actions_keyboard(day_num: int, post: dict) -> InlineKeyboardMarkup:
    """Клавиатура действий с постом"""
    post_id = post["id"]
    is_protected = post.get("protected", False)

    buttons = [
        [
            InlineKeyboardButton(text="✏️ Тема", callback_data=f"post_edit_topic_{day_num}_{post_id}"),
            InlineKeyboardButton(text="📝 Пост", callback_data=f"post_write_{day_num}_{post_id}"),
            InlineKeyboardButton(text="🎨 ТЗ", callback_data=f"post_brief_{day_num}_{post_id}")
        ]
    ]

    # Кнопка удаления только для незащищённых постов
    if not is_protected:
        buttons.append([
            InlineKeyboardButton(text="🗑 Удалить пост", callback_data=f"post_delete_{day_num}_{post_id}")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_day_view_keyboard(day_num: int, posts: list) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра дня с несколькими постами"""
    buttons = []

    # Кнопки для каждого поста
    for i, post in enumerate(posts):
        post_id = post["id"]
        format_type = post.get("format", "ПОСТ")
        protected_mark = "🔒" if post.get("protected") else ""
        status_mark = "✅" if post.get("status") == "done" else "⏳"

        buttons.append([
            InlineKeyboardButton(
                text=f"{status_mark}{protected_mark} {format_type}: {post.get('topic', '')[:30]}...",
                callback_data=f"post_view_{day_num}_{post_id}"
            )
        ])

    # Кнопка добавления поста
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить пост", callback_data=f"post_add_{day_num}")
    ])

    # Назад к плану
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад к плану", callback_data="plan_back")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_add_post_format_keyboard(day_num: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора формата нового поста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 ПРОГРЕВ", callback_data=f"post_add_format_{day_num}_ПРОГРЕВ")],
        [InlineKeyboardButton(text="📸 ЖИВОЙ", callback_data=f"post_add_format_{day_num}_ЖИВОЙ")],
        [InlineKeyboardButton(text="😄 МЕМ", callback_data=f"post_add_format_{day_num}_МЕМ")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"plan_day_{day_num}")]
    ])


def get_approve_post_keyboard(day_num: int, post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура согласования поста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Согласовать", callback_data=f"post_approve_{day_num}_{post_id}"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_text_{day_num}_{post_id}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"post_view_{day_num}_{post_id}")]
    ])


def get_approve_brief_keyboard(day_num: int, post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура согласования ТЗ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Согласовать", callback_data=f"brief_approve_{day_num}_{post_id}"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"brief_edit_{day_num}_{post_id}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"post_view_{day_num}_{post_id}")]
    ])


async def show_plan_with_days(message: types.Message, client_slug: str, plan_id: str = None):
    """Показать план с кнопками дней"""
    plan = load_plan(client_slug, plan_id)

    if not plan:
        await message.answer("❌ План не найден. Сначала создай план через 📅 Контент-план")
        return

    # Формируем текст плана
    text = f"📅 Контент-план: {client_slug}\n"
    text += f"📆 Создан: {plan.get('created', 'н/д')}\n\n"

    for day in plan.get("days", [])[:7]:  # Показываем первые 7 дней
        posts = day.get("posts", [])
        all_done = all(p.get("status") == "done" for p in posts) if posts else False
        status = "✅" if all_done else "⏳"

        text += f"{status} День {day['day']} ({day['date']}):"

        if len(posts) == 1:
            post = posts[0]
            ads = " 📢" if post.get("is_ads") else ""
            text += f" {post['format']}{ads}\n"
            topic = post['topic'][:45] + "..." if len(post['topic']) > 45 else post['topic']
            text += f"   {topic}\n\n"
        else:
            text += f" ({len(posts)} постов)\n"
            for post in posts:
                protected = "🔒" if post.get("protected") else ""
                topic = post['topic'][:35] + "..." if len(post['topic']) > 35 else post['topic']
                text += f"   {protected}{post['format']}: {topic}\n"
            text += "\n"

    text += "👇 Выбери день для действий:"

    await message.answer(text, reply_markup=get_plan_days_keyboard(plan))


async def callback_plan_day(callback: CallbackQuery, state: FSMContext):
    """Показать день со всеми постами"""
    day_num = int(callback.data.replace("plan_day_", ""))
    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    if not plan:
        await callback.answer("План не найден")
        return

    # Ищем день
    day = None
    for d in plan.get("days", []):
        if d["day"] == day_num:
            day = d
            break

    if not day:
        await callback.answer("День не найден")
        return

    # Сохраняем текущий день
    await state.update_data(current_day_num=day_num)

    posts = day.get("posts", [])

    # Формируем текст
    text = f"📆 День {day_num} ({day['date']}, {day.get('weekday', '')})\n\n"

    for i, post in enumerate(posts, 1):
        protected = "🔒" if post.get("protected") else ""
        ads = " 📢" if post.get("is_ads") else ""
        status = "✅" if post.get("status") == "done" else "⏳"

        text += f"{status} {protected}**{post['format']}**{ads}\n"
        text += f"   {post['topic']}\n\n"

    text += "👇 Выбери пост для действий:"

    await callback.message.edit_text(
        text,
        reply_markup=get_day_view_keyboard(day_num, posts)
    )
    await callback.answer()


async def callback_post_view(callback: CallbackQuery, state: FSMContext):
    """Просмотр конкретного поста"""
    parts = callback.data.replace("post_view_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])  # post_id может содержать _

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await callback.answer("Пост не найден")
        return

    await state.update_data(current_day_num=day_num, current_post_id=post_id)

    protected = "🔒 ЗАЩИЩЁН" if post.get("protected") else ""
    ads = "📢 Для рекламы" if post.get("is_ads") else "📱 Только канал"
    status = "✅ Готово" if post.get("status") == "done" else "⏳ В работе"

    text = f"📋 **{post['format']}** {protected}\n\n"
    text += f"📌 Тема: {post['topic']}\n\n"
    text += f"{ads}\n"
    text += f"Статус: {status}\n\n"
    text += "👇 Выбери действие:"

    await callback.message.edit_text(
        text,
        reply_markup=get_post_actions_keyboard(day_num, post)
    )
    await callback.answer()


async def callback_plan_back(callback: CallbackQuery, state: FSMContext):
    """Назад к списку дней"""
    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    if not plan:
        await callback.answer("План не найден")
        return

    # Формируем текст плана
    text = f"📅 Контент-план: {client_slug}\n\n"

    for day in plan.get("days", [])[:7]:
        posts = day.get("posts", [])
        all_done = all(p.get("status") == "done" for p in posts) if posts else False
        status = "✅" if all_done else "⏳"

        text += f"{status} День {day['day']} ({day['date']}):"

        if len(posts) == 1:
            post = posts[0]
            ads = " 📢" if post.get("is_ads") else ""
            topic = post['topic'][:40] + "..." if len(post['topic']) > 40 else post['topic']
            text += f" {post['format']}{ads}\n   {topic}\n\n"
        else:
            text += f" ({len(posts)} постов)\n"
            for post in posts[:2]:
                topic = post['topic'][:30] + "..." if len(post['topic']) > 30 else post['topic']
                text += f"   • {post['format']}: {topic}\n"
            if len(posts) > 2:
                text += f"   ... и ещё {len(posts) - 2}\n"
            text += "\n"

    text += "👇 Выбери день:"

    await callback.message.edit_text(text, reply_markup=get_plan_days_keyboard(plan))
    await callback.answer()


# === РЕДАКТИРОВАНИЕ ТЕМЫ ===

async def callback_edit_topic(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование темы поста"""
    parts = callback.data.replace("post_edit_topic_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await callback.answer("Пост не найден")
        return

    await state.update_data(editing_day=day_num, editing_post_id=post_id)

    protected_warning = ""
    if post.get("protected"):
        protected_warning = "⚠️ Это ЛИДГЕН-пост. Тема должна быть объектом недвижимости (ЖК, лот, подборка).\n\n"

    await callback.message.answer(
        f"✏️ Редактирование темы\n\n"
        f"Текущая тема: {post['topic']}\n\n"
        f"{protected_warning}"
        "Напиши новую тему:"
    )
    await state.set_state(PlanStates.editing_topic)
    await callback.answer()


async def process_edit_topic(message: types.Message, state: FSMContext):
    """Обработка новой темы"""
    new_topic = message.text
    data = await state.get_data()
    day_num = data.get("editing_day")
    post_id = data.get("editing_post_id")
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await message.answer("Пост не найден")
        await state.set_state(None)
        return

    # Валидация для защищённых постов (ЛИДГЕН)
    if post.get("protected"):
        await message.answer("⏳ Проверяю тему...")

        is_valid, reason = validate_lidgen_topic(new_topic)

        if not is_valid:
            await message.answer(
                f"❌ Тема не подходит для ЛИДГЕН\n\n"
                f"Причина: {reason}\n\n"
                "ЛИДГЕН — это пост про конкретный объект недвижимости.\n"
                "Введи ЖК, лот или подборку объектов:"
            )
            return  # Остаёмся в состоянии редактирования

    # Сохраняем новую тему
    success = update_post(client_slug, plan_id, day_num, post_id, {"topic": new_topic})

    if success:
        await message.answer(f"✅ Тема обновлена:\n{new_topic}")
    else:
        await message.answer("❌ Ошибка сохранения")

    await state.set_state(None)

    # Показываем пост снова
    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)
    if post:
        protected = "🔒" if post.get("protected") else ""
        ads = "📢" if post.get("is_ads") else "📱"
        text = f"📋 **{post['format']}** {protected}\n"
        text += f"📌 Тема: {post['topic']}\n\n"
        text += f"{ads}\n\n"
        text += "👇 Выбери действие:"

        await message.answer(text, reply_markup=get_post_actions_keyboard(day_num, post))


# === ДОБАВЛЕНИЕ ПОСТА ===

async def callback_add_post(callback: CallbackQuery, state: FSMContext):
    """Начать добавление поста к дню"""
    day_num = int(callback.data.replace("post_add_", ""))
    await state.update_data(adding_to_day=day_num)

    await callback.message.edit_text(
        f"➕ Добавить пост к Дню {day_num}\n\n"
        "Выбери формат:",
        reply_markup=get_add_post_format_keyboard(day_num)
    )
    await callback.answer()


async def callback_add_post_format(callback: CallbackQuery, state: FSMContext):
    """Выбран формат нового поста"""
    parts = callback.data.replace("post_add_format_", "").split("_")
    day_num = int(parts[0])
    format_type = "_".join(parts[1:])

    await state.update_data(adding_to_day=day_num, adding_format=format_type)

    await callback.message.answer(
        f"📝 Новый пост: {format_type}\n\n"
        "Напиши тему поста:"
    )
    await state.set_state(PlanStates.adding_post_topic)
    await callback.answer()


async def process_add_post_topic(message: types.Message, state: FSMContext):
    """Обработка темы нового поста"""
    topic = message.text
    data = await state.get_data()
    day_num = data.get("adding_to_day")
    format_type = data.get("adding_format")
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    # Добавляем пост
    new_post_id = add_post_to_day(client_slug, plan_id, day_num, format_type, topic)

    if new_post_id:
        await message.answer(f"✅ Пост добавлен:\n{format_type}: {topic}")

        # Показываем день с обновлённым списком постов
        plan = load_plan(client_slug, plan_id)
        day = next((d for d in plan["days"] if d["day"] == day_num), None)

        if day:
            posts = day.get("posts", [])
            text = f"📆 День {day_num} ({day['date']})\n\n"
            for post in posts:
                protected = "🔒" if post.get("protected") else ""
                status = "✅" if post.get("status") == "done" else "⏳"
                text += f"{status} {protected}{post['format']}: {post['topic'][:40]}\n"

            text += "\n👇 Выбери пост:"
            await message.answer(text, reply_markup=get_day_view_keyboard(day_num, posts))
    else:
        await message.answer("❌ Ошибка добавления поста")

    await state.set_state(None)


# === УДАЛЕНИЕ ПОСТА ===

async def callback_delete_post(callback: CallbackQuery, state: FSMContext):
    """Удалить пост"""
    parts = callback.data.replace("post_delete_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await callback.answer("Пост не найден")
        return

    if post.get("protected"):
        await callback.answer("❌ Нельзя удалить ЛИДГЕН-пост", show_alert=True)
        return

    success = delete_post_from_day(client_slug, plan_id, day_num, post_id)

    if success:
        await callback.answer("✅ Пост удалён")

        # Показываем день с обновлённым списком
        plan = load_plan(client_slug, plan_id)
        day = next((d for d in plan["days"] if d["day"] == day_num), None)

        if day:
            posts = day.get("posts", [])
            text = f"📆 День {day_num} ({day['date']})\n\n"
            for p in posts:
                protected = "🔒" if p.get("protected") else ""
                status = "✅" if p.get("status") == "done" else "⏳"
                text += f"{status} {protected}{p['format']}: {p['topic'][:40]}\n"

            text += "\n👇 Выбери пост:"
            await callback.message.edit_text(text, reply_markup=get_day_view_keyboard(day_num, posts))
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)


# === ГЕНЕРАЦИЯ ПОСТА ===

async def callback_write_post(callback: CallbackQuery, state: FSMContext):
    """Генерация текста поста"""
    parts = callback.data.replace("post_write_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    day = next((d for d in plan["days"] if d["day"] == day_num), None)
    post = get_post_by_id(plan, day_num, post_id)

    if not day or not post:
        await callback.answer("Пост не найден")
        return

    await callback.message.edit_text(f"⏳ Генерирую пост: {post['format']}...")
    await callback.answer()

    try:
        context = get_client_prompt(client_slug)
        emoji_section = get_emoji_prompt_section(client_slug)

        format_type = post.get("format", "ПОСТ")
        topic = post.get("topic", "")

        system_prompt = f"""{context}

Ты пишешь пост для Telegram-канала агентства недвижимости.

ФОРМАТ: {format_type}

СТРУКТУРА ПОСТА:
1. Эмодзи-заголовок + тема
2. Эмоциональный хук (для кого)
3. Ключевые характеристики
4. Фишки проекта (▪️)
5. CTA (⚪️ "Напишите...")

{emoji_section}

ПРАВИЛА:
- НЕ используй markdown
- ЗАПРЕЩЕНО указывать название ЖК, девелопера, застройщика — используй "Жилой комплекс", "Проект", "Комплекс у парка"
- Короткие абзацы
- Конкретные цифры"""

        user_prompt = f"""Напиши пост на тему:
{topic}

Формат: {format_type}
День: {day.get('date', '')} ({day.get('weekday', '')})

ВАЖНО: Название ЖК и застройщика — служебная информация. В посте их указывать ЗАПРЕЩЕНО.

Сделай пост готовым к публикации."""

        post_text = generate_content_with_memory(client_slug, system_prompt, user_prompt)

        # Сохраняем пост в state
        await state.update_data(
            current_day_num=day_num,
            current_post_id=post_id,
            generated_post=post_text
        )

        # Показываем с кнопками согласования
        preview = post_text[:3000] + "..." if len(post_text) > 3000 else post_text
        await callback.message.answer(
            f"📝 Пост [{post['format']}]:\n\n{preview}",
            reply_markup=get_approve_post_keyboard(day_num, post_id)
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")


async def callback_approve_post(callback: CallbackQuery, state: FSMContext):
    """Согласовать пост и отправить оператору"""
    parts = callback.data.replace("post_approve_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")
    post_text = data.get("generated_post", "")

    if not post_text:
        await callback.answer("Пост не найден")
        return

    await callback.answer("Отправляю оператору...")

    # Отправляем в рабочий чат
    bot: Bot = callback.message.bot
    success = await send_post_to_operator(bot, client_slug, post_text)

    if success:
        # Обновляем статус поста
        update_post(client_slug, plan_id, day_num, post_id, {"status": "done"})
        await callback.message.edit_text(
            f"✅ Пост отправлен оператору @{config.OPERATOR_USERNAME}"
        )
    else:
        await callback.message.edit_text(
            f"⚠️ Не удалось отправить в рабочий чат. Пост:\n\n{post_text[:2000]}"
        )


async def callback_edit_post_text(callback: CallbackQuery, state: FSMContext):
    """Редактировать текст поста"""
    parts = callback.data.replace("post_edit_text_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    await state.update_data(editing_day=day_num, editing_post_id=post_id)

    await callback.message.answer("✏️ Напиши исправленный текст поста:")
    await state.set_state(PlanStates.editing_post)
    await callback.answer()


async def process_edit_post_text(message: types.Message, state: FSMContext):
    """Обработка отредактированного текста поста"""
    new_post = message.text
    data = await state.get_data()
    day_num = data.get("editing_day")
    post_id = data.get("editing_post_id")

    await state.update_data(generated_post=new_post)
    await state.set_state(None)

    await message.answer(
        f"✅ Пост обновлён:\n\n{new_post[:2000]}",
        reply_markup=get_approve_post_keyboard(day_num, post_id)
    )


# === ТЗ ДИЗАЙНЕРУ ===

async def callback_write_brief(callback: CallbackQuery, state: FSMContext):
    """Генерация ТЗ для поста"""
    parts = callback.data.replace("post_brief_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    day = next((d for d in plan.get("days", []) if d["day"] == day_num), None)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await callback.answer("Пост не найден")
        return

    # Сохраняем контекст
    await state.update_data(current_day_num=day_num, current_post_id=post_id)

    # Проверяем, есть ли данные лота в плане
    lot_data = post.get("lot_data", "")
    topic = post.get("topic", "")

    # Предлагаем варианты
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Из темы плана", callback_data=f"brief_from_topic_{day_num}_{post_id}")],
        [InlineKeyboardButton(text="📎 Добавить данные/ссылку", callback_data=f"brief_add_data_{day_num}_{post_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"post_view_{day_num}_{post_id}")]
    ])

    await callback.message.edit_text(
        f"🎨 ТЗ для поста: {topic[:50]}\n\n"
        "Как генерировать ТЗ?",
        reply_markup=keyboard
    )
    await callback.answer()


async def callback_brief_from_topic(callback: CallbackQuery, state: FSMContext):
    """Генерация ТЗ из темы плана (без запроса дополнительных данных)"""
    parts = callback.data.replace("brief_from_topic_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await callback.answer("Пост не найден")
        return

    await callback.message.edit_text(f"⏳ Генерирую ТЗ из темы: {post['topic'][:40]}...")
    await callback.answer()

    try:
        lot_data = f"Тема: {post['topic']}"

        system_prompt = """Ты — копирайтер. Создаёшь ТЗ для дизайнеров баннеров Telegram Ads.

ФОРМАТ ТЕКСТОВЫХ БЛОКОВ:
[ПЛАШКА 1] — Локация/Срочность
[ПЛАШКА 2] — Дополнительный триггер
[ЗАГОЛОВОК] — Основная выгода

ПРАВИЛА:
- Генерируй ТОЛЬКО текстовые блоки
- НЕ указывай название ЖК и девелопера
- Текст плашек: UPPERCASE, 2-4 слова
- Время до метро: "мин." (не "минут")
- Если есть данные о первом взносе — пиши "ПЕРВЫЙ ВЗНОС", не сокращай до "ВЗНОС"

ЗАПРЕЩЕНО:
- Абстракции ("история встречается с будущим")
- Размеры в пикселях"""

        user_prompt = f"""Данные лота:
{lot_data}

Тема из плана: {post['topic']}
Формат: {post.get('format', 'баннер')}

Сгенерируй 3 ВАРИАНТА:
1. ФИНАНСЫ — акцент на доступности
2. ЛОКАЦИЯ — акцент на близости
3. ПРЕМИУМ — акцент на уникальности"""

        brief = generate_content(system_prompt, user_prompt)

        await state.update_data(
            generated_brief=brief,
            current_day_num=day_num,
            current_post_id=post_id
        )

        preview = brief[:3000] + "..." if len(brief) > 3000 else brief
        await callback.message.answer(
            f"🎨 ТЗ:\n\n{preview}",
            reply_markup=get_approve_brief_keyboard(day_num, post_id)
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации: {e}")


async def callback_brief_add_data(callback: CallbackQuery, state: FSMContext):
    """Запрос дополнительных данных/ссылки для ТЗ"""
    parts = callback.data.replace("brief_add_data_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await callback.answer("Пост не найден")
        return

    await state.update_data(current_day_num=day_num, current_post_id=post_id)

    await callback.message.edit_text(
        f"🎨 ТЗ для: {post['topic'][:50]}\n\n"
        "Отправь данные лота:\n"
        "• Ссылка на сайт ЖК или планировку\n"
        "• Цена / взнос / платёж\n"
        "• Особенности\n\n"
        "💡 Ссылка на планировку будет передана дизайнеру"
    )
    await state.set_state(PlanStates.waiting_for_lot_data)
    await callback.answer()


async def process_lot_data_for_brief(message: types.Message, state: FSMContext):
    """Обработка данных лота для генерации ТЗ"""
    user_input = message.text
    data = await state.get_data()
    day_num = data.get("current_day_num")
    post_id = data.get("current_post_id")
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    plan = load_plan(client_slug, plan_id)
    post = get_post_by_id(plan, day_num, post_id)

    if not post:
        await message.answer("Пост не найден")
        await state.set_state(None)
        return

    await message.answer(f"⏳ Генерирую ТЗ для дизайнера...")
    await state.set_state(None)

    try:
        # Ищем URL в сообщении для передачи дизайнеру
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, user_input)
        url_for_designer = urls[0] if urls else None

        lot_data = user_input if user_input.lower() != "из темы" else f"Тема: {post['topic']}"

        system_prompt = """Ты — копирайтер. Создаёшь ТЗ для дизайнеров баннеров Telegram Ads.

ФОРМАТ ТЕКСТОВЫХ БЛОКОВ:
[ПЛАШКА 1] — Локация/Срочность
[ПЛАШКА 2] — Дополнительный триггер
[ЗАГОЛОВОК] — Основная выгода

ПРАВИЛА:
- Генерируй ТОЛЬКО текстовые блоки
- НЕ указывай название ЖК и девелопера
- Текст плашек: UPPERCASE, 2-4 слова
- Время до метро: "мин." (не "минут")
- Если есть данные о первом взносе — пиши "ПЕРВЫЙ ВЗНОС", не сокращай до "ВЗНОС"

ЗАПРЕЩЕНО:
- Абстракции ("история встречается с будущим")
- Размеры в пикселях"""

        user_prompt = f"""Данные лота:
{lot_data}

Тема из плана: {post['topic']}
Формат: {post.get('format', 'баннер')}

Сгенерируй 3 ВАРИАНТА:
1. ФИНАНСЫ — акцент на доступности
2. ЛОКАЦИЯ — акцент на близости
3. ПРЕМИУМ — акцент на уникальности"""

        brief = generate_content(system_prompt, user_prompt)

        # Добавляем ссылку для дизайнера в конец ТЗ
        if url_for_designer:
            brief = f"{brief}\n\n🔗 Ссылка на планировку/визуалы:\n{url_for_designer}"

        await state.update_data(generated_brief=brief)

        preview = brief[:3000] + "..." if len(brief) > 3000 else brief
        await message.answer(
            f"🎨 ТЗ:\n\n{preview}",
            reply_markup=get_approve_brief_keyboard(day_num, post_id)
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {e}")


async def callback_approve_brief(callback: CallbackQuery, state: FSMContext):
    """Согласовать ТЗ и отправить дизайнеру"""
    parts = callback.data.replace("brief_approve_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    data = await state.get_data()
    client_slug = data.get("current_client")
    brief = data.get("generated_brief", "")

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
            f"⚠️ Не удалось отправить. ТЗ:\n\n{brief[:2000]}"
        )


async def callback_edit_brief(callback: CallbackQuery, state: FSMContext):
    """Редактировать ТЗ"""
    parts = callback.data.replace("brief_edit_", "").split("_")
    day_num = int(parts[0])
    post_id = "_".join(parts[1:])

    await state.update_data(editing_day=day_num, editing_post_id=post_id)

    await callback.message.answer("✏️ Напиши исправленный текст ТЗ:")
    await state.set_state(PlanStates.editing_brief)
    await callback.answer()


async def process_edit_brief(message: types.Message, state: FSMContext):
    """Обработка отредактированного ТЗ"""
    new_brief = message.text
    data = await state.get_data()
    day_num = data.get("editing_day")
    post_id = data.get("editing_post_id")

    await state.update_data(generated_brief=new_brief)
    await state.set_state(None)

    await message.answer(
        f"✅ ТЗ обновлено:\n\n{new_brief[:2000]}",
        reply_markup=get_approve_brief_keyboard(day_num, post_id)
    )


# === ОЧИСТКА ПЛАНА ===

async def callback_plan_clear(callback: CallbackQuery, state: FSMContext):
    """Показать подтверждение очистки плана"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data="plan_clear_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="plan_back")
        ]
    ])

    await callback.message.edit_text(
        "🗑 **Удалить текущий контент-план?**\n\n"
        "Это действие необратимо.",
        reply_markup=keyboard
    )
    await callback.answer()


async def callback_plan_clear_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение очистки плана"""
    data = await state.get_data()
    client_slug = data.get("current_client")
    plan_id = data.get("current_plan_id")

    if not client_slug:
        await callback.answer("Клиент не выбран")
        return

    success = delete_plan(client_slug, plan_id)

    if success:
        # Очищаем данные плана из state
        await state.update_data(current_plan_id=None)
        await callback.message.edit_text(
            "✅ Контент-план удалён.\n\n"
            "Создай новый план через 📅 Контент-план"
        )
        await callback.answer("План удалён")
    else:
        await callback.answer("Ошибка удаления", show_alert=True)


async def cmd_plan_export_csv(message: types.Message, state: FSMContext):
    """Экспорт плана в CSV/текстовый формат"""
    if not config.ENABLE_PLAN_EXPORT:
        await message.answer("Функция выключена (ENABLE_PLAN_EXPORT=0)")
        return

    data = await state.get_data()
    client_slug = data.get("current_client")

    if not client_slug:
        await message.answer("⚠️ Сначала выбери клиента")
        return

    plan = load_plan(client_slug)

    if not plan:
        await message.answer(f"⚠️ Нет плана для {client_slug}")
        return

    # Формируем CSV-текст
    lines = ["date | client | format | topic | status"]
    lines.append("-" * 60)

    for day in plan.get("days", []):
        date = day.get("date", "")
        for post in day.get("posts", []):
            fmt = post.get("format", "ПОСТ")
            topic = post.get("topic", "").replace("|", "/")[:50]
            status = post.get("status", "pending")
            lines.append(f"{date} | {client_slug} | {fmt} | {topic} | {status}")

    csv_text = "\n".join(lines)

    # Отправляем как текст (Telegram ограничение 4096)
    if len(csv_text) > 4000:
        # Разбиваем на части
        parts = [csv_text[i:i+4000] for i in range(0, len(csv_text), 4000)]
        for part in parts:
            await message.answer(f"```\n{part}\n```", parse_mode="Markdown")
    else:
        await message.answer(
            f"📋 *Контент-план {client_slug}*\n\n"
            f"```\n{csv_text}\n```",
            parse_mode="Markdown"
        )


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков плана"""
    # Команда экспорта плана
    from aiogram.filters import Command
    dp.message.register(cmd_plan_export_csv, Command("plan_export_csv"))

    # Callback для дней плана
    dp.callback_query.register(callback_plan_day, F.data.startswith("plan_day_"))
    dp.callback_query.register(callback_plan_back, F.data == "plan_back")

    # Callback для очистки плана
    dp.callback_query.register(callback_plan_clear, F.data == "plan_clear")
    dp.callback_query.register(callback_plan_clear_confirm, F.data == "plan_clear_confirm")

    # Callback для просмотра поста
    dp.callback_query.register(callback_post_view, F.data.startswith("post_view_"))

    # Callback для действий с постом
    dp.callback_query.register(callback_edit_topic, F.data.startswith("post_edit_topic_"))
    dp.callback_query.register(callback_write_post, F.data.startswith("post_write_"))
    dp.callback_query.register(callback_write_brief, F.data.startswith("post_brief_"))
    dp.callback_query.register(callback_brief_from_topic, F.data.startswith("brief_from_topic_"))
    dp.callback_query.register(callback_brief_add_data, F.data.startswith("brief_add_data_"))
    dp.callback_query.register(callback_delete_post, F.data.startswith("post_delete_"))

    # Callback для добавления поста
    dp.callback_query.register(callback_add_post, F.data.startswith("post_add_") & ~F.data.startswith("post_add_format_"))
    dp.callback_query.register(callback_add_post_format, F.data.startswith("post_add_format_"))

    # Callback для согласования
    dp.callback_query.register(callback_approve_post, F.data.startswith("post_approve_"))
    dp.callback_query.register(callback_edit_post_text, F.data.startswith("post_edit_text_"))
    dp.callback_query.register(callback_approve_brief, F.data.startswith("brief_approve_"))
    dp.callback_query.register(callback_edit_brief, F.data.startswith("brief_edit_"))

    # FSM обработчики
    dp.message.register(process_edit_topic, PlanStates.editing_topic)
    dp.message.register(process_edit_post_text, PlanStates.editing_post)
    dp.message.register(process_edit_brief, PlanStates.editing_brief)
    dp.message.register(process_lot_data_for_brief, PlanStates.waiting_for_lot_data)
    dp.message.register(process_add_post_topic, PlanStates.adding_post_topic)
