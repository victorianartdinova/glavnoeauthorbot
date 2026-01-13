"""
Dev Handler — команды для работы с бэклогом разработки
Только для админа (ADMIN_USER_ID из config)
"""
from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
from utils.dev_backlog import backlog_store, sync_backlog_to_md, create_from_feedback


class DevStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_search = State()


def is_admin(user_id: int) -> bool:
    """Проверка админа"""
    admin_id = getattr(config, "ADMIN_USER_ID", None)
    return admin_id and user_id == admin_id


def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню бэклога"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="dev:add"),
            InlineKeyboardButton(text="📋 Список P0", callback_data="dev:list_p0"),
        ],
        [
            InlineKeyboardButton(text="🔄 В работе", callback_data="dev:in_progress"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data="dev:search"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="dev:stats"),
            InlineKeyboardButton(text="🔄 Sync MD", callback_data="dev:sync"),
        ],
    ])


def get_task_actions(task_id: int, current_status: str) -> InlineKeyboardMarkup:
    """Кнопки действий с задачей"""
    buttons = []

    if current_status == "todo":
        buttons.append([
            InlineKeyboardButton(text="▶️ В работу", callback_data=f"dev:status:{task_id}:in_progress"),
        ])
    elif current_status == "in_progress":
        buttons.append([
            InlineKeyboardButton(text="✅ Done", callback_data=f"dev:status:{task_id}:done"),
            InlineKeyboardButton(text="🚫 Blocked", callback_data=f"dev:status:{task_id}:blocked"),
        ])
    elif current_status == "blocked":
        buttons.append([
            InlineKeyboardButton(text="▶️ В работу", callback_data=f"dev:status:{task_id}:in_progress"),
        ])

    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"dev:delete:{task_id}"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="dev:back"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_task(task: dict, short: bool = False) -> str:
    """Форматирование задачи"""
    status_icon = {
        "todo": "⬜",
        "in_progress": "🔄",
        "done": "✅",
        "blocked": "🚫"
    }.get(task["status"], "⬜")

    type_icon = {
        "bug": "🐛",
        "feature": "✨",
        "debt": "🔧"
    }.get(task["type"], "📝")

    if short:
        return f"{status_icon} {type_icon} *#{task['id']}* [{task['priority']}] {task['title'][:50]}"

    lines = [
        f"{status_icon} {type_icon} *#{task['id']}* \\[{task['priority']}\\]",
        f"*{task['title']}*",
        f"Статус: {task['status']} | Тип: {task['type']}",
    ]

    if task.get("notes"):
        lines.append(f"📝 {task['notes'][:200]}")

    if task.get("related_files"):
        files = task["related_files"][:3]
        lines.append(f"📁 {', '.join(files)}")

    return "\n".join(lines)


# === Команды ===

