"""
Обработчик метрик и отчётов
"""
from aiogram import types, Dispatcher, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from utils.client_context import list_clients, get_client_prompt
from utils.tg_booster_api import (
    load_metrics,
    update_cpl,
    update_tg_booster_metrics,
    format_metrics_report,
    save_tg_booster_config,
    get_tg_booster_config
)
from utils.claude_api import generate_content


class MetricsStates(StatesGroup):
    """Состояния для FSM"""
    waiting_for_metrics_client = State()
    waiting_for_report_client = State()


async def cmd_metrics(message: types.Message, state: FSMContext):
    """Команда /metrics - показать метрики клиента"""
    clients = list_clients()

    if not clients:
        await message.answer("❌ Нет клиентов. Создай клиента через /newclient")
        return

    # Если один клиент — сразу показываем
    if len(clients) == 1:
        report = format_metrics_report(clients[0])
        await message.answer(report)
        return

    # Иначе спрашиваем
    clients_list = "\n".join([f"• {c}" for c in clients])
    await message.answer(
        f"📊 Метрики клиента\n\n"
        f"Выбери клиента (напиши slug):\n{clients_list}"
    )
    await state.set_state(MetricsStates.waiting_for_metrics_client)


async def process_metrics_client(message: types.Message, state: FSMContext):
    """Обработка выбора клиента для метрик"""
    client_slug = message.text.strip().lower()
    clients = list_clients()

    if client_slug not in clients:
        await message.answer(f"❌ Клиент '{client_slug}' не найден. Попробуй снова.")
        return

    await state.clear()
    report = format_metrics_report(client_slug)
    await message.answer(report)