async def cmd_dev_backlog(message: types.Message):
    """Команда /dev_backlog"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админа")
        return

    stats = backlog_store.stats()
    text = (
        "🛠 *Dev Backlog*\n\n"
        f"📊 Активных: {stats['total_active']}\n"
        f"• P0: {stats['by_priority'].get('P0', 0)}\n"
        f"• P1: {stats['by_priority'].get('P1', 0)}\n"
        f"• В работе: {stats['by_status'].get('in_progress', 0)}\n\n"
        "👇 Выбери действие:"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())


# === Callback handlers ===

async def cb_add_task(callback: types.CallbackQuery, state: FSMContext):
    """Добавить задачу"""
    await callback.message.edit_text(
        "➕ *Новая задача*\n\n"
        "Опиши проблему/идею одним сообщением.\n"
        "Бот сам определит тип и приоритет.\n\n"
        "_Примеры:_\n"
        "• баг: кнопка не работает\n"
        "• хочу фичу для экспорта\n"
        "• срочно: память течёт",
        parse_mode="Markdown"
    )
    await state.set_state(DevStates.waiting_for_task)
    await callback.answer()


async def cb_list_p0(callback: types.CallbackQuery):
    """Список P0 задач"""
    tasks = backlog_store.list_by_priority("P0", limit=10)

    if not tasks:
        await callback.message.edit_text(
            "🎉 *Нет P0 задач!*\n\nВсё критичное закрыто.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
    else:
        lines = ["🔴 *P0 задачи:*\n"]
        for t in tasks:
            lines.append(format_task(t, short=True))

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )

    await callback.answer()


async def cb_in_progress(callback: types.CallbackQuery):
    """Задачи в работе"""
    tasks = backlog_store.list_by_status("in_progress", limit=10)

    if not tasks:
        await callback.message.edit_text(
            "📭 *Нет задач в работе*\n\nВозьми что-то из бэклога!",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
    else:
        lines = ["🔄 *В работе:*\n"]
        for t in tasks:
            lines.append(format_task(t, short=True))

        # Кнопки для каждой задачи
        buttons = []
        for t in tasks[:5]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"#{t['id']} {t['title'][:30]}",
                    callback_data=f"dev:view:{t['id']}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="dev:back")])

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

    await callback.answer()


async def cb_search(callback: types.CallbackQuery, state: FSMContext):
    """Поиск"""
    await callback.message.edit_text(
        "🔍 *Поиск задач*\n\n"
        "Введи текст для поиска:",
        parse_mode="Markdown"
    )
    await state.set_state(DevStates.waiting_for_search)
    await callback.answer()


async def cb_stats(callback: types.CallbackQuery):
    """Статистика"""
    stats = backlog_store.stats()

    text = (
        "📊 *Статистика бэклога*\n\n"
        "*По статусу:*\n"
        f"• Todo: {stats['by_status'].get('todo', 0)}\n"
        f"• In Progress: {stats['by_status'].get('in_progress', 0)}\n"
        f"• Blocked: {stats['by_status'].get('blocked', 0)}\n"
        f"• Done: {stats['by_status'].get('done', 0)}\n\n"
        "*По приоритету (активные):*\n"
        f"• P0: {stats['by_priority'].get('P0', 0)}\n"
        f"• P1: {stats['by_priority'].get('P1', 0)}\n"
        f"• P2: {stats['by_priority'].get('P2', 0)}\n"
        f"• P3: {stats['by_priority'].get('P3', 0)}\n\n"
        f"*Всего активных: {stats['total_active']}*"
    )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer()


async def cb_sync(callback: types.CallbackQuery):
    """Синхронизация с MD"""
    result = sync_backlog_to_md()

    await callback.message.edit_text(
        "✅ *Синхронизировано*\n\n"
        f"• {result['backlog']}\n"
        f"• {result['status']}",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer("Sync done!")


async def cb_back(callback: types.CallbackQuery, state: FSMContext):
    """Назад в меню"""
    await state.clear()
    stats = backlog_store.stats()
    text = (
        "🛠 *Dev Backlog*\n\n"
        f"📊 Активных: {stats['total_active']}\n\n"
        "👇 Выбери действие:"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer()


async def cb_view_task(callback: types.CallbackQuery):
    """Просмотр задачи"""
    task_id = int(callback.data.split(":")[-1])
    task = backlog_store.get(task_id)

    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        format_task(task),
        parse_mode="Markdown",
        reply_markup=get_task_actions(task_id, task["status"])
    )
    await callback.answer()


async def cb_change_status(callback: types.CallbackQuery):
    """Изменить статус"""
    parts = callback.data.split(":")
    task_id = int(parts[2])
    new_status = parts[3]

    backlog_store.set_status(task_id, new_status)
    task = backlog_store.get(task_id)

    if task:
        await callback.message.edit_text(
            f"✅ Статус изменён на *{new_status}*\n\n" + format_task(task),
            parse_mode="Markdown",
            reply_markup=get_task_actions(task_id, new_status)
        )

    # Автосинк при завершении
    if new_status == "done":
        sync_backlog_to_md()

    await callback.answer(f"Status → {new_status}")


async def cb_delete_task(callback: types.CallbackQuery):
    """Удалить задачу"""
    task_id = int(callback.data.split(":")[-1])
    backlog_store.delete(task_id)

    await callback.message.edit_text(
        f"🗑 Задача #{task_id} удалена",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer("Удалено")


# === Message handlers ===

async def handle_new_task(message: types.Message, state: FSMContext):
    """Обработка новой задачи"""
    if not is_admin(message.from_user.id):
        return

    task = create_from_feedback(message.text, source="user")

    if task:
        await message.answer(
            f"✅ *Задача создана*\n\n{format_task(task)}",
            parse_mode="Markdown",
            reply_markup=get_task_actions(task["id"], task["status"])
        )
        sync_backlog_to_md()
    else:
        await message.answer(
            "⚠️ *Похожая задача уже есть*\n\n"
            "Используй поиск чтобы найти её.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )

    await state.clear()


async def handle_search(message: types.Message, state: FSMContext):
    """Обработка поиска"""
    if not is_admin(message.from_user.id):
        return

    tasks = backlog_store.search(message.text, limit=10)

    if not tasks:
        await message.answer(
            "🔍 *Ничего не найдено*",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
    else:
        lines = [f"🔍 *Найдено: {len(tasks)}*\n"]
        for t in tasks:
            lines.append(format_task(t, short=True))

        buttons = []
        for t in tasks[:5]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"#{t['id']} {t['title'][:30]}",
                    callback_data=f"dev:view:{t['id']}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="dev:back")])

        await message.answer(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

    await state.clear()


# === Регистрация ===

def register_handlers(dp: Dispatcher):
    """Регистрация хендлеров"""
    # Команда
    dp.message.register(cmd_dev_backlog, Command("dev"))

    # Callbacks
    dp.callback_query.register(cb_add_task, F.data == "dev:add")
    dp.callback_query.register(cb_list_p0, F.data == "dev:list_p0")
    dp.callback_query.register(cb_in_progress, F.data == "dev:in_progress")
    dp.callback_query.register(cb_search, F.data == "dev:search")
    dp.callback_query.register(cb_stats, F.data == "dev:stats")
    dp.callback_query.register(cb_sync, F.data == "dev:sync")
    dp.callback_query.register(cb_back, F.data == "dev:back")
    dp.callback_query.register(cb_view_task, F.data.startswith("dev:view:"))
    dp.callback_query.register(cb_change_status, F.data.startswith("dev:status:"))
    dp.callback_query.register(cb_delete_task, F.data.startswith("dev:delete:"))

    # State handlers
    dp.message.register(handle_new_task, DevStates.waiting_for_task)
    dp.message.register(handle_search, DevStates.waiting_for_search)