async def cmd_update_cpl(message: types.Message):
    """
    Команда /update_cpl - обновить CPL клиента

    Формат: /update_cpl 3500 client_slug
    Или: /update_cpl 3500 (если один клиент)
    """
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if len(args) < 1:
        await message.answer(
            "📊 Обновление CPL\n\n"
            "Формат: /update_cpl <сумма> [client_slug]\n\n"
            "Пример: /update_cpl 3500 apple_real_estate\n"
            "Или: /update_cpl 3500 (если один клиент)"
        )
        return

    # Парсим сумму
    try:
        cpl_value = float(args[0].replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer(f"❌ Неверный формат суммы: {args[0]}")
        return

    # Определяем клиента
    clients = list_clients()

    if len(args) >= 2:
        client_slug = args[1].lower()
    elif len(clients) == 1:
        client_slug = clients[0]
    else:
        await message.answer(
            f"❌ Укажи клиента: /update_cpl {cpl_value:.0f} client_slug\n\n"
            f"Доступные клиенты: {', '.join(clients)}"
        )
        return

    if client_slug not in clients:
        await message.answer(f"❌ Клиент '{client_slug}' не найден")
        return

    # Обновляем CPL
    metrics = update_cpl(client_slug, cpl_value)

    await message.answer(
        f"✅ CPL обновлён для {client_slug}\n\n"
        f"• Новый CPL: {cpl_value:,.0f} ₽\n"
        f"• Дата: {metrics['cpl_updated']}"
    )

    # Отправляем в рабочий чат (если настроен)
    if config.TEAM_CHAT_ID:
        try:
            bot: Bot = message.bot
            await bot.send_message(
                config.TEAM_CHAT_ID,
                f"📊 CPL обновлён: {client_slug}\n"
                f"• CPL: {cpl_value:,.0f} ₽\n"
                f"• От: @{message.from_user.username or message.from_user.first_name}"
            )
        except Exception:
            pass


async def cmd_update_metrics(message: types.Message):
    """
    Команда /update_metrics - обновить метрики TG Booster вручную

    Формат: /update_metrics client_slug ctr=2.3 cps=45 spend=10000
    """
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if len(args) < 2:
        await message.answer(
            "📊 Обновление метрик TG Booster\n\n"
            "Формат: /update_metrics client_slug параметры\n\n"
            "Параметры:\n"
            "• ctr=2.3 — CTR в процентах\n"
            "• cps=45 — стоимость подписки\n"
            "• impressions=10000 — показы\n"
            "• clicks=500 — клики\n"
            "• subscribers=100 — подписки\n"
            "• spend=5000 — расход\n\n"
            "Пример: /update_metrics apple_real_estate ctr=2.3 cps=45"
        )
        return

    client_slug = args[0].lower()
    clients = list_clients()

    if client_slug not in clients:
        await message.answer(f"❌ Клиент '{client_slug}' не найден")
        return

    # Парсим параметры
    params = {}
    for arg in args[1:]:
        if "=" in arg:
            key, value = arg.split("=", 1)
            try:
                if key in ["impressions", "clicks", "subscribers"]:
                    params[key] = int(value)
                else:
                    params[key] = float(value.replace(",", "."))
            except ValueError:
                await message.answer(f"❌ Неверное значение: {arg}")
                return

    if not params:
        await message.answer("❌ Не указаны параметры для обновления")
        return

    # Обновляем метрики
    metrics = update_tg_booster_metrics(client_slug, **params)

    # Формируем ответ
    updated = []
    if "ctr" in params:
        updated.append(f"CTR: {params['ctr']:.2f}%")
    if "cps" in params:
        updated.append(f"CPS: {params['cps']:,.0f} ₽")
    if "impressions" in params:
        updated.append(f"Показы: {params['impressions']:,}")
    if "clicks" in params:
        updated.append(f"Клики: {params['clicks']:,}")
    if "subscribers" in params:
        updated.append(f"Подписки: {params['subscribers']:,}")
    if "spend" in params:
        updated.append(f"Расход: {params['spend']:,.0f} ₽")

    await message.answer(
        f"✅ Метрики обновлены для {client_slug}\n\n"
        f"Обновлено:\n• " + "\n• ".join(updated)
    )


async def cmd_report(message: types.Message, state: FSMContext):
    """Команда /report - полный отчёт по клиенту с рекомендациями"""
    clients = list_clients()

    if not clients:
        await message.answer("❌ Нет клиентов. Создай клиента через /newclient")
        return

    # Если один клиент — сразу генерируем
    if len(clients) == 1:
        await generate_report(message, clients[0])
        return

    # Иначе спрашиваем
    clients_list = "\n".join([f"• {c}" for c in clients])
    await message.answer(
        f"📈 Отчёт по клиенту\n\n"
        f"Выбери клиента (напиши slug):\n{clients_list}"
    )
    await state.set_state(MetricsStates.waiting_for_report_client)


async def process_report_client(message: types.Message, state: FSMContext):
    """Обработка выбора клиента для отчёта"""
    client_slug = message.text.strip().lower()
    clients = list_clients()

    if client_slug not in clients:
        await message.answer(f"❌ Клиент '{client_slug}' не найден. Попробуй снова.")
        return

    await state.clear()
    await generate_report(message, client_slug)


async def generate_report(message: types.Message, client_slug: str):
    """Генерация полного отчёта с рекомендациями от Claude"""
    await message.answer(f"⏳ Генерирую отчёт для {client_slug}...")

    try:
        # Получаем метрики
        metrics = load_metrics(client_slug)
        metrics_text = format_metrics_report(client_slug)

        # Получаем контекст клиента
        context = get_client_prompt(client_slug)

        # Системный промпт
        system_prompt = f"""Ты — аналитик рекламных кампаний для агентства недвижимости премиум-сегмента.

{context}

Твоя задача: проанализировать метрики и дать рекомендации.

ВАЖНО:
- Анализируй только предоставленные данные
- Давай конкретные рекомендации (что делать, не абстрактно)
- Если данных мало — укажи что нужно собрать
- НЕ используй markdown-форматирование
- Используй эмодзи для структуры"""

        user_prompt = f"""Проанализируй метрики клиента и дай рекомендации:

{metrics_text}

Структура ответа:
1. Краткий анализ (2-3 предложения)
2. Что хорошо (если есть)
3. Что улучшить (конкретные действия)
4. Следующие шаги (1-3 пункта)

Если данных недостаточно — укажи какие метрики нужно добавить."""

        # Генерация через Claude
        analysis = generate_content(system_prompt, user_prompt)

        # Формируем полный отчёт
        full_report = f"📈 Отчёт: {client_slug}\n\n"
        full_report += metrics_text
        full_report += "\n" + "=" * 30 + "\n\n"
        full_report += "🤖 Анализ и рекомендации:\n\n"
        full_report += analysis

        # Отправляем результат
        max_length = 4000
        if len(full_report) > max_length:
            parts = [full_report[i:i+max_length] for i in range(0, len(full_report), max_length)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(full_report)

    except Exception as e:
        await message.answer(f"❌ Ошибка генерации отчёта: {str(e)}")


async def cmd_set_tg_token(message: types.Message):
    """
    Команда /set_tg_token - установить токен TG Booster для клиента

    Формат: /set_tg_token client_slug token
    """
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if len(args) < 2:
        await message.answer(
            "🔑 Установка токена TG Booster\n\n"
            "Формат: /set_tg_token client_slug token\n\n"
            "Пример: /set_tg_token apple_real_estate abc123xyz"
        )
        return

    client_slug = args[0].lower()
    token = args[1]

    clients = list_clients()
    if client_slug not in clients:
        await message.answer(f"❌ Клиент '{client_slug}' не найден")
        return

    # Сохраняем токен
    success = save_tg_booster_config(client_slug, token)

    if success:
        await message.answer(f"✅ Токен TG Booster сохранён для {client_slug}")
    else:
        await message.answer(f"❌ Не удалось сохранить токен")


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.message.register(cmd_metrics, Command("metrics"))
    dp.message.register(cmd_update_cpl, Command("update_cpl"))
    dp.message.register(cmd_update_metrics, Command("update_metrics"))
    dp.message.register(cmd_report, Command("report"))
    dp.message.register(cmd_set_tg_token, Command("set_tg_token"))

    # FSM обработчики
    dp.message.register(process_metrics_client, MetricsStates.waiting_for_metrics_client)
    dp.message.register(process_report_client, MetricsStates.waiting_for_report_client)
